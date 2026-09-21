"""FR-30 to FR-34, FR-50 and FR-62: the pages, what they show and what they change."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from cubit.core import ProjectStatus, Storage
from helpers import active_tab, row_for, text_of

# --------------------------------------------------------------- dashboard


def test_dashboard_shows_the_week_and_a_start_form(web, storage: Storage) -> None:
    """FR-31."""
    html = text_of(web.get("/"))

    assert "Start a timer" in html
    assert "This week" in html
    assert "Today" in html
    assert 'action="/timer/start"' in html


def test_dashboard_shows_the_running_timer(web, storage: Storage) -> None:
    """FR-3, FR-31."""
    web.post("/timer/start", {"project_id": "acme-web", "category": "testing", "note": "Web"})

    html = text_of(web.get("/"))
    assert "Running" in html
    assert "Acme website" in html
    assert "#testing" in html
    assert "Web" in html
    assert "data-started-at=" in html  # the script counts up from here
    assert 'action="/timer/stop"' in html


def test_starting_a_timer_registers_a_new_category(web, storage: Storage) -> None:
    """FR-45 from the browser."""
    web.post("/timer/start", {"project_id": "internal", "category": "Code Review"})

    state = storage.read_timer()
    assert state is not None
    assert state.category == "code-review"
    assert "code-review" in storage.get_project("internal").categories


def test_stopping_the_timer_logs_an_entry(web, storage: Storage) -> None:
    """FR-2."""
    before = len(storage.load_all_entries())
    web.post("/timer/start", {"project_id": "acme-web"})
    response = web.post("/timer/stop", {"note": "Done"})

    assert "Logged" in text_of(response)
    assert storage.read_timer() is None
    assert len(storage.load_all_entries()) == before + 1
    assert storage.load_all_entries()[-1].note == "Done"


def test_cancelling_the_timer_logs_nothing(web, storage: Storage) -> None:
    """FR-4."""
    before = len(storage.load_all_entries())
    web.post("/timer/start", {"project_id": "acme-web"})
    response = web.post("/timer/cancel")

    assert "Nothing was logged" in text_of(response)
    assert storage.read_timer() is None
    assert len(storage.load_all_entries()) == before


def test_a_second_timer_is_refused_with_a_message(web) -> None:
    """FR-1: errors flash, they do not crash."""
    web.post("/timer/start", {"project_id": "acme-web"})
    response = web.post("/timer/start", {"project_id": "internal"})

    assert response.status_code == 200
    assert "already running" in text_of(response)
    assert "Traceback" not in text_of(response)


def test_the_timer_is_shared_with_the_cli(web, cli, storage: Storage) -> None:
    """FR-8: started in one interface, seen and stopped in the other."""
    web.post("/timer/start", {"project_id": "acme-web", "note": "From the web"})

    status = cli("status")
    assert "acme-web" in status.stdout
    assert "From the web" in status.stdout

    cli("stop")
    assert storage.read_timer() is None
    assert "No timer running." in text_of(web.get("/")) or "Start a timer" in text_of(web.get("/"))


def test_a_timer_started_in_the_cli_shows_in_the_web_app(web, cli) -> None:
    """FR-8, the other way round."""
    cli("start", "acme-web", "-m", "From the CLI", "--yes")
    assert "From the CLI" in text_of(web.get("/"))


# ----------------------------------------------------------------- entries


def test_entries_page_lists_and_totals(web) -> None:
    """FR-32."""
    html = text_of(web.get("/entries/?all=1"))

    assert "6 entries" in html
    assert "5h40m" in html
    for entry_id in ["a3f9c1", "b71c02", "c48d7e"]:
        assert f"/entries/{entry_id}/edit" in html


def test_entries_page_filters(web) -> None:
    """FR-6, FR-32."""
    by_project = text_of(web.get("/entries/?all=1&project=internal"))
    assert "Invoicing and admin" in by_project
    assert "Landing page layout" not in by_project

    by_client = text_of(web.get("/entries/?all=1&client=Acme+Corp"))
    assert "Landing page layout" in by_client
    assert "Invoicing and admin" not in by_client

    by_category = text_of(web.get("/entries/?all=1&category=project-management"))
    assert "Sprint planning" in by_category
    assert "Landing page layout" not in by_category

    by_range = text_of(web.get("/entries/?from=2026-08-01&to=2026-08-31"))
    assert "Cache layer" in by_range
    assert "Landing page layout" not in by_range


def test_entries_page_defaults_to_this_month(web, storage: Storage) -> None:
    today = date.today()
    web.post(
        "/entries/",
        {"project_id": "acme-web", "duration": "1h", "date": today.isoformat()},
    )
    assert today.isoformat() in text_of(web.get("/entries/"))


def test_adding_an_entry(web, storage: Storage) -> None:
    """FR-5."""
    response = web.post(
        "/entries/",
        {
            "project_id": "acme-web",
            "duration": "1h30m",
            "date": "2026-09-21",
            "start": "13:00",
            "category": "#Code Review",
            "note": "Pairing, with notes",
        },
    )
    assert response.status_code == 200

    entry = storage.load_entries(date(2026, 9, 21), date(2026, 9, 21))[0]
    assert entry.duration_minutes == 90
    assert (entry.start.hour, entry.end.hour) == (13, 14)
    assert entry.category == "code-review"
    assert entry.note == "Pairing, with notes"
    assert "code-review" in storage.get_project("acme-web").categories


def test_editing_an_entry(web, storage: Storage) -> None:
    """FR-7."""
    web.post(
        "/entries/a3f9c1",
        {
            "project_id": "acme-web",
            "duration": "2h",
            "date": "2026-09-18",
            "category": "software-coding",
            "note": "Landing page, second pass",
        },
    )
    entry = storage.find_entry("a3f9c1")
    assert entry is not None
    assert entry.duration_minutes == 120
    assert entry.note == "Landing page, second pass"


def test_the_edit_form_is_filled_in(web) -> None:
    html = text_of(web.get("/entries/a3f9c1/edit"))
    assert 'value="1h30m"' in html
    assert 'value="2026-09-18"' in html
    assert 'value="Landing page layout"' in html
    assert 'value="software-coding"' in html


def test_deleting_an_entry(web, storage: Storage) -> None:
    """FR-7."""
    web.post("/entries/c48d7e/delete")
    assert storage.find_entry("c48d7e") is None


def test_an_unknown_entry_is_a_404(web) -> None:
    assert web.raw.get("/entries/ffffff/edit").status_code == 404
    assert web.post("/entries/ffffff/delete").status_code == 404


def test_a_bad_duration_comes_back_as_a_message(web) -> None:
    """FR-25: no traceback in the browser either."""
    response = web.post(
        "/entries/",
        {"project_id": "acme-web", "duration": "bananas", "date": "2026-09-21"},
    )
    html = text_of(response)
    assert response.status_code == 200
    assert "Cannot read" in html
    assert "90m, 1h30m" in html
    assert "Traceback" not in html


def test_an_archived_project_is_refused_then_forced(web, storage: Storage) -> None:
    """FR-10."""
    refused = web.post(
        "/entries/", {"project_id": "old-site", "duration": "1h", "date": "2026-09-21"}
    )
    assert "archived" in text_of(refused)

    web.post(
        "/entries/",
        {"project_id": "old-site", "duration": "1h", "date": "2026-09-21", "force": "1"},
    )
    assert storage.load_entries(project_id="old-site")


def test_the_entry_form_offers_the_projects_categories(web) -> None:
    """FR-50: an autocomplete per project, so the list follows the selection."""
    html = text_of(web.get("/entries/new"))

    assert 'id="categories-acme-web"' in html
    assert 'id="categories-internal"' in html
    assert "data-project-select" in html
    assert "data-category-input" in html
    # The acme list is ranked, most recently used first (FR-46).
    acme = html.split('id="categories-acme-web"')[1].split("</datalist>")[0]
    assert acme.index("software-coding") < acme.index("testing")


def test_archived_projects_are_not_offered_in_the_picker(web) -> None:
    """FR-13."""
    html = text_of(web.get("/entries/new"))
    assert 'value="acme-web"' in html
    assert 'value="old-site"' not in html


def test_editing_an_old_entry_keeps_its_archived_project_in_the_list(web, storage) -> None:
    """Otherwise saving would silently move the entry somewhere else."""
    entry = storage.load_all_entries()[0]
    storage.update_entry(entry.model_copy(update={"project_id": "old-site"}))

    html = text_of(web.get(f"/entries/{entry.id}/edit"))
    assert 'value="old-site"' in html
    assert "(archived)" in html


# ---------------------------------------------------------------- projects


def test_projects_page_lists_the_active_ones(web) -> None:
    """FR-33, FR-13."""
    html = text_of(web.get("/projects/"))
    assert "Acme website" in html
    assert "Old brochure site" not in html
    assert "Show archived (1)" in html

    everything = text_of(web.get("/projects/?all=1"))
    assert "Old brochure site" in everything


def test_projects_page_shows_rate_budget_and_logged(web) -> None:
    row = row_for(text_of(web.get("/projects/")), "Acme website")
    assert "105.00" in row  # the rate valid today
    assert "120" in row  # the budget
    assert "4h25m" in row  # everything logged


def test_creating_a_project(web, storage: Storage) -> None:
    """FR-11."""
    web.post(
        "/projects/",
        {
            "id": "beta-app",
            "name": "Beta app",
            "client": "Beta AS",
            "rate": "110.50",
            "rate_from": "2026-09-01",
            "budget_hours": "40",
        },
    )
    project = storage.get_project("beta-app")
    assert project.name == "Beta app"
    assert project.rates[0].rate == Decimal("110.50")
    assert project.budget_hours == Decimal("40")


def test_creating_a_project_with_a_taken_id(web) -> None:
    """FR-12."""
    response = web.post("/projects/", {"id": "acme-web", "name": "Clash"})
    assert "already exists" in text_of(response)


def test_project_detail_shows_rates_categories_and_budget(web) -> None:
    """FR-33."""
    html = text_of(web.get("/projects/acme-web"))

    assert "from 2026-01-01" in html and "95.00" in html
    assert "from 2026-07-01" in html and "105.00" in html
    assert "#software-coding" in html
    assert "4h25m of 120h" in html
    assert "meter-ok" in html


def test_editing_a_project(web, storage: Storage) -> None:
    web.post("/projects/acme-web", {"name": "Acme site", "client": "Acme AS"})
    project = storage.get_project("acme-web")
    assert project.name == "Acme site"
    assert project.client == "Acme AS"


def test_adding_a_rate(web, storage: Storage) -> None:
    """FR-14."""
    web.post("/projects/acme-web/rate", {"rate": "120", "valid_from": "2027-01-01"})
    rates = storage.get_project("acme-web").rates
    assert rates[-1].rate == Decimal("120")
    assert rates[-1].valid_from == date(2027, 1, 1)


def test_archiving_and_unarchiving(web, storage: Storage) -> None:
    """FR-13."""
    web.post("/projects/internal/archive")
    assert storage.get_project("internal").status is ProjectStatus.ARCHIVED
    assert storage.load_entries(project_id="internal")  # entries stay

    web.post("/projects/internal/archive", {"undo": "1"})
    assert storage.get_project("internal").status is ProjectStatus.ACTIVE


def test_a_project_with_entries_cannot_be_deleted(web, storage: Storage) -> None:
    """FR-16: the button is not even offered."""
    html = text_of(web.get("/projects/acme-web"))
    assert 'action="/projects/acme-web/delete"' not in html

    response = web.post("/projects/acme-web/delete")
    assert "Archive it instead" in text_of(response)
    assert storage.get_project("acme-web")


def test_an_empty_project_can_be_deleted(web, storage: Storage) -> None:
    web.post("/projects/", {"id": "beta-app", "name": "Beta app"})
    assert 'action="/projects/beta-app/delete"' in text_of(web.get("/projects/beta-app"))

    web.post("/projects/beta-app/delete")
    assert "beta-app" not in {project.id for project in storage.load_projects()}


def test_registering_and_unregistering_a_category(web, storage: Storage) -> None:
    """FR-44, FR-55."""
    web.post("/projects/internal/categories", {"category": "Code Review"})
    assert "code-review" in storage.get_project("internal").categories

    web.post("/projects/internal/categories/code-review/delete")
    assert "code-review" not in storage.get_project("internal").categories


def test_an_unknown_project_is_an_error_page(web) -> None:
    response = web.raw.get("/projects/ghost")
    assert response.status_code == 400
    assert "Unknown project" in text_of(response)
    assert "Traceback" not in text_of(response)


# ----------------------------------------------------------------- reports


def test_reports_week(web) -> None:
    """FR-34, FR-17."""
    html = text_of(web.get("/reports/?view=week&from=2026-09-14&to=2026-09-20"))
    assert "3h40m" in html
    assert "By project" in html and "By day" in html
    assert "Acme website" in row_for(html, "Acme website")


def test_reports_month(web) -> None:
    """FR-34, FR-18."""
    html = text_of(web.get("/reports/?view=month&from=2026-09-01&to=2026-09-30"))
    assert "By client" in html
    assert "By week" in html
    assert "IceCube Solutions" in html


def test_reports_project_shows_the_budget(web) -> None:
    """FR-34, FR-19, FR-22."""
    html = text_of(web.get("/reports/?view=project&project=acme-web"))
    assert "4h25m" in html
    assert "of 120h" in html
    assert "By category" in html


def test_a_report_period_does_not_shrink_the_project_total(web) -> None:
    """FR-19: the same rule the CLI follows."""
    html = text_of(web.get("/reports/?view=project&project=acme-web&from=2026-09-19&to=2026-09-19"))
    assert "4h25m" in html  # the whole history
    assert "1h25m" in html  # the selected day
    assert "4h25m of 120h" in html  # the budget is about the project


def test_reports_client(web) -> None:
    """FR-34, FR-20."""
    html = text_of(web.get("/reports/?view=client&client=Acme+Corp"))
    assert "Acme Corp" in html
    assert "2 projects" in html


def test_reports_category(web) -> None:
    """FR-34, FR-61."""
    html = text_of(web.get("/reports/?view=category&category=software-coding"))
    assert "#software-coding" in html
    assert "3h45m" in html


def test_reports_unrated_time_is_flagged(web) -> None:
    """FR-15."""
    html = text_of(web.get("/reports/?view=month&from=2026-09-01&to=2026-09-30"))
    assert "Unrated" in html
    assert "45m" in row_for(html, "Internal work")


def test_an_unknown_report_view_falls_back_to_the_week(web) -> None:
    """Which view rendered, not what was in it: this week is often empty."""
    html = text_of(web.get("/reports/?view=nonsense"))

    assert active_tab(html) == "Week"
    assert "Week " in html  # the period header the week view always draws


# ------------------------------------------------------------------- theme


def test_the_theme_comes_from_the_config(web, storage: Storage) -> None:
    """FR-62."""
    assert 'data-theme="dark"' in text_of(web.get("/"))

    config = storage.load_config()
    storage.save_config(config.model_copy(update={"theme": "light"}))
    assert 'data-theme="light"' in text_of(web.get("/"))


def test_the_toggle_writes_the_theme_to_the_config(web, storage: Storage) -> None:
    """FR-62: a setting, so the CLI and the next session agree."""
    web.post("/settings/theme", {"theme": "light"})
    assert storage.load_config().theme == "light"

    web.post("/settings/theme", {"theme": "dark"})
    assert storage.load_config().theme == "dark"


def test_the_toggle_keeps_the_comments_in_the_config(web, storage: Storage) -> None:
    web.post("/settings/theme", {"theme": "light"})
    assert "# Cubit configuration" in storage.config_path.read_text(encoding="utf-8")


def test_an_unknown_theme_is_refused(web, storage: Storage) -> None:
    response = web.post("/settings/theme", {"theme": "neon"})
    assert "Unknown theme" in text_of(response)
    assert storage.load_config().theme == "dark"


def test_every_page_carries_the_navigation(web) -> None:
    """FR-56: logo on the left, navigation on the right."""
    for path in ["/", "/entries/", "/projects/", "/reports/"]:
        html = text_of(web.get(path))
        assert "cubit-mark.svg" in html
        for item in ["Dashboard", "Entries", "Projects", "Reports"]:
            assert f">{item}</a>" in html


def test_the_active_page_is_marked_in_the_navigation(web) -> None:
    html = text_of(web.get("/projects/"))
    active = [line for line in html.splitlines() if "is-active" in line]
    assert any("Projects" in line for line in active)


# ------------------------------------------------------------------ export


def test_the_reports_page_offers_both_downloads(web) -> None:
    """FR-23."""
    html = text_of(web.get("/reports/?view=month"))
    assert "/reports/export?" in html
    assert "format=csv" in html
    assert "format=markdown" in html


def test_a_download_carries_the_filters_of_the_page(web) -> None:
    """The link keeps the query string, so the file matches what is on screen."""
    html = text_of(web.get("/reports/?view=month&from=2026-09-01&to=2026-09-30"))
    link = html.split('href="')[1:]
    export = next(part for part in link if part.startswith("/reports/export"))
    assert "from=2026-09-01" in export
    assert "to=2026-09-30" in export


def test_downloading_a_month_as_csv(web) -> None:
    response = web.get("/reports/export?view=month&from=2026-09-01&to=2026-09-30&format=csv")

    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert "attachment" in response.headers["Content-Disposition"]
    assert ".csv" in response.headers["Content-Disposition"]

    body = text_of(response)
    assert body.startswith("Custom range")
    assert "Acme website,2h55m" in body


def test_downloading_a_project_as_markdown(web) -> None:
    response = web.get("/reports/export?view=project&project=acme-web&format=markdown")

    assert response.mimetype == "text/markdown"
    assert "cubit-project-acme-website-acme-web.md" in response.headers["Content-Disposition"]
    body = text_of(response)
    assert body.startswith("# Acme website (acme-web)")
    assert "| Budget |" in body


def test_downloading_a_client_and_a_category(web) -> None:
    client = text_of(web.get("/reports/export?view=client&client=Acme+Corp&format=markdown"))
    assert client.startswith("# Acme Corp")

    category = text_of(web.get("/reports/export?view=category&category=software-coding&format=csv"))
    assert "software-coding" in category


def test_an_unknown_download_format_is_refused(web) -> None:
    response = web.raw.get("/reports/export?view=month&format=pdf")
    assert response.status_code == 400
    assert "csv, markdown" in text_of(response)


def test_downloading_a_category_nobody_picked(web) -> None:
    response = web.raw.get("/reports/export?view=category&format=csv")
    assert response.status_code == 400
    assert "nothing to export" in text_of(response)


def test_a_download_needs_no_token(web) -> None:
    """It is a GET: reading is never blocked by the CSRF guard."""
    assert web.raw.get("/reports/export?view=week&format=csv").status_code == 200


# ------------------------------------------------------ 24-hour times


def test_the_start_field_is_a_24_hour_text_box(web) -> None:
    """A browser draws <input type="time"> in its own locale, am/pm and all."""
    html = text_of(web.get("/entries/new"))
    field = next(line for line in html.splitlines() if 'id="start"' in line)

    assert 'type="time"' not in field
    assert 'placeholder="09:05"' in html
    assert "24-hour" in html


def test_an_afternoon_time_round_trips(web, storage: Storage) -> None:
    """13:00 stays 13:00, and the end is worked out from it."""
    web.post(
        "/entries/",
        {
            "project_id": "acme-web",
            "duration": "1h30m",
            "date": "2026-09-21",
            "start": "13:00",
        },
    )
    entry = storage.load_entries(date(2026, 9, 21), date(2026, 9, 21))[0]

    assert (entry.start.hour, entry.start.minute) == (13, 0)
    assert (entry.end.hour, entry.end.minute) == (14, 30)
    assert "13:00" in text_of(web.get(f"/entries/{entry.id}/edit"))


def test_a_single_digit_hour_is_accepted(web, storage: Storage) -> None:
    """A text field invites 9:05, so it must not be an error."""
    web.post(
        "/entries/",
        {"project_id": "acme-web", "duration": "1h", "date": "2026-09-22", "start": "9:05"},
    )
    entry = storage.load_entries(date(2026, 9, 22), date(2026, 9, 22))[0]
    assert (entry.start.hour, entry.start.minute) == (9, 5)


def test_a_twelve_hour_time_is_refused_with_a_message(web) -> None:
    response = web.post(
        "/entries/",
        {"project_id": "acme-web", "duration": "1h", "date": "2026-09-21", "start": "1:30 PM"},
    )
    body = text_of(response)
    assert "Cannot read" in body
    assert "24-hour" in body
    assert "Traceback" not in body


def test_times_are_shown_on_a_24_hour_clock(web, storage: Storage) -> None:
    """FR-3: the dashboard shows the timer's start, never as am/pm."""
    web.post("/timer/start", {"project_id": "acme-web"})
    html = text_of(web.get("/"))

    assert "started" in html
    assert " AM" not in html and " PM" not in html


def test_the_entry_table_shows_24_hour_times(web) -> None:
    html = text_of(web.get("/entries/?all=1"))
    assert "23:40" in html  # the entry that runs past midnight
    assert "PM" not in html
