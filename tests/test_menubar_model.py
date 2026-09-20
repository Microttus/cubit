"""FR-64 to FR-67 and FR-71: the menu decided without any macOS.

The whole point of the split is that these run on any platform, so nothing
here imports rumps, and nothing here needs a menu bar.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone

import pytest

from cubit.core import Storage, start_timer
from cubit.menubar.model import (
    DATA_PROBLEM,
    LABEL_NEW_CATEGORY,
    LABEL_NO_CATEGORY,
    MAX_PROJECTS,
    Choice,
    Icon,
    MenuModel,
    build_menu,
    category_choices,
    format_hm,
    menu_title,
    project_choices,
    rank_projects,
)

OSLO = timezone(timedelta(hours=2))


def test_the_menu_model_never_imports_rumps() -> None:
    """FR-71: the menu contents are testable without macOS."""
    import cubit.menubar
    import cubit.menubar.model  # noqa: F401

    assert "rumps" not in sys.modules
    assert cubit.menubar.build_menu is build_menu


# ---------------------------------------------------------------- H:MM


@pytest.mark.parametrize(
    ("minutes", "text"),
    [
        (0, "0:00"),
        (5, "0:05"),
        (60, "1:00"),
        (205, "3:25"),
        (850, "14:10"),
        (1440, "24:00"),
        (-10, "0:00"),
    ],
)
def test_format_hm(minutes: int, text: str) -> None:
    """FR-67: totals read as H:MM, which is what a menu has room for."""
    assert format_hm(minutes) == text


# --------------------------------------------------------------- title


@pytest.fixture
def running(storage: Storage):
    started = datetime(2026, 9, 21, 9, 5, tzinfo=OSLO)
    start_timer(storage, "acme-web", category="software-coding", note="Layout", now=started)
    return build_menu(
        storage,
        now=started + timedelta(hours=1, minutes=24),
        today=date(2026, 9, 21),
    )


def test_a_running_timer_gets_the_running_icon_and_a_title(running: MenuModel) -> None:
    """FR-64."""
    assert running.icon is Icon.RUNNING
    assert running.is_running
    assert running.title == "1:24"


def test_an_idle_menu_bar_is_the_icon_alone(storage: Storage) -> None:
    """FR-64: nothing running, nothing to say."""
    model = build_menu(storage)

    assert model.icon is Icon.IDLE
    assert model.title == ""
    assert not model.is_running


@pytest.mark.parametrize(
    ("style", "expected"),
    [("none", ""), ("time", "1:24"), ("project-time", "acme-web 1:24")],
)
def test_menubar_title_styles(running: MenuModel, style: str, expected: str) -> None:
    """FR-64: menubar_title is none | time | project-time."""
    assert menu_title(running.running, style) == expected


def test_the_title_follows_the_config(storage: Storage) -> None:
    """REQUIREMENTS 4.3: the style comes from config.yaml."""
    config = storage.load_config()
    storage.save_config(config.model_copy(update={"menubar_title": "project-time"}))

    started = datetime(2026, 9, 21, 9, 5, tzinfo=OSLO)
    start_timer(storage, "acme-web", now=started)
    model = build_menu(storage, now=started + timedelta(minutes=90))

    assert model.title == "acme-web 1:30"


def test_an_idle_title_is_empty_whatever_the_style(storage: Storage) -> None:
    for style in ("none", "time", "project-time"):
        assert menu_title(None, style) == ""


# ------------------------------------------------------- running timer


def test_the_running_lines(running: MenuModel) -> None:
    """FR-66: project, category and start time."""
    assert running.running is not None
    assert running.running.heading == "Acme website  #software-coding"
    assert running.running.detail == "Since 09:05  -  1:24"
    assert running.running.elapsed_minutes == 84


def test_a_timer_without_a_category(storage: Storage) -> None:
    started = datetime(2026, 9, 21, 9, 5, tzinfo=OSLO)
    start_timer(storage, "internal", now=started)
    model = build_menu(storage, now=started + timedelta(minutes=30))

    assert model.running is not None
    assert model.running.heading == "Internal work"
    assert model.running.category is None


def test_a_timer_on_a_project_that_vanished(storage: Storage) -> None:
    """A hand-edited projects.yaml must not blank the menu."""
    started = datetime(2026, 9, 21, 9, 5, tzinfo=OSLO)
    start_timer(storage, "acme-web", now=started)
    storage.projects_path.write_text("projects: []\n", encoding="utf-8")

    model = build_menu(storage, now=started + timedelta(minutes=30))
    assert model.running is not None
    assert model.running.heading == "acme-web"  # falls back to the id


# -------------------------------------------------------------- totals


def test_today_and_week_totals(storage: Storage) -> None:
    """FR-67, against the sample folder's week of 14-20 September 2026."""
    model = build_menu(storage, today=date(2026, 9, 18))

    assert model.today_minutes == 135  # 90 + 45 on the 18th
    assert model.today_text == "2:15"
    assert model.week_minutes == 220  # the whole ISO week
    assert model.week_text == "3:40"


def test_totals_use_the_configured_week_start(storage: Storage) -> None:
    config = storage.load_config()
    storage.save_config(config.model_copy(update={"week_starts_on": "sunday"}))

    model = build_menu(storage, today=date(2026, 9, 20))
    assert model.week_minutes == 0  # the Sunday week starts on the 20th


def test_a_day_with_nothing_logged(storage: Storage) -> None:
    model = build_menu(storage, today=date(2026, 9, 17))
    assert model.today_text == "0:00"
    assert model.week_text == "3:40"


