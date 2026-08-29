"""Tests for the polling cadence floor.

Klereo's own API documentation says the server refreshes every 10 minutes and that polling
faster risks a ban — a cost that lands on the **user's** Klereo account, not on us, and that
buys nothing: above one call per 10 minutes the server returns the same payload.

Forgejo #139. Reported by @nopbop on GitHub #58, 2026-08-28.
"""
import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import voluptuous as vol
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.klereo.api import KlereoApi
from custom_components.klereo.config_flow import options_schema
from custom_components.klereo.const import SCAN_INTERVAL_MIN_MINUTES, SCAN_INTERVAL_MINUTES
from custom_components.klereo.coordinator import KlereoCoordinator

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def mock_hass():
    """Create a mock HomeAssistant instance."""
    hass = MagicMock()
    hass.loop = None
    return hass


@pytest.fixture
def mock_api():
    """Create a mock API."""
    return AsyncMock(spec=KlereoApi)


@pytest.fixture
def interval_passed_to_home_assistant(mock_hass, mock_api, monkeypatch):
    """Return the `update_interval` KlereoCoordinator hands to its Home Assistant base.

    ⚠️ Home Assistant's `DataUpdateCoordinator.__init__` needs a live event loop (it reports
    a deprecation through the frame helper), which no test in this repo has — every other
    fixture bypasses `__init__` via `__new__` for that reason. Stubbing that one base call is
    the unavoidable boundary; the value under assertion is still the one OUR `__init__`
    computes, so the test fails if the clamp is wrong or missing.
    """
    captured = {}

    def fake_init(self, hass, logger, *, name, update_interval, **kwargs):
        captured["update_interval"] = update_interval

    monkeypatch.setattr(DataUpdateCoordinator, "__init__", fake_init)

    def build(**kwargs):
        KlereoCoordinator(mock_hass, mock_api, **kwargs)
        return captured["update_interval"]

    return build


class TestTheCoordinatorHonoursTheFloor:
    """The floor has to bind on READ, not only on the options form.

    `scan_interval` is a persisted option: `__init__.py` serves whatever is stored, so an
    install configured before the floor existed keeps hammering the API after the fix, and
    nothing signals it — the form is only re-validated if the user happens to open it.
    """

    def test_the_default_interval_is_the_server_refresh_period(self, interval_passed_to_home_assistant):
        assert interval_passed_to_home_assistant() == timedelta(minutes=10)

    def test_a_persisted_interval_below_the_floor_is_raised_to_it(self, interval_passed_to_home_assistant):
        assert interval_passed_to_home_assistant(scan_interval=1) == timedelta(
            minutes=SCAN_INTERVAL_MIN_MINUTES
        )

    def test_an_interval_above_the_floor_is_left_alone(self, interval_passed_to_home_assistant):
        """Positive control.

        Without it, "clamped to 10" is indistinguishable from "everyone is forced to 10" —
        we bound from below, never from above.
        """
        assert interval_passed_to_home_assistant(scan_interval=30) == timedelta(minutes=30)


class TestTheOptionsFormRefusesFasterThanTheFloor:
    """The form is the second half: it must stop a NEW value below the floor being stored."""

    def test_an_interval_below_the_floor_is_refused(self):
        schema = options_schema(current=SCAN_INTERVAL_MINUTES)

        with pytest.raises(vol.Invalid):
            schema({"scan_interval": 1})

    def test_the_floor_itself_is_accepted(self):
        """Positive control: the refusal above is about the value, not about the schema."""
        schema = options_schema(current=SCAN_INTERVAL_MINUTES)

        assert schema({"scan_interval": SCAN_INTERVAL_MIN_MINUTES}) == {
            "scan_interval": SCAN_INTERVAL_MIN_MINUTES
        }

    def test_a_slower_interval_is_still_accepted(self):
        """Negative control against over-correction: we cap nobody at the floor."""
        schema = options_schema(current=SCAN_INTERVAL_MINUTES)

        assert schema({"scan_interval": 60}) == {"scan_interval": 60}


class TestTheDocumentationAgreesWithTheConstants:
    """A README that still advertises the old default invites someone to "fix" the regression.

    Same reasoning as `test_release_agreement.py`: the places that must agree are checked,
    not trusted.
    """

    def test_the_readme_does_not_advertise_the_retired_default(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

        assert "default 5" not in readme

    def test_the_readme_states_the_current_default(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

        assert f"default {SCAN_INTERVAL_MINUTES}" in readme

    def test_the_options_form_explains_why_the_floor_exists(self):
        """The label alone leaves the floor looking arbitrary, which is how it gets undone."""
        strings = json.loads(
            (REPO_ROOT / "custom_components/klereo/strings.json").read_text(encoding="utf-8")
        )

        description = strings["options"]["step"]["init"]["data_description"]["scan_interval"]

        assert "10 minutes" in description

    def test_the_english_translation_carries_the_same_explanation(self):
        translation = json.loads(
            (REPO_ROOT / "custom_components/klereo/translations/en.json").read_text(encoding="utf-8")
        )

        description = translation["options"]["step"]["init"]["data_description"]["scan_interval"]

        assert "10 minutes" in description
