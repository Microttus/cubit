"""FR-45, FR-52 and FR-53: what cubit asks before it registers a category.

The runner is never a real terminal, so the tests turn the interactive check
on deliberately and feed the answers in.
"""

from __future__ import annotations

import pytest

from cubit.cli import prompts
from cubit.cli.exit_codes import EXIT_OK
from cubit.core import Storage


@pytest.fixture
def at_a_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend there is someone to ask."""
    monkeypatch.setattr(prompts, "interactive", lambda: True)


def test_a_new_category_asks_before_it_is_registered(
    cli, storage: Storage, at_a_terminal: None
) -> None:
    """FR-45."""
    result = cli("add", "acme-web", "1h", "--date", "2026-09-21", "-c", "invoicing", input="y\n")

    assert result.exit_code == EXIT_OK
    assert "is new to acme-web" in result.stdout
    assert "invoicing" in storage.get_project("acme-web").categories


def test_declining_leaves_the_entry_uncategorized(
    cli, storage: Storage, at_a_terminal: None
) -> None:
    """FR-45: saying no must not quietly register it anyway."""
    result = cli("add", "acme-web", "1h", "--date", "2026-09-21", "-c", "invoicing", input="n\n")

    assert result.exit_code == EXIT_OK
    assert "invoicing" not in storage.get_project("acme-web").categories
    entry = storage.load_entries()[-1]
    assert entry.category is None


def test_a_registered_category_asks_nothing(cli, storage: Storage, at_a_terminal: None) -> None:
    """FR-45: the common case is silent."""
    result = cli("add", "acme-web", "1h", "--date", "2026-09-21", "-c", "software-coding", input="")
    assert result.exit_code == EXIT_OK
    assert "is new to" not in result.stdout


def test_a_near_miss_asks_did_you_mean(cli, storage: Storage, at_a_terminal: None) -> None:
    """FR-52."""
    result = cli(
        "add", "acme-web", "1h", "--date", "2026-09-21", "-c", "software-codng", input="y\n"
    )

    assert "Did you mean #software-coding?" in result.stdout
    assert "software-codng" not in storage.get_project("acme-web").categories
    assert storage.load_entries()[-1].category == "software-coding"


def test_declining_the_near_miss_still_offers_the_new_name(
    cli, storage: Storage, at_a_terminal: None
) -> None:
    """FR-52 then FR-45: no, it really is a new category."""
    result = cli(
        "add", "acme-web", "1h", "--date", "2026-09-21", "-c", "software-codng", input="n\ny\n"
    )

    assert "Did you mean" in result.stdout
    assert "is new to acme-web" in result.stdout
    assert "software-codng" in storage.get_project("acme-web").categories


def test_without_a_category_the_suggestions_are_offered(
    cli, storage: Storage, at_a_terminal: None
) -> None:
    """FR-53: a numbered list, most recently used first."""
    result = cli("add", "acme-web", "1h", "--date", "2026-09-21", input="1\n")

    assert "Categories for acme-web:" in result.stdout
    assert "1  #software-coding" in result.stdout
    assert storage.load_entries()[-1].category == "software-coding"


def test_enter_skips_the_suggestions(cli, storage: Storage, at_a_terminal: None) -> None:
    """FR-53: Enter skips."""
    result = cli("add", "acme-web", "1h", "--date", "2026-09-21", input="\n")

    assert result.exit_code == EXIT_OK
    assert storage.load_entries()[-1].category is None


def test_a_name_typed_at_the_suggestions_goes_through_confirmation(
    cli, storage: Storage, at_a_terminal: None
) -> None:
    """FR-53 into FR-45."""
    result = cli("add", "acme-web", "1h", "--date", "2026-09-21", input="invoicing\ny\n")

    assert "is new to acme-web" in result.stdout
    assert storage.load_entries()[-1].category == "invoicing"


def test_the_config_can_turn_the_suggestions_off(
    cli, storage: Storage, at_a_terminal: None
) -> None:
    """FR-53: prompt_for_category in config.yaml."""
    config = storage.load_config()
    storage.save_config(config.model_copy(update={"prompt_for_category": False}))

    result = cli("add", "acme-web", "1h", "--date", "2026-09-21")

    assert result.exit_code == EXIT_OK
    assert "Categories for" not in result.stdout
    assert storage.load_entries()[-1].category is None


def test_yes_skips_every_prompt(cli, storage: Storage, at_a_terminal: None) -> None:
    result = cli("add", "acme-web", "1h", "--date", "2026-09-21", "-c", "invoicing", "--yes")

    assert result.exit_code == EXIT_OK
    assert "is new to" not in result.stdout
    assert "invoicing" in storage.get_project("acme-web").categories


def test_nothing_is_asked_when_there_is_no_terminal(cli, storage: Storage) -> None:
    """A piped or scripted run must never block waiting for an answer."""
    result = cli("add", "acme-web", "1h", "--date", "2026-09-21", "-c", "invoicing")

    assert result.exit_code == EXIT_OK
    assert "is new to" not in result.stdout
    assert "invoicing" in storage.get_project("acme-web").categories


def test_start_offers_the_same_prompts(cli, storage: Storage, at_a_terminal: None) -> None:
    """FR-53 covers start as well as add."""
    result = cli("start", "acme-web", input="2\n")

    assert result.exit_code == EXIT_OK
    assert "Categories for acme-web:" in result.stdout
    state = storage.read_timer()
    assert state is not None
    assert state.category == "project-management"
