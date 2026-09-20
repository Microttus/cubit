"""FR-78: the settings page, which edits config.yaml.

config.yaml stays a hand-editable file (FR-37). These tests hold the page to
that: it must write the same shape the CLI reads, and must not cost the user
the comments they wrote in it.
"""

from __future__ import annotations

from cubit.cli.exit_codes import EXIT_OK
from cubit.core import Storage
from helpers import text_of


def test_the_page_shows_every_setting(web, storage: Storage) -> None:
    """REQUIREMENTS 4.3 lists six; all six are editable."""
    html = text_of(web.get("/settings/"))

    for field in [
        "currency",
        "week_starts_on",
        "budget_warning_percent",
        "prompt_for_category",
        "theme",
        "menubar_title",
    ]:
        assert f'name="{field}"' in html, field


def test_the_form_is_filled_in_from_the_file(web, storage: Storage) -> None:
    html = text_of(web.get("/settings/"))

    assert 'value="EUR"' in html  # the sample folder's currency
    assert 'value="80"' in html
    assert "checked" in html  # prompt_for_category is on


def test_saving_writes_every_setting(web, storage: Storage) -> None:
    response = web.post(
        "/settings/",
        {
            "currency": "NOK",
            "week_starts_on": "sunday",
            "budget_warning_percent": "60",
            "prompt_for_category": "1",
            "theme": "light",
            "menubar_title": "project-time",
        },
    )
    assert response.status_code == 200
    assert "Settings saved." in text_of(response)

    config = storage.load_config()
    assert config.currency == "NOK"
    assert config.week_starts_on == "sunday"
    assert config.budget_warning_percent == 60
    assert config.theme == "light"
    assert config.menubar_title == "project-time"


def test_an_unchecked_box_turns_the_setting_off(web, storage: Storage) -> None:
    """A checkbox that is off sends nothing at all, which must mean false."""
    assert storage.load_config().prompt_for_category is True

    web.post(
        "/settings/",
        {
            "currency": "NOK",
            "week_starts_on": "monday",
            "budget_warning_percent": "80",
            "theme": "dark",
            "menubar_title": "time",
        },
    )
    assert storage.load_config().prompt_for_category is False


def test_saving_keeps_the_comments_in_the_file(web, storage: Storage) -> None:
    """The file is meant to be edited by hand, so saving must not flatten it."""
    storage.config_path.write_text(
        "# My notes about this folder\ncurrency: EUR  # invoiced in euros\n"
        "week_starts_on: monday\n",
        encoding="utf-8",
    )

    web.post(
        "/settings/",
        {
            "currency": "NOK",
            "week_starts_on": "monday",
            "budget_warning_percent": "80",
            "theme": "dark",
            "menubar_title": "time",
        },
    )

    text = storage.config_path.read_text(encoding="utf-8")
    assert "# My notes about this folder" in text
    assert "currency: NOK" in text


def test_the_cli_sees_what_the_page_saved(web, cli, storage: Storage) -> None:
    """One config file, three front ends (REQUIREMENTS section 6)."""
    web.post(
        "/settings/",
        {
            "currency": "NOK",
            "week_starts_on": "monday",
            "budget_warning_percent": "80",
            "theme": "dark",
            "menubar_title": "time",
        },
    )
    result = cli("report", "project", "acme-web")

    assert result.exit_code == EXIT_OK
    assert "NOK" in result.stdout


def test_a_bad_percentage_changes_nothing(web, storage: Storage) -> None:
    """Nothing is written until the whole config validates."""
    before = storage.config_path.read_text(encoding="utf-8")

    response = web.post(
        "/settings/",
        {
            "currency": "NOK",
            "week_starts_on": "monday",
            "budget_warning_percent": "500",
            "theme": "dark",
            "menubar_title": "time",
        },
    )

    assert "budget_warning_percent" in text_of(response)
    assert "nothing was saved" in text_of(response)
    assert storage.config_path.read_text(encoding="utf-8") == before


def test_a_percentage_that_is_not_a_number(web, storage: Storage) -> None:
    response = web.post(
        "/settings/",
        {
            "currency": "NOK",
            "week_starts_on": "monday",
            "budget_warning_percent": "lots",
            "theme": "dark",
            "menubar_title": "time",
        },
    )
    assert "whole number" in text_of(response)


def test_a_blank_currency_is_refused(web, storage: Storage) -> None:
    """Money with no currency reads as a bare number everywhere."""
    response = web.post(
        "/settings/",
        {
            "currency": "  ",
            "week_starts_on": "monday",
            "budget_warning_percent": "80",
            "theme": "dark",
            "menubar_title": "time",
        },
    )
    assert "currency" in text_of(response).lower()
    assert storage.load_config().currency == "EUR"


def test_an_unknown_theme_is_refused(web, storage: Storage) -> None:
    response = web.post(
        "/settings/",
        {
            "currency": "NOK",
            "week_starts_on": "monday",
            "budget_warning_percent": "80",
            "theme": "neon",
            "menubar_title": "time",
        },
    )
    assert "theme" in text_of(response)
    assert storage.load_config().theme == "dark"


def test_an_error_never_leaves_a_half_written_file(web, storage: Storage) -> None:
    """A rejected save must not have applied the settings before it."""
    web.post(
        "/settings/",
        {
            "currency": "USD",
            "week_starts_on": "sunday",
            "budget_warning_percent": "999",
            "theme": "light",
            "menubar_title": "none",
        },
    )
    config = storage.load_config()

    assert config.currency == "EUR"
    assert config.week_starts_on == "monday"
    assert config.theme == "dark"


def test_saving_needs_a_token(web) -> None:
    """FR-36: it changes a file, so it is not exempt."""
    assert web.raw.post("/settings/", data={"currency": "NOK"}).status_code == 400


def test_the_page_is_in_the_navigation(web) -> None:
    html = text_of(web.get("/"))
    assert ">Settings</a>" in html


def test_the_page_marks_itself_active(web) -> None:
    html = text_of(web.get("/settings/"))
    active = [line for line in html.splitlines() if "is-active" in line]
    assert any("Settings" in line for line in active)


def test_the_page_says_where_the_file_is(web, storage: Storage) -> None:
    """A settings page should not hide the file it is editing."""
    html = text_of(web.get("/settings/"))
    assert str(storage.config_path) in html
    assert str(storage.data_dir) in html
    assert "cubit check" in html


def test_the_header_toggle_still_works(web, storage: Storage) -> None:
    """FR-62: the quick switch stays, alongside the full page."""
    web.post("/settings/theme", {"theme": "light"})
    assert storage.load_config().theme == "light"


def test_the_toggle_leaves_the_other_settings_alone(web, storage: Storage) -> None:
    web.post("/settings/theme", {"theme": "light"})
    config = storage.load_config()

    assert config.currency == "EUR"
    assert config.budget_warning_percent == 80
    assert config.menubar_title == "time"