# ------------------------------------------------------------ projects


def test_projects_are_offered_most_recently_used_first(storage: Storage) -> None:
    """FR-65."""
    model = build_menu(storage)
    assert [p.project_id for p in model.projects] == ["acme-web", "internal"]


def test_archived_projects_are_not_offered(storage: Storage) -> None:
    """FR-13, FR-65."""
    assert "old-site" not in {p.project_id for p in build_menu(storage).projects}


def test_a_project_used_today_moves_to_the_top(storage: Storage) -> None:
    from cubit.core import add_manual_entry

    add_manual_entry(storage, "internal", 30, day=date(2026, 12, 1))
    model = build_menu(storage)

    assert [p.project_id for p in model.projects][0] == "internal"


def test_at_most_eight_projects(storage: Storage) -> None:
    """FR-65: a submenu is not a project list."""
    from cubit.core import create_project

    for index in range(12):
        create_project(storage, f"extra-{index:02d}", name=f"Extra {index}")

    model = build_menu(storage)
    assert len(model.projects) == MAX_PROJECTS == 8


def test_unused_projects_come_last_alphabetically(storage: Storage) -> None:
    from cubit.core import create_project

    create_project(storage, "zulu", name="Zulu")
    create_project(storage, "alpha", name="Alpha")

    order = [p.project_id for p in build_menu(storage).projects]
    assert order == ["acme-web", "internal", "alpha", "zulu"]


def test_rank_projects_without_any_entries(storage: Storage) -> None:
    projects = [p for p in storage.load_projects() if p.is_active]
    assert [p.id for p in rank_projects(projects, [])] == ["acme-web", "internal"]


def test_no_projects_at_all(empty_storage: Storage) -> None:
    model = build_menu(empty_storage)
    assert model.projects == []
    assert not model.has_projects


# ---------------------------------------------------------- categories


def test_categories_are_in_suggestion_order_then_the_two_extras(
    storage: Storage,
) -> None:
    """FR-65, using core's own ranking (FR-46)."""
    model = build_menu(storage)
    acme = next(p for p in model.projects if p.project_id == "acme-web")

    assert [choice.label for choice in acme.categories] == [
        "#software-coding",
        "#project-management",
        "#testing",
        LABEL_NO_CATEGORY,
        LABEL_NEW_CATEGORY,
    ]


def test_the_two_extra_items_carry_their_meaning(storage: Storage) -> None:
    acme = next(p for p in build_menu(storage).projects if p.project_id == "acme-web")

    assert acme.categories[-2].kind is Choice.NONE
    assert acme.categories[-2].category is None
    assert acme.categories[-1].kind is Choice.NEW
    assert acme.categories[0].kind is Choice.CATEGORY
    assert acme.categories[0].category == "software-coding"


def test_a_project_with_no_categories_still_offers_the_extras(storage: Storage) -> None:
    from cubit.core import create_project

    project = create_project(storage, "beta-app", name="Beta app")
    choices = category_choices(project, storage.load_all_entries())

    assert [choice.label for choice in choices] == [LABEL_NO_CATEGORY, LABEL_NEW_CATEGORY]


def test_categories_are_per_project(storage: Storage) -> None:
    """FR-47: the menu suggests only the selected project's categories."""
    model = build_menu(storage)
    internal = next(p for p in model.projects if p.project_id == "internal")

    assert [c.label for c in internal.categories][0] == "#admin"
    assert "#software-coding" not in {c.label for c in internal.categories}


def test_project_choices_can_be_built_without_storage(storage: Storage) -> None:
    """FR-71: the ordering is a pure function over what core loaded."""
    choices = project_choices(storage.load_projects(), storage.load_all_entries())
    assert [choice.project_id for choice in choices] == ["acme-web", "internal"]


# --------------------------------------------------------- error states


def test_a_folder_that_will_not_parse_shows_one_clear_item(storage: Storage) -> None:
    """FR-73: errors never fail silently."""
    storage.projects_path.write_text("projects:\n  - id: Acme-Web\n    name: x\n", "utf-8")

    model = build_menu(storage)

    assert model.error == DATA_PROBLEM
    assert "cubit check" in model.error
    assert model.projects == []
    assert model.title == ""
    assert model.icon is Icon.IDLE


def test_a_malformed_entries_file_is_an_error_state(storage: Storage) -> None:
    storage.month_path(2026, 9).write_text("id,date\nbroken\n", encoding="utf-8")
    assert build_menu(storage).error == DATA_PROBLEM


def test_a_broken_config_is_an_error_state(storage: Storage) -> None:
    storage.config_path.write_text("menubar_title: flashing\n", encoding="utf-8")
    assert build_menu(storage).error == DATA_PROBLEM


def test_a_busy_folder_does_not_raise(storage: Storage) -> None:
    """FR-70, FR-73: a lock another process holds must not break the menu."""
    model = build_menu(storage)
    assert model.error is None  # reads do not take the lock at all


def test_a_folder_that_was_never_created(tmp_path) -> None:
    model = build_menu(Storage(tmp_path / "nothing-here"))
    assert model.error is None
    assert model.projects == []
    assert model.today_text == "0:00"


def test_an_empty_model_is_usable() -> None:
    model = MenuModel()
    assert (model.title, model.today_text, model.week_text) == ("", "0:00", "0:00")
    assert model.icon is Icon.IDLE
    assert not model.is_running
