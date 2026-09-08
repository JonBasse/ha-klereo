"""Tests for the manual refresh button.

Forgejo #164, asked for by @StephanH27 on GitHub #61.

The ticket was refused once, on the reasoning that a button calling
`async_request_refresh()` would be an inert mechanism imitating a synchronisation the web
interface performs for real. A network capture retired that: clicking the button in the v1
and v3 web interfaces emits **one** `POST GetPoolDetails.php` and nothing else. The web
button re-reads; it pushes nothing. So the two gestures coincide and a local refresh is a
faithful implementation, not a substitute.

What survives from the refusal is the naming rule, and one hard constraint: #139 put a
10-minute floor under the polling interval because Klereo refreshes server-side every ten
minutes and threatens to ban faster callers — a cost that lands on the **user's** account.
A button anybody can press twenty times a minute undoes that floor by the back door, so
the button carries the same floor between two of its own refreshes.
"""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import Platform
from homeassistant.exceptions import HomeAssistantError

from custom_components.klereo import PLATFORMS
from custom_components.klereo import coordinator as coordinator_module
from custom_components.klereo.button import KlereoRefreshButton, _extract_buttons
from custom_components.klereo.const import BUTTON_REFRESH_MIN_MINUTES, SCAN_INTERVAL_MIN_MINUTES
from custom_components.klereo.coordinator import KlereoCoordinator
from custom_components.klereo.models import (
    KlereoPoolDetails,
    KlereoSystemData,
    KlereoSystemInfo,
)

from .conftest import MOCK_SYSTEM_ID

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def fake_clock(monkeypatch):
    """Drive the coordinator's rate limiter from the test instead of from real time.

    The guard reads a MONOTONIC clock, so it cannot be steered by `freezegun` or by a
    system clock change — which is the point of using one. Replacing the name the module
    imported keeps the substitution local to this module rather than mutating `time`.
    """
    now = {"t": 1000.0}

    monkeypatch.setattr(coordinator_module, "monotonic", lambda: now["t"])

    def advance(seconds: float) -> None:
        now["t"] += seconds

    return advance


@pytest.fixture
def coordinator(mock_api):
    """A real `KlereoCoordinator` whose refresh actually re-reads the mock API.

    `__init__` is bypassed the way every other coordinator test in this repo bypasses it —
    Home Assistant's base needs a live event loop. `async_request_refresh` is Home
    Assistant's own debounced method and needs `hass`; standing in for it with a call to
    our real `_async_update_data` keeps the assertions on what actually reaches the API,
    which is the only thing #139 cares about.
    """
    coord = KlereoCoordinator.__new__(KlereoCoordinator)
    coord.api = mock_api
    coord.last_update_success = True
    coord.data = {}
    coord._last_manual_refresh = None

    async def _request_refresh():
        coord.data = await coord._async_update_data()

    coord.async_request_refresh = _request_refresh
    return coord


@pytest.fixture
def button(coordinator):
    """The refresh button of the one system the mock API reports."""
    return KlereoRefreshButton(coordinator, MOCK_SYSTEM_ID)


class TestPressingTheButtonRereadsKlereo:
    """The positive control: the press has to reach the API, or it is decoration."""

    async def test_pressing_it_fetches_the_pool_details_again(self, button, mock_api, fake_clock):
        assert mock_api.get_pool_details.await_count == 0

        await button.async_press()

        assert mock_api.get_pool_details.await_count == 1

    async def test_pressing_it_refreshes_the_coordinator_data(self, button, coordinator, fake_clock):
        """Asserted on the data the coordinator ends up holding, not on a call count."""
        await button.async_press()

        assert MOCK_SYSTEM_ID in coordinator.data
        assert isinstance(coordinator.data[MOCK_SYSTEM_ID], KlereoSystemData)


class TestTheButtonWritesNothing:
    """It is a READ button, and that is asserted on the absence of a write.

    Asserting it on the resulting state instead would let a silent write through: a
    `SetOut` that queues, answers status 9 and changes the payload back to what it was
    reads exactly like a refresh from the outside.
    """

    async def test_it_sends_no_set_output_command(self, button, mock_api, fake_clock):
        await button.async_press()

        mock_api.set_output.assert_not_called()

    async def test_it_sends_no_set_param_command(self, button, mock_api, fake_clock):
        await button.async_press()

        mock_api.set_param.assert_not_called()

    async def test_it_writes_nothing_when_pressed_repeatedly(self, button, mock_api, fake_clock):
        """Including on the refused presses — a refusal must not fall back to a write."""
        await button.async_press()
        for _ in range(5):
            with pytest.raises(HomeAssistantError):
                await button.async_press()

        mock_api.set_output.assert_not_called()
        mock_api.set_param.assert_not_called()


