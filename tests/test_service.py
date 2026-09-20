"""The operations behind the commands (cubit.core.service)."""

from __future__ import annotations

import threading
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest

from cubit.core import (
    CubitError,
    ProjectError,
    ProjectStatus,
    Storage,
    TimerError,
    add_manual_entry,
    archive_project,
    cancel_timer,
    check_category,
    create_project,
    edit_entry,
    edit_project,
    end_of,
    ensure_loggable,
    find_entries,
    remove_entry,
    remove_project,
    running_timer,
    set_rate,
    start_timer,
    stop_timer,
    unarchive_project,
    unregister_project_category,
)

OSLO = timezone(timedelta(hours=2))


# ------------------------------------------------------------------ timer


def test_start_timer_writes_the_state_and_registers_the_category(storage: Storage) -> None:
    """FR-1 and FR-45."""
    state = start_timer(storage, "internal", category="#Code Review", note="Cleanup")

    assert state.project_id == "internal"
    assert state.category == "code-review"
    assert running_timer(storage) == state
    assert "code-review" in storage.get_project("internal").categories


def test_only_one_timer_runs_at_a_time(storage: Storage) -> None:
    """FR-1."""
    start_timer(storage, "acme-web")
    with pytest.raises(TimerError, match="already running"):
        start_timer(storage, "internal")


def test_start_refuses_an_archived_project_unless_forced(storage: Storage) -> None:
    """FR-10."""
    with pytest.raises(ProjectError, match="archived"):
        start_timer(storage, "old-site")

    state = start_timer(storage, "old-site", force=True)
    assert state.project_id == "old-site"


def test_ensure_loggable_hints_at_the_way_out(storage: Storage) -> None:
    with pytest.raises(ProjectError) as caught:
        ensure_loggable(storage.get_project("old-site"))
    assert "--force" in (caught.value.hint or "")


def test_stop_timer_saves_the_entry_and_clears_the_state(storage: Storage) -> None:
    """FR-2."""
    started = datetime(2026, 9, 21, 9, 5, tzinfo=OSLO)
    start_timer(storage, "acme-web", category="testing", note="Unit tests", now=started)

    entry = stop_timer(storage, now=datetime(2026, 9, 21, 10, 35, tzinfo=OSLO))

    assert entry.duration_minutes == 90
    assert entry.date == date(2026, 9, 21)
    assert entry.category == "testing"
    assert entry.note == "Unit tests"
    assert running_timer(storage) is None
    assert storage.find_entry(entry.id) == entry


def test_stop_timer_can_change_the_note_and_category(storage: Storage) -> None:
    """FR-2 and FR-45: a category set at stop is registered too."""
    start_timer(storage, "internal", now=datetime(2026, 9, 21, 9, 0, tzinfo=OSLO))
    entry = stop_timer(
        storage,
        note="Quarterly VAT",
        category="#Book Keeping",
        now=datetime(2026, 9, 21, 9, 30, tzinfo=OSLO),
    )

    assert entry.note == "Quarterly VAT"
    assert entry.category == "book-keeping"
    assert "book-keeping" in storage.get_project("internal").categories


def test_a_timer_past_midnight_is_one_entry_on_the_start_date(storage: Storage) -> None:
    """FR-9, end to end through the service."""
    start_timer(storage, "acme-web", now=datetime(2026, 9, 21, 23, 30, tzinfo=OSLO))
    entry = stop_timer(storage, now=datetime(2026, 9, 22, 0, 15, tzinfo=OSLO))

    assert entry.date == date(2026, 9, 21)
    assert entry.duration_minutes == 45
    assert [e.id for e in storage.load_entries(date(2026, 9, 22), date(2026, 9, 22))] == []


def test_stop_without_a_timer_is_an_error_with_a_hint(storage: Storage) -> None:
    with pytest.raises(TimerError) as caught:
        stop_timer(storage)
    assert "cubit start" in (caught.value.hint or "")


def test_cancel_timer_logs_nothing(storage: Storage) -> None:
    """FR-4."""
    before = len(storage.load_all_entries())
    start_timer(storage, "acme-web")

    state = cancel_timer(storage)

    assert state.project_id == "acme-web"
    assert running_timer(storage) is None
    assert len(storage.load_all_entries()) == before


def test_cancel_without_a_timer_is_an_error(storage: Storage) -> None:
    with pytest.raises(TimerError, match="No timer"):
        cancel_timer(storage)


# ---------------------------------------------------------------- entries


def test_add_manual_entry(storage: Storage) -> None:
    """FR-5."""
    entry = add_manual_entry(
        storage,
        "acme-web",
        90,
        day=date(2026, 9, 21),
        category="#Software Coding",
        note="Refactor",
    )

    assert entry.duration_minutes == 90
    assert entry.category == "software-coding"
    assert entry.start is None and entry.end is None
    assert storage.find_entry(entry.id) == entry


def test_add_manual_entry_works_out_the_end_from_the_start(storage: Storage) -> None:
    entry = add_manual_entry(storage, "acme-web", 90, day=date(2026, 9, 21), start=time(13, 0))
    assert entry.start == time(13, 0)
    assert entry.end == time(14, 30)


