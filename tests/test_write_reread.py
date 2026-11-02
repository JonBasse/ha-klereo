"""How often a write re-reads Klereo, through the real service call and the real timers (#214).

Every write ends in a coordinator refresh (#181), and a refresh is `GetIndex` plus
`GetPoolDetails`, on the user's account. Home Assistant's default debouncer spaces those by
ten seconds, against a floor of ten minutes everywhere else (#139).

These tests drive the real `DataUpdateCoordinator` and its real `Debouncer`, and advance
the clock instead of mocking `async_request_refresh`: that mock is what every older test
replaces, so none of them can see the spacing at all. They count `GetPoolDetails` calls.
"""
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.klereo.api import (
    HEAT_MODE_STOP,
    OUT_IDX_HEATING,
    OUT_STATE_OFF,
)
from custom_components.klereo.const import DOMAIN, WRITE_REREAD_COOLDOWN_SECONDS

SYS = "SYS1"
SELECT = "select.pool_heating_mode"
CLIMATE = "climate.pool_heating"
NUMBER = "number.pool_water_setpoint"
CONFIRMED = 9
INSUFFICIENT_RIGHTS = 13


class Box:
    """A KlereoTherm that applies what it accepts, and counts how often it is read."""

    def __init__(self):
        self.mode = HEAT_MODE_STOP
        self.status = OUT_STATE_OFF
        self.setpoint = 25
        self.verdict = CONFIRMED
        self.api = AsyncMock()
        self.api.get_systems.return_value = {"response": [{"idSystem": SYS, "poolNickname": "Pool"}]}
        self.api.get_pool_details.side_effect = self._details
        self.api.set_output.side_effect = self._set_output
        self.api.set_param.side_effect = self._set_param
        self.api.command_status.side_effect = self._command_status

    @property
    def reads(self):
        return self.api.get_pool_details.await_count

    def _details(self, _system_id):
        return {
            "response": [
                {
                    "access": 10,
                    "probes": [],
                    "outs": [{"index": OUT_IDX_HEATING, "type": 8, "mode": self.mode, "status": self.status}],
                    "RegulModes": {"ConsigneEau": self.setpoint, "HeaterMode": 2},
                }
            ]
        }

    def _set_output(self, _system_id, _index, mode, state):
        if self.verdict == CONFIRMED:
            self.mode, self.status = mode, state
        return {"status": "ok", "response": {"cmdID": 77}}

    def _set_param(self, _system_id, _param, value):
        if self.verdict == CONFIRMED:
            self.setpoint = value
        return {"status": "ok", "response": {"cmdID": 77}}

    def _command_status(self, _cmd_id):
        return {"status": "ok", "response": {"cmdID": 77, "status": self.verdict, "detail": ""}}


@pytest.fixture
def box():
    return Box()


