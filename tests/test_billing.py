"""FR-81: marking entries as billed, and filtering on it."""

from __future__ import annotations

from datetime import date

import pytest

from cubit.cli.exit_codes import EXIT_ERROR, EXIT_OK
from cubit.core import (
    CubitError,
    Storage,
    check_data,
    edit_entry,
    find_entries,
    project_report,
    set_billed,
)

INVOICED = date(2026, 9, 30)


def _billed_ids(storage: Storage) -> set[str]:
    return {entry.id for entry in find_entries(storage, billed=True)}


# ------------------------------------------------------------------- core


def test_marking_entries_billed(storage: Storage) -> None:
    changed = set_billed(storage, ["a3f9c1", "c48d7e"], INVOICED)

    assert [entry.id for entry in changed] == ["a3f9c1", "c48d7e"]
    assert storage.find_entry("a3f9c1").billed_on == INVOICED
    assert _billed_ids(storage) == {"a3f9c1", "c48d7e"}


def test_marking_again_keeps_the_first_invoice_date(storage: Storage) -> None:
    set_billed(storage, ["a3f9c1"], INVOICED)
    changed = set_billed(storage, ["a3f9c1", "c48d7e"], date(2026, 10, 31))

    assert [entry.id for entry in changed] == ["c48d7e"]
    assert storage.find_entry("a3f9c1").billed_on == INVOICED


def test_unmarking_clears_the_date(storage: Storage) -> None:
    set_billed(storage, ["a3f9c1", "c48d7e"], INVOICED)
    changed = set_billed(storage, ["a3f9c1"], None)

    assert [entry.id for entry in changed] == ["a3f9c1"]
    assert _billed_ids(storage) == {"c48d7e"}


def test_an_unknown_id_marks_nothing(storage: Storage) -> None:
    with pytest.raises(CubitError, match="zzzzzz"):
        set_billed(storage, ["a3f9c1", "zzzzzz"], INVOICED)
    assert _billed_ids(storage) == set()


def test_marking_across_months(storage: Storage) -> None:
    set_billed(storage, ["9a1b2c", "a3f9c1"], INVOICED)
    assert _billed_ids(storage) == {"9a1b2c", "a3f9c1"}


def test_find_entries_by_billing(storage: Storage) -> None:
    set_billed(storage, ["a3f9c1"], INVOICED)
    everything = find_entries(storage)
    unbilled = find_entries(storage, billed=False)

    assert len(unbilled) == len(everything) - 1
    assert "a3f9c1" not in {entry.id for entry in unbilled}


def test_editing_an_entry_keeps_its_billing(storage: Storage) -> None:
    set_billed(storage, ["a3f9c1"], INVOICED)
    edit_entry(storage, "a3f9c1", note="Landing page, final")
    assert storage.find_entry("a3f9c1").billed_on == INVOICED

    edit_entry(storage, "a3f9c1", billed_on=None)
    assert storage.find_entry("a3f9c1").billed_on is None


def test_an_unbilled_project_report_still_measures_the_whole_budget(storage: Storage) -> None:
    set_billed(storage, ["a3f9c1"], INVOICED)
    report = project_report(
        storage.get_project("acme-web"),
        find_entries(storage),
        storage.load_projects_map(),
        billed=False,
    )

    assert "a3f9c1" not in {entry.id for entry in report.entries}
    assert report.budget.used_minutes == report.total.minutes
    assert report.period.minutes == report.total.minutes - 90


def test_check_warns_about_billing_before_the_work(storage: Storage) -> None:
    set_billed(storage, ["a3f9c1"], date(2026, 9, 1))
    codes = [problem.code for problem in check_data(storage).warnings]
    assert "billed-before-worked" in codes


# -------------------------------------------------------------------- CLI


def test_bill_by_filters(cli, storage: Storage) -> None:
    result = cli(
        "bill", "--project", "acme-web", "--from", "2026-09-01", "--on", "2026-09-30", "-y"
    )

    assert result.exit_code == EXIT_OK
    assert "3 entries" in result.stdout
    assert _billed_ids(storage) == {"a3f9c1", "c48d7e", "d90a11"}


def test_bill_asks_before_marking_and_refuses_without_a_terminal(cli, storage: Storage) -> None:
    result = cli("bill", "--project", "acme-web")

    assert result.exit_code == EXIT_ERROR
    assert "--yes" in result.output
    assert _billed_ids(storage) == set()