def test_add_manual_entry_wraps_an_end_past_midnight(storage: Storage) -> None:
    entry = add_manual_entry(storage, "acme-web", 45, day=date(2026, 9, 21), start=time(23, 40))
    assert entry.end == time(0, 25)
    assert entry.date == date(2026, 9, 21)


def test_add_manual_entry_registers_a_new_category(storage: Storage) -> None:
    """FR-45."""
    add_manual_entry(storage, "internal", 30, day=date(2026, 9, 21), category="Invoicing")
    assert "invoicing" in storage.get_project("internal").categories


def test_add_manual_entry_refuses_an_archived_project(storage: Storage) -> None:
    """FR-10."""
    with pytest.raises(ProjectError, match="archived"):
        add_manual_entry(storage, "old-site", 30, day=date(2026, 9, 21))
    assert add_manual_entry(storage, "old-site", 30, day=date(2026, 9, 21), force=True)


def test_end_of_wraps_at_midnight() -> None:
    assert end_of(time(9, 0), 90) == time(10, 30)
    assert end_of(time(23, 40), 45) == time(0, 25)


def test_edit_entry_changes_only_what_it_is_given(storage: Storage) -> None:
    """FR-7."""
    before = storage.find_entry("a3f9c1")
    assert before is not None

    after = edit_entry(storage, "a3f9c1", note="Landing page, second pass")

    assert after.note == "Landing page, second pass"
    assert after.duration_minutes == before.duration_minutes
    assert after.category == before.category
    assert after.date == before.date


def test_edit_entry_recomputes_the_end_when_the_duration_changes(storage: Storage) -> None:
    after = edit_entry(storage, "a3f9c1", duration_minutes=120)
    assert after.start == time(9, 5)
    assert after.end == time(11, 5)


def test_edit_entry_recomputes_the_end_when_the_start_changes(storage: Storage) -> None:
    after = edit_entry(storage, "a3f9c1", start=time(8, 0))
    assert after.end == time(9, 30)


def test_edit_entry_can_clear_the_times(storage: Storage) -> None:
    after = edit_entry(storage, "a3f9c1", start=None)
    assert after.start is None and after.end is None
    assert after.duration_minutes == 90


def test_edit_entry_can_clear_the_category(storage: Storage) -> None:
    after = edit_entry(storage, "a3f9c1", category=None)
    assert after.category is None


def test_edit_entry_moves_between_months(storage: Storage) -> None:
    after = edit_entry(storage, "a3f9c1", day=date(2026, 10, 2))
    assert after.date == date(2026, 10, 2)
    assert storage.find_entry("a3f9c1") == after
    assert "a3f9c1" not in {e.id for e in storage.load_month(2026, 9)}


def test_edit_entry_moves_between_projects_and_registers_the_category(
    storage: Storage,
) -> None:
    after = edit_entry(storage, "b71c02", project_id="acme-web", category="admin")
    assert after.project_id == "acme-web"
    assert "admin" in storage.get_project("acme-web").categories


def test_edit_entry_refuses_an_archived_target_project(storage: Storage) -> None:
    """FR-10."""
    with pytest.raises(ProjectError, match="archived"):
        edit_entry(storage, "a3f9c1", project_id="old-site")


def test_edit_entry_without_changes_is_a_no_op(storage: Storage) -> None:
    before = storage.projects_path.read_text(encoding="utf-8")
    assert edit_entry(storage, "a3f9c1") == storage.find_entry("a3f9c1")
    assert storage.projects_path.read_text(encoding="utf-8") == before


def test_edit_unknown_entry_has_a_hint(storage: Storage) -> None:
    with pytest.raises(CubitError) as caught:
        edit_entry(storage, "ffffff", note="nope")
    assert "cubit list" in (caught.value.hint or "")


def test_remove_entry(storage: Storage) -> None:
    """FR-7."""
    removed = remove_entry(storage, "c48d7e")
    assert removed.id == "c48d7e"
    assert storage.find_entry("c48d7e") is None

    with pytest.raises(CubitError, match="No entry"):
        remove_entry(storage, "c48d7e")


def test_find_entries_by_client(storage: Storage) -> None:
    """FR-6: a client filter spans that client's projects."""
    acme = find_entries(storage, client="acme corp")
    assert {entry.project_id for entry in acme} == {"acme-web"}

    icecube = find_entries(storage, client="IceCube Solutions")
    assert {entry.project_id for entry in icecube} == {"internal"}


def test_find_entries_combines_filters(storage: Storage) -> None:
    found = find_entries(
        storage,
        start=date(2026, 9, 1),
        end=date(2026, 9, 30),
        category="#Software Coding",
    )
    assert {entry.id for entry in found} == {"a3f9c1", "d90a11"}


def test_find_entries_for_an_unknown_client_is_empty(storage: Storage) -> None:
    assert find_entries(storage, client="Nobody") == []