@pytest.fixture
async def entry(hass, enable_custom_integrations, box, freezer):
    """A loaded entry, its setup read already spent."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        data={CONF_USERNAME: "u", CONF_PASSWORD: "p", "password_hashed": True},
    )
    entry.add_to_hass(hass)
    with patch("custom_components.klereo.KlereoApi", return_value=box.api):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    box.api.get_pool_details.reset_mock()
    return entry


async def _advance(hass, freezer, seconds):
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def _select(hass, option):
    await hass.services.async_call(
        "select", "select_option", {"entity_id": SELECT, "option": option}, blocking=True
    )
    await hass.async_block_till_done()


async def _set_temperature(hass, temperature):
    await hass.services.async_call(
        "climate", "set_temperature", {"entity_id": CLIMATE, "temperature": temperature}, blocking=True
    )
    await hass.async_block_till_done()


def _target(hass):
    return hass.states.get(CLIMATE).attributes["temperature"]


async def test_an_isolated_write_rereads_at_once(hass, entry, box):
    await _set_temperature(hass, 26)

    assert box.reads == 1
    assert _target(hass) == 26


async def test_a_second_write_after_the_cooldown_rereads_at_once(hass, entry, box, freezer):
    """"Isolated" is a distance from the last write, not a first-write-only privilege."""
    await _set_temperature(hass, 26)
    await _advance(hass, freezer, WRITE_REREAD_COOLDOWN_SECONDS + 1)

    await _set_temperature(hass, 27)

    assert box.reads == 2


async def test_a_burst_gets_one_reread_per_cooldown(hass, entry, box, freezer):
    """The issue's reproduction: ten writes, fifteen seconds apart.

    Ten re-reads under the ten-second default, one per write. The expected four are the
    leading read at 0 s, then one at the end of each 60 s window until the burst is settled.
    """
    interval = 15

    for step in range(10):
        await _set_temperature(hass, 20 + step)
        await _advance(hass, freezer, interval)

    await _advance(hass, freezer, WRITE_REREAD_COOLDOWN_SECONDS)
    await _advance(hass, freezer, WRITE_REREAD_COOLDOWN_SECONDS)

    assert box.reads == 4


async def test_the_last_write_of_a_burst_is_read_back(hass, entry, box, freezer):
    """Nothing but a re-read can move the thermostat: `climate` writes no optimism.

    The two middle assertions are what make the last one worth anything: the value really
    is stale inside the window, so reaching 29 can only be the deferred re-read.
    """
    await _set_temperature(hass, 26)
    await _set_temperature(hass, 29)

    assert box.reads == 1
    assert _target(hass) == 26

    await _advance(hass, freezer, WRITE_REREAD_COOLDOWN_SECONDS + 1)

    assert box.reads == 2
    assert _target(hass) == 29


async def test_a_refused_command_inside_the_cooldown_repaints_without_a_read(hass, entry, box):
    """#181 where it can no longer lean on the re-read.

    The first write opens the cooldown, so the refused one gets no immediate read. The
    entity must still drop its optimism at once. It does so from the state already held,
    and the read count says so: a loop of refused commands must not buy itself a read each.
    """
    await _select(hass, "Heating")
    assert box.reads == 1

    box.verdict = INSUFFICIENT_RIGHTS
    with pytest.raises(HomeAssistantError, match="rejected"):
        await _select(hass, "Off")

    assert hass.states.get(SELECT).state == "Heating"
    assert box.reads == 1


async def test_a_failed_send_inside_the_cooldown_repaints_too(hass, entry, box):
    """The other refusal: the command never reached Klereo, and nothing else would undo it."""
    await _select(hass, "Heating")

    box.api.set_output.side_effect = ConnectionError("down")
    with pytest.raises(HomeAssistantError, match="Failed to set output"):
        await _select(hass, "Off")

    assert hass.states.get(SELECT).state == "Heating"


async def test_a_refused_command_is_still_read_back_after_the_cooldown(hass, entry, box, freezer):
    """The repaint shows what we held. The box stays the authority, so the read still comes."""
    await _select(hass, "Heating")

    box.verdict = INSUFFICIENT_RIGHTS
    with pytest.raises(HomeAssistantError, match="rejected"):
        await _select(hass, "Off")

    await _advance(hass, freezer, WRITE_REREAD_COOLDOWN_SECONDS + 1)

    assert box.reads == 2


async def test_an_isolated_refused_command_rereads_at_once(hass, entry, box):
    """No cooldown is running here, so #181 holds exactly as it did before."""
    box.verdict = INSUFFICIENT_RIGHTS

    with pytest.raises(HomeAssistantError, match="rejected"):
        await _select(hass, "Heating")

    assert hass.states.get(SELECT).state == "Off"
    assert box.reads == 1


async def test_a_confirmed_command_inside_the_cooldown_shows_on_every_sibling(hass, entry, box):
    """#174 does not wait for the deferred read: the thermostat moves on the confirmation."""
    await _set_temperature(hass, 26)
    assert box.reads == 1

    await _select(hass, "Heating")

    assert box.reads == 1
    assert hass.states.get(SELECT).state == "Heating"
    assert hass.states.get(CLIMATE).state == "heat"


async def test_a_confirmed_setpoint_inside_the_cooldown_keeps_its_value(hass, entry, box):
    """`number` holds this value in the entity alone, so repainting on success would lose it."""
    await _select(hass, "Heating")
    assert box.reads == 1

    await hass.services.async_call(
        "number", "set_value", {"entity_id": NUMBER, "value": 29}, blocking=True
    )
    await hass.async_block_till_done()

    assert box.reads == 1
    assert float(hass.states.get(NUMBER).state) == 29


async def test_a_deferred_reread_does_not_survive_unloading(hass, entry, box, freezer):
    """A write inside the cooldown arms a re-read; unloading has to take it away."""
    await _set_temperature(hass, 26)
    await _set_temperature(hass, 27)
    assert box.reads == 1

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED

    await _advance(hass, freezer, 10 * WRITE_REREAD_COOLDOWN_SECONDS)

    assert box.reads == 1


async def test_a_write_finishing_after_unloading_arms_nothing(hass, entry, box, freezer):
    """The write's own `finally` runs after the unload, and must not start a read or a timer.

    The coordinator is taken before unloading on purpose: this is the command that was
    still waiting for its verdict when the entry went away. `verify_cleanup` fails the test
    on any timer left behind, which covers the half this assertion cannot see.
    """
    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    await coordinator.async_set_param(SYS, "ConsigneEau", 26)
    await hass.async_block_till_done()
    await _advance(hass, freezer, 10 * WRITE_REREAD_COOLDOWN_SECONDS)

    assert box.reads == 0


async def test_the_refresh_button_is_served_at_the_end_of_a_running_cooldown(hass, entry, box, freezer):
    """The button shares this debouncer: a press inside the window is late, never lost."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    await _set_temperature(hass, 26)
    assert box.reads == 1

    await coordinator.async_manual_refresh()
    assert box.reads == 1

    await _advance(hass, freezer, WRITE_REREAD_COOLDOWN_SECONDS + 1)

    assert box.reads == 2