def test_bill_by_id_and_an_unknown_id(cli, storage: Storage) -> None:
    assert cli("bill", "a3f9c1", "-y").exit_code == EXIT_OK
    assert _billed_ids(storage) == {"a3f9c1"}

    result = cli("bill", "c48d7e", "zzzzzz", "-y")
    assert result.exit_code == EXIT_ERROR
    assert "zzzzzz" in result.output
    assert _billed_ids(storage) == {"a3f9c1"}


def test_bill_with_nothing_left_to_bill(cli, storage: Storage) -> None:
    cli("bill", "-y")
    result = cli("bill", "-y")
    assert result.exit_code == EXIT_OK
    assert "Nothing to bill" in result.stdout


def test_unbill_by_id_and_by_date(cli, storage: Storage) -> None:
    cli("bill", "a3f9c1", "c48d7e", "--on", "2026-09-30", "-y")
    cli("bill", "9a1b2c", "--on", "2026-09-01", "-y")

    assert cli("unbill", "c48d7e").exit_code == EXIT_OK
    assert _billed_ids(storage) == {"a3f9c1", "9a1b2c"}

    assert cli("unbill", "--on", "2026-09-30", "-y").exit_code == EXIT_OK
    assert _billed_ids(storage) == {"9a1b2c"}


def test_list_and_reports_filter_on_billing(cli) -> None:
    cli("bill", "a3f9c1", "--on", "2026-09-30", "-y")

    listed = cli("list", "--from", "2026-09-01", "--to", "2026-09-30", "--unbilled").stdout
    assert "a3f9c1" not in listed and "c48d7e" in listed

    billed = cli("list", "--from", "2026-09-01", "--to", "2026-09-30", "--billed").stdout
    assert "a3f9c1" in billed and "2026-09-30" in billed

    report = cli("report", "month", "2026-09", "--unbilled").stdout
    assert "2h10m" in report  # 3h40m logged, less the 1h30m billed


def test_billed_and_unbilled_together_are_refused(cli) -> None:
    result = cli("list", "--billed", "--unbilled")
    assert result.exit_code == EXIT_ERROR
    assert "not both" in result.output


# -------------------------------------------------------------------- web


def test_marking_billed_from_the_entries_page(web, storage: Storage) -> None:
    html = web.get("/entries/?from=2026-09-01&to=2026-09-30").get_data(as_text=True)
    assert "Mark 4 unbilled entries" in html

    response = web.post(
        "/entries/billed", {"entry_id": ["a3f9c1", "c48d7e"], "billed_on": "2026-09-30"}
    )
    assert "Marked 2 entries (2h10m) as billed." in response.get_data(as_text=True)
    assert _billed_ids(storage) == {"a3f9c1", "c48d7e"}


def test_the_entries_page_filters_and_labels_billed_entries(web, storage: Storage) -> None:
    set_billed(storage, ["a3f9c1"], INVOICED)

    unbilled = web.get("/entries/?from=2026-09-01&to=2026-09-30&billing=unbilled")
    assert "Landing page layout" not in unbilled.get_data(as_text=True)

    billed = web.get("/entries/?from=2026-09-01&to=2026-09-30&billing=billed")
    html = billed.get_data(as_text=True)
    assert "Landing page layout" in html
    assert "billed 2026-09-30" in html
    assert "Mark these 1 as unbilled" in html


def test_unmarking_from_the_entries_page(web, storage: Storage) -> None:
    set_billed(storage, ["a3f9c1", "c48d7e"], INVOICED)
    web.post("/entries/unbilled", {"entry_id": ["a3f9c1"]})
    assert _billed_ids(storage) == {"c48d7e"}


def test_the_edit_form_sets_and_clears_the_billing_date(web, storage: Storage) -> None:
    set_billed(storage, ["a3f9c1"], INVOICED)
    form = web.get("/entries/a3f9c1/edit").get_data(as_text=True)
    assert 'name="billed_on" value="2026-09-30"' in form

    web.post(
        "/entries/a3f9c1",
        {"project_id": "acme-web", "duration": "1h30m", "date": "2026-09-18", "billed_on": ""},
    )
    assert storage.find_entry("a3f9c1").billed_on is None


def test_a_report_of_unbilled_hours_downloads_as_that(web, storage: Storage) -> None:
    set_billed(storage, ["a3f9c1"], INVOICED)
    page = web.get("/reports/?view=month&from=2026-09-01&to=2026-09-30&billing=unbilled")
    html = page.get_data(as_text=True)
    assert "unbilled hours only" in html
    assert 'name="billing" value="unbilled"' in html  # carried into the download

    markdown = web.get(
        "/reports/export?view=month&from=2026-09-01&to=2026-09-30&billing=unbilled&format=markdown"
    ).get_data(as_text=True)
    assert "Landing page layout" not in markdown
    assert "Hotfix past midnight" in markdown