class TestTheButtonCannotOutpaceThePollingFloor:
    """#139 put the floor under the polling interval; the button must not step over it.

    The rule is that a button can add at most ONE read per floor period on top of the
    polling it already permits — never a bar on the first press, which would make the
    entity inert, and never an unbounded rate.
    """

    async def test_a_second_press_inside_the_floor_is_refused(self, button, fake_clock):
        await button.async_press()
        fake_clock(BUTTON_REFRESH_MIN_MINUTES * 60 - 1)

        with pytest.raises(HomeAssistantError):
            await button.async_press()

    async def test_a_refused_press_costs_no_api_call(self, button, mock_api, fake_clock):
        """The refusal is the whole point: a raise that still called Klereo would be theatre."""
        await button.async_press()
        fake_clock(60)

        with pytest.raises(HomeAssistantError):
            await button.async_press()

        assert mock_api.get_pool_details.await_count == 1

    async def test_hammering_it_costs_exactly_one_api_call(self, button, mock_api, fake_clock):
        for _ in range(20):
            fake_clock(3)
            try:
                await button.async_press()
            except HomeAssistantError:
                pass

        assert mock_api.get_pool_details.await_count == 1

    async def test_a_press_after_the_floor_has_elapsed_is_served(self, button, mock_api, fake_clock):
        """Positive control against over-correction: the guard delays, it does not disable."""
        await button.async_press()
        fake_clock(BUTTON_REFRESH_MIN_MINUTES * 60)

        await button.async_press()

        assert mock_api.get_pool_details.await_count == 2

    async def test_the_very_first_press_is_never_refused(self, button, mock_api, fake_clock):
        """A guard that bars a cold entity is the inert mechanism of #115 in a new shape."""
        await button.async_press()

        assert mock_api.get_pool_details.await_count == 1

    async def test_the_refusal_tells_the_user_when_to_come_back(self, button, fake_clock):
        await button.async_press()
        fake_clock(60)

        with pytest.raises(HomeAssistantError) as refusal:
            await button.async_press()

        assert "minute" in str(refusal.value)

    def test_the_button_floor_is_the_polling_floor(self):
        """They are the same measured constraint, so they must not drift apart."""
        assert BUTTON_REFRESH_MIN_MINUTES == SCAN_INTERVAL_MIN_MINUTES


class TestTheEntitySaysWhatItDoes:
    """The naming rule the refused version of the ticket left standing.

    Nothing may suggest a dialogue with the box at the poolside: the button re-reads
    Klereo's cloud, exactly like the web interface's own button.
    """

    def test_its_name_names_klereo_as_the_source(self, button):
        assert button._attr_name == "Refresh from Klereo"

    def test_its_unique_id_is_per_system(self, coordinator):
        first = KlereoRefreshButton(coordinator, "SYS1")
        second = KlereoRefreshButton(coordinator, "SYS2")

        assert first._attr_unique_id != second._attr_unique_id

    def test_it_is_unavailable_once_its_system_leaves_the_payload(self, button, coordinator):
        coordinator.data = {}

        assert button.available is False

    def test_it_is_available_while_its_system_is_reported(self, button, coordinator):
        coordinator.data = {
            MOCK_SYSTEM_ID: KlereoSystemData(
                info=KlereoSystemInfo(id_system=MOCK_SYSTEM_ID, pool_nickname="My Pool"),
                details=KlereoPoolDetails(
                    probes=[], outs=[], regul_modes={}, probe_index={}, output_index={}
                ),
            )
        }

        assert button.available is True


class TestOneButtonPerSystem:
    """Discovery follows the shape the six other platforms use, so a pool that appears
    later gets its button without a restart."""

    def test_a_reported_system_gets_exactly_one_button(self, coordinator):
        details = KlereoPoolDetails(
            probes=[], outs=[], regul_modes={}, probe_index={}, output_index={}
        )

        items = _extract_buttons(coordinator, "SYS1", details)

        assert len(items) == 1

    def test_two_systems_yield_two_distinct_entities(self, coordinator):
        details = KlereoPoolDetails(
            probes=[], outs=[], regul_modes={}, probe_index={}, output_index={}
        )

        [(first_uid, _)] = _extract_buttons(coordinator, "SYS1", details)
        [(second_uid, _)] = _extract_buttons(coordinator, "SYS2", details)

        assert first_uid != second_uid


class TestThePlatformIsForwardedAtSetup:
    """A `button.py` nobody forwards creates no entity at all — the failure this catches."""

    def test_button_is_in_the_forwarded_platforms(self):
        assert Platform.BUTTON in PLATFORMS


class TestTheGuardLivesInTheCoordinator:
    """Platform modules command through coordinator methods, never through `coordinator.api`.

    A second button — or a service — reaching the API around the guard would restore the
    hammering the floor exists to prevent, so the floor is enforced where the writes are.
    """

    async def test_the_button_does_not_touch_the_api_itself(self, mock_api):
        recording_coordinator = MagicMock()
        recording_coordinator.async_manual_refresh = AsyncMock()
        recording_coordinator.api = mock_api

        entity = KlereoRefreshButton(recording_coordinator, MOCK_SYSTEM_ID)
        await entity.async_press()

        mock_api.get_pool_details.assert_not_called()
        recording_coordinator.async_manual_refresh.assert_awaited_once()


class TestTheDocumentationExplainsTheLimit:
    """A user whose second press is refused has to be able to find out why.

    Same reasoning as `test_scan_interval.py`: the places that must agree are checked, not
    trusted. An undocumented refusal reads as a bug and invites someone to "fix" it by
    removing the guard — which is how #139 would be undone a second time.
    """

    def test_the_readme_documents_the_button(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

        assert "Refresh from Klereo" in readme

    def test_the_readme_states_why_the_button_is_rate_limited(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

        assert f"once every {BUTTON_REFRESH_MIN_MINUTES} minutes" in readme