def test_ids_stay_unique_when_two_threads_log_at_once(storage: Storage) -> None:
    """The id is generated inside the lock that writes the entry."""
    barrier = threading.Barrier(2)
    failures: list[BaseException] = []

    def log() -> None:
        own = Storage(storage.data_dir)
        barrier.wait()
        try:
            for _ in range(10):
                add_manual_entry(own, "acme-web", 30, day=date(2026, 9, 25))
        except BaseException as error:  # noqa: BLE001 - reported below
            failures.append(error)

    threads = [threading.Thread(target=log) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not failures
    logged = storage.load_entries(date(2026, 9, 25), date(2026, 9, 25))
    assert len(logged) == 20
    assert len({entry.id for entry in logged}) == 20


# --------------------------------------------------------------- projects


def test_create_project_with_a_first_rate(storage: Storage) -> None:
    """FR-11, FR-14."""
    project = create_project(
        storage,
        "beta-app",
        name="Beta app",
        client="Beta AS",
        budget_hours=Decimal("40"),
        categories=["#Software Coding"],
        rate=Decimal("110"),
        rate_from=date(2026, 9, 1),
    )

    assert project.categories == ["software-coding"]
    assert project.rates[0].rate == Decimal("110")
    assert storage.get_project("beta-app") == project


def test_create_project_without_a_rate_is_unrated(storage: Storage) -> None:
    """FR-15."""
    assert create_project(storage, "pro-bono", name="Pro bono").rates == []


def test_a_rate_start_date_without_a_rate_is_an_error(storage: Storage) -> None:
    with pytest.raises(CubitError, match="rate start date"):
        create_project(storage, "beta-app", name="Beta app", rate_from=date(2026, 9, 1))


def test_edit_project_cannot_change_the_id(storage: Storage) -> None:
    """FR-12: there is no way to ask for it."""
    project = edit_project(storage, "acme-web", name="Acme website v2", client="Acme AS")
    assert project.id == "acme-web"
    assert project.name == "Acme website v2"
    assert project.client == "Acme AS"


def test_edit_project_can_clear_the_budget(storage: Storage) -> None:
    assert edit_project(storage, "acme-web", budget_hours=None).budget_hours is None


def test_set_rate_appends_a_step(storage: Storage) -> None:
    """FR-14."""
    project = set_rate(storage, "acme-web", Decimal("120"), date(2027, 1, 1))
    assert [step.valid_from for step in project.rates] == [
        date(2026, 1, 1),
        date(2026, 7, 1),
        date(2027, 1, 1),
    ]
    assert project.rates[-1].rate == Decimal("120")


def test_set_rate_replaces_a_step_that_starts_the_same_day(storage: Storage) -> None:
    project = set_rate(storage, "acme-web", Decimal("99"), date(2026, 7, 1))
    assert len(project.rates) == 2
    assert project.rates[-1].rate == Decimal("99")


def test_archive_and_unarchive(storage: Storage) -> None:
    """FR-13."""
    assert archive_project(storage, "internal").status is ProjectStatus.ARCHIVED
    assert archive_project(storage, "internal").status is ProjectStatus.ARCHIVED  # idempotent
    assert storage.load_entries(project_id="internal")  # entries stay

    assert unarchive_project(storage, "internal").status is ProjectStatus.ACTIVE


def test_a_project_with_entries_cannot_be_deleted(storage: Storage) -> None:
    """FR-16."""
    with pytest.raises(ProjectError) as caught:
        remove_project(storage, "acme-web")
    assert "archive" in (caught.value.hint or "").lower()
    assert storage.get_project("acme-web")


def test_a_project_without_entries_can_be_deleted(storage: Storage) -> None:
    create_project(storage, "beta-app", name="Beta app")
    removed = remove_project(storage, "beta-app")

    assert removed.id == "beta-app"
    assert [project.id for project in storage.load_projects()] == [
        "acme-web",
        "internal",
        "old-site",
    ]


def test_unregister_a_category_leaves_the_entries_alone(storage: Storage) -> None:
    """FR-55: remove only unregisters the name."""
    project = unregister_project_category(storage, "acme-web", "#Testing")
    assert project.categories == ["software-coding", "project-management"]
    assert {e.category for e in storage.load_entries(project_id="acme-web")} == {
        "software-coding",
        "project-management",
    }


def test_unregister_an_unknown_category_is_an_error(storage: Storage) -> None:
    with pytest.raises(CubitError, match="no category"):
        unregister_project_category(storage, "acme-web", "invoicing")


# -------------------------------------------------------------- categories


def test_check_category_knows_a_registered_name(storage: Storage) -> None:
    """FR-45: a known category asks nothing."""
    result = check_category(storage.get_project("acme-web"), "#Software Coding")
    assert result.slug == "software-coding"
    assert result.is_registered
    assert not result.is_new
    assert result.did_you_mean is None


def test_check_category_flags_a_new_name(storage: Storage) -> None:
    result = check_category(storage.get_project("acme-web"), "Invoicing")
    assert result.is_new
    assert result.did_you_mean is None


def test_check_category_offers_a_near_miss(storage: Storage) -> None:
    """FR-52."""
    result = check_category(storage.get_project("acme-web"), "software-codng")
    assert result.is_new
    assert result.did_you_mean == "software-coding"
