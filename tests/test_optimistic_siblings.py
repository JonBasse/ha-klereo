"""A confirmed command must reach EVERY entity of that output, not just the one actuated.

@nopbop, 2026-09-08, v1.16.0: he starts the heat pump **from Home Assistant**, the pump
physically restarts, `Heating Mode` reads *Heating*, the thermostat reads *Heat 28 °C*, the
official v1 client agrees — and the `switch` stays `off` for ~10 minutes before coming back
on its own (Forgejo #174).

The ticket refused to build before measuring, because two readings predicted exactly that:

1. the payload is uniformly stale — the lag is LOCAL to this integration;
2. the payload is partially fresh, `mode` updated and `status` not — the lag is a fact about
   the box, and propagating optimism would HIDE it.

Reading 2 is refuted by the export of 2026-09-08: on `outs[4]`, `mode` and `status` are two
fields of ONE element carrying ONE `updateTime` (684), so they cannot have different
freshness. Verified in the file rather than taken on trust.

🔴 That refutation rests on ONE installation, so
`test_a_contrary_refresh_wins_over_the_optimistic_state` below is not decoration: the
optimism must be OVERWRITTEN by the next payload, never sticky. A sticky one would mask
reading 2 wherever it does turn out to be real, and this file would then be a green test
over an inert mechanism.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.exceptions import HomeAssistantError

from custom_components.klereo.api import (
    HEAT_MODE_STOP,
    OUT_IDX_HEATING,
    OUT_MODE_MAN,
    OUT_MODE_REGUL,
    OUT_STATE_OFF,
    OUT_STATE_ON,
    KlereoApi,
)
from custom_components.klereo.climate import KlereoClimate
from custom_components.klereo.coordinator import KlereoCoordinator
from custom_components.klereo.select import KlereoOutputModeSelect
from custom_components.klereo.switch import KlereoSwitch

SYS1 = "SYS1"
SYS2 = "SYS2"


def _out(index, status, mode, type_=0):
    return {"index": index, "status": status, "mode": mode, "type": type_}


@pytest.fixture
def payloads():
    """Mutable `GetPoolDetails` bodies, so a test can change what the box says.

    Output 0 runs under Manual, output 1 is stopped under Manual, output 4 is a stopped
    KlereoTherm. `HeaterMode: 2` is a real heat pump, so all four modes are offered.
    """
    settings = {"ConsigneEau": 28, "HeaterMode": 2}
    return {
        SYS1: {
            "probes": [],
            "outs": [
                _out(0, OUT_STATE_ON, OUT_MODE_MAN),
                _out(1, OUT_STATE_OFF, OUT_MODE_MAN),
                _out(OUT_IDX_HEATING, OUT_STATE_OFF, HEAT_MODE_STOP, 8),
            ],
            "RegulModes": dict(settings),
        },
        SYS2: {
            "probes": [],
            "outs": [_out(OUT_IDX_HEATING, OUT_STATE_OFF, HEAT_MODE_STOP, 8)],
            "RegulModes": dict(settings),
        },
    }


@pytest.fixture
def coordinator(payloads, monkeypatch):
    """A real coordinator over a mocked API, built the way the other suites build one."""
    monkeypatch.setattr("custom_components.klereo.coordinator.asyncio.sleep", AsyncMock())

    api = AsyncMock(spec=KlereoApi)
    api.get_systems.return_value = {
        "response": [{"idSystem": SYS1}, {"idSystem": SYS2}]
    }
    api.get_pool_details.side_effect = lambda sid: {"response": [payloads[sid]]}
    api.set_output.return_value = {"status": "ok", "response": {"cmdID": 77}}
    api.command_status.return_value = {
        "status": "ok", "response": {"cmdID": 77, "status": 9, "detail": "Ok"}
    }

    coord = KlereoCoordinator.__new__(KlereoCoordinator)
    coord.api = api
    coord.hass = MagicMock()
    coord.logger = MagicMock()
    coord.name = "klereo"
    coord.update_interval = None
    coord._listeners = {}
    # `async_add_listener` bumps this counter; bypassing `__init__` leaves it unset.
    coord._last_listener_id = 0
    coord.data = {}
    coord.last_update_success = True
    coord.async_request_refresh = AsyncMock()
    return coord


async def _refresh(coordinator):
    """Publish a fresh poll, as `DataUpdateCoordinator.async_refresh` does.

    The two lines this stands in for are Home Assistant's, not ours; everything below them
    — the payload, the parsing, the models — is the real path.
    """
    coordinator.data = await coordinator._async_update_data()
    coordinator.async_update_listeners()


def _bind(coordinator, entity):
    """Subscribe an entity the way `async_added_to_hass` would, minus the hass plumbing."""
    entity.async_write_ha_state = MagicMock()
    coordinator.async_add_listener(entity._handle_coordinator_update)
    return entity


def _switch(coordinator, system_id, index):
    output = coordinator.data[system_id].details.output_index[index]
    return _bind(coordinator, KlereoSwitch(coordinator, system_id, output))


def _select(coordinator, system_id, index):
    output = coordinator.data[system_id].details.output_index[index]
    return _bind(coordinator, KlereoOutputModeSelect(coordinator, system_id, output))


class TestTheSiblingsOfACommandedOutputFollowIt:
    """The defect @nopbop measured, from each of the three entities that can command."""

    async def test_the_switch_follows_a_command_sent_from_the_select(self, coordinator):
        await _refresh(coordinator)
        switch = _switch(coordinator, SYS1, OUT_IDX_HEATING)
        select = _select(coordinator, SYS1, OUT_IDX_HEATING)
        assert switch.is_on is False

        await select.async_select_option("Heating")

        assert switch.is_on is True

    async def test_the_switch_follows_a_command_sent_from_the_thermostat(self, coordinator):
        await _refresh(coordinator)
        switch = _switch(coordinator, SYS1, OUT_IDX_HEATING)
        select = _select(coordinator, SYS1, OUT_IDX_HEATING)
        climate = KlereoClimate(coordinator, SYS1)

        await climate.async_set_hvac_mode(HVACMode.HEAT)

        assert switch.is_on is True
        assert select.current_option == "Heating"
        assert climate.hvac_mode is HVACMode.HEAT

    async def test_the_select_and_the_thermostat_follow_a_command_sent_from_the_switch(
        self, coordinator
    ):
        await _refresh(coordinator)
        switch = _switch(coordinator, SYS1, OUT_IDX_HEATING)
        select = _select(coordinator, SYS1, OUT_IDX_HEATING)
        climate = KlereoClimate(coordinator, SYS1)
        assert select.current_option == "Off"

        await switch.async_turn_on()

        assert select.current_option == "Heating"
        assert climate.hvac_mode is HVACMode.HEAT


class TestNegativeControls:
    """Two of them, and they do not guard the same thing."""

    async def test_commanding_one_output_leaves_its_neighbours_alone(self, coordinator):
        """No lateral spill: output 1 is stopped under Manual and must stay there."""
        await _refresh(coordinator)
        neighbour = _switch(coordinator, SYS1, 1)
        neighbour_select = _select(coordinator, SYS1, 1)
        select = _select(coordinator, SYS1, OUT_IDX_HEATING)

        await select.async_select_option("Heating")

        assert neighbour.is_on is False
        assert neighbour_select.current_option == "Manual"
        stored = coordinator.data[SYS1].details.output_index[1]
        assert (stored.status, stored.mode) == (OUT_STATE_OFF, OUT_MODE_MAN)

    async def test_commanding_one_system_leaves_the_other_alone(self, coordinator):
        """No spill across installations: SYS2 has an output 4 of its own."""
        await _refresh(coordinator)
        other = _switch(coordinator, SYS2, OUT_IDX_HEATING)
        select = _select(coordinator, SYS1, OUT_IDX_HEATING)

        await select.async_select_option("Heating")

        assert other.is_on is False
        stored = coordinator.data[SYS2].details.output_index[OUT_IDX_HEATING]
        assert (stored.status, stored.mode) == (OUT_STATE_OFF, HEAT_MODE_STOP)

    async def test_a_contrary_refresh_wins_over_the_optimistic_state(self, coordinator):
        """No stickiness — and this is the test that keeps reading 2 of #174 visible.

        The box keeps answering "stopped". Whatever we optimistically showed, the next
        payload must overwrite it: an optimism that survived a contradicting refresh would
        hide a real cloud-side lag instead of removing one.
        """
        await _refresh(coordinator)
        switch = _switch(coordinator, SYS1, OUT_IDX_HEATING)
        select = _select(coordinator, SYS1, OUT_IDX_HEATING)

        await select.async_select_option("Heating")
        # Positive control: without this the test would pass on an integration that never
        # writes any optimism at all.
        assert switch.is_on is True

        await _refresh(coordinator)

        assert switch.is_on is False
        assert select.current_option == "Off"

    async def test_an_unconfirmed_command_is_never_shown(self, coordinator):
        """A verdict, not a hope. The ceiling of the confirmation poll is not success (#140).

        Painting a command across three entities on "we could not tell" would restore the
        exact silence #95 removed: a status 13 reading identically to a status 9.
        """
        coordinator.api.command_status.return_value = {
            "status": "ok", "response": {"cmdID": 77, "status": 1}
        }
        await _refresh(coordinator)
        switch = _switch(coordinator, SYS1, OUT_IDX_HEATING)
        select = _select(coordinator, SYS1, OUT_IDX_HEATING)

        await select.async_select_option("Heating")

        assert switch.is_on is False
        stored = coordinator.data[SYS1].details.output_index[OUT_IDX_HEATING]
        assert (stored.status, stored.mode) == (OUT_STATE_OFF, HEAT_MODE_STOP)


class TestARejectedCommandDoesNotStayOnScreen:
    """The actuated entity must stop showing a command the box refused (#181).

    `switch` and `select` write their own state BEFORE sending, for immediate feedback. A
    rejection raises, and Home Assistant does not repaint on that: its service handler
    re-reads only `should_poll` entities, and only after a call that returned. So the
    refused state stayed on screen until the next poll — ten minutes at the default — and
    the premise of the ticket, "the lie lasts one round trip", was false.

    The repair is the box's own answer, not a remembered previous state: a refresh after
    ANY write, whatever its outcome. `_async_update_data` rebuilds the models from the
    payload, so the next payload overwrites the optimism by construction — the property
    `test_a_contrary_refresh_wins_over_the_optimistic_state` already holds.
    """

    @pytest.fixture(autouse=True)
    def _rejecting_box(self, coordinator):
        """Status 13 — insufficient rights — and a refresh that really re-reads the box."""
        coordinator.api.command_status.return_value = {
            "status": "ok", "response": {"cmdID": 77, "status": 13, "detail": ""}
        }
        # An `async def`, not a lambda: AsyncMock awaits a coroutine FUNCTION, but returns
        # the coroutine a lambda produces without running it — a refresh that never happens.
        async def _really_refresh():
            await _refresh(coordinator)

        coordinator.async_request_refresh = AsyncMock(side_effect=_really_refresh)

    async def test_the_switch_returns_to_what_the_box_says(self, coordinator):
        await _refresh(coordinator)
        switch = _switch(coordinator, SYS1, 1)
        assert switch.is_on is False

        with pytest.raises(HomeAssistantError, match="rejected"):
            await switch.async_turn_on()

        assert switch.is_on is False

    async def test_the_select_returns_to_what_the_box_says(self, coordinator):
        await _refresh(coordinator)
        select = _select(coordinator, SYS1, OUT_IDX_HEATING)
        assert select.current_option == "Off"

        with pytest.raises(HomeAssistantError, match="rejected"):
            await select.async_select_option("Heating")

        assert select.current_option == "Off"

    async def test_an_accepted_command_keeps_its_optimism(self, coordinator):
        """Negative control: the refresh must not undo a command the box ACCEPTED.

        Here the box answers 9 and the next payload says "on", as it would after a real
        start. Without this, "always show the payload" would pass the two tests above by
        flashing every accepted command back to its old state.
        """
        coordinator.api.command_status.return_value = {
            "status": "ok", "response": {"cmdID": 77, "status": 9, "detail": "Ok"}
        }
        await _refresh(coordinator)
        switch = _switch(coordinator, SYS1, 1)
        coordinator.api.get_pool_details.side_effect = lambda sid: {
            "response": [{**_payload_with_output_on(coordinator, sid, 1)}]
        }

        await switch.async_turn_on()

        assert switch.is_on is True


def _payload_with_output_on(coordinator, system_id, index):
    """The raw payload the box would return once output `index` runs under Manual."""
    raw = dict(coordinator.data[system_id].details.raw)
    raw["outs"] = [
        {**out, "status": OUT_STATE_ON, "mode": OUT_MODE_MAN} if out["index"] == index else out
        for out in raw["outs"]
    ]
    return raw


class TestAutoIsNotARelayReading:
    """`newState` states something about the relay only under Manual.

    Every other mode sends AUTO, which means "the box decides". @nopbop's export of
    2026-09-08 shows `outs[1]` in mode 3 (Regulation) reporting `status: 1` — a running
    relay under automatic control — so echoing the commanded AUTO into `status` would turn
    a switch that correctly reads ON into `off`. That is the same class of invention as
    #105: a specific, plausible, wrong answer where the honest one is "we did not ask".
    """

    async def test_handing_control_to_the_box_moves_the_mode_and_not_the_relay(
        self, coordinator
    ):
        await _refresh(coordinator)
        switch = _switch(coordinator, SYS1, 0)
        select = _select(coordinator, SYS1, 0)
        assert switch.is_on is True

        await select.async_select_option("Regulation")

        assert select.current_option == "Regulation"
        assert switch.is_on is True
        stored = coordinator.data[SYS1].details.output_index[0]
        assert (stored.mode, stored.status) == (OUT_MODE_REGUL, OUT_STATE_ON)

    async def test_manual_still_states_the_relay(self, coordinator):
        """Positive control: the exclusion is on AUTO, not on writing `status` at all.

        Without it, "never write `status`" would pass the test above and leave the switch
        exactly as late as before on the Manual writes that DO state a relay.
        """
        await _refresh(coordinator)
        switch = _switch(coordinator, SYS1, 1)
        select = _select(coordinator, SYS1, 1)
        assert switch.is_on is False

        await switch.async_turn_on()

        assert select.current_option == "Manual"
        stored = coordinator.data[SYS1].details.output_index[1]
        assert (stored.mode, stored.status) == (OUT_MODE_MAN, OUT_STATE_ON)
