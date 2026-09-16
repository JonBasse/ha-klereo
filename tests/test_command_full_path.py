"""A heating command through the WHOLE Home Assistant path, re-read included (#182).

@nopbop, 2026-09-15, v1.18.1: from *Stopped* he presses the **Heating** switch, his debug log
shows one `SetOut mode=3 state=1` confirmed by Klereo in 2.7 s, **Heating Mode** and the
thermostat move to *Heating* — and the switch he pressed stays `off`. He read it as optimism
applied to the siblings and not to the actuated entity.

`tests/test_optimistic_siblings.py` could not say whether that reading holds: it drives the
entities directly and replaces `async_request_refresh` with an inert mock, so the re-read
that follows every command (#181) never runs there. This file drives the real service
call, the real coordinator and the real re-read, from each of the three entities that can
start the heat pump.

What it measured, 2026-09-16:

1. When Klereo's next payload agrees with the command, the switch reads `on` from ALL three
   entry points. There is no local asymmetry, and the reading "optimism applied to the
   others" is refuted in code.
2. When that payload carries `mode: 3` with `status: 0`, the three entities end exactly as
   @nopbop describes — switch `off`, select *Heating*, thermostat *heat* — but from ALL three
   entry points, not only the switch. `select` and `climate` read `mode`, `switch` reads
   `status`, and the re-read replaces the optimism by construction (#174).

Case 2 is the only mechanism found that produces his picture, and it is reading 2 of #174 —
the partially fresh payload that ticket refuted structurally but never measured inside the
window. It is a shape, not a measurement: a diagnostics export taken WHILE the switch reads
`off` and the select reads *Heating* shows `details.raw.outs[4]` as that re-read returned it,
and settles it. Until then nothing here is "fixed": holding the optimism against the payload
would hide exactly the box-side lag #174 refused to hide.
"""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.klereo.api import (
    HEAT_MODE_HEATING,
    HEAT_MODE_STOP,
    OUT_IDX_HEATING,
    OUT_STATE_OFF,
    OUT_STATE_ON,
)
from custom_components.klereo.const import DOMAIN

SYS = "SYS1"
SWITCH = "switch.pool_heating"
SELECT = "select.pool_heating_mode"
CLIMATE = "climate.pool_heating"

ENTRY_POINTS = [
    pytest.param(("switch", "turn_on", SWITCH, {}), id="from-the-switch"),
    pytest.param(("select", "select_option", SELECT, {"option": "Heating"}), id="from-the-select"),
    pytest.param(("climate", "set_hvac_mode", CLIMATE, {"hvac_mode": "heat"}), id="from-the-thermostat"),
]


def _payload(mode, status):
    """@nopbop's shape: access 10, a real heat pump, output 4 a KlereoTherm."""
    return {
        "response": [
            {
                "access": 10,
                "probes": [],
                "outs": [{"index": OUT_IDX_HEATING, "type": 8, "mode": mode, "status": status}],
                "RegulModes": {"ConsigneEau": 28, "HeaterMode": 2},
            }
        ]
    }


@pytest.fixture
def box():
    """A stopped KlereoTherm whose payload becomes `box["after"]` once the command is confirmed."""
    box = {"now": (HEAT_MODE_STOP, OUT_STATE_OFF), "after": None}
    api = AsyncMock()
    api.get_systems.return_value = {"response": [{"idSystem": SYS, "poolNickname": "Pool"}]}
    api.get_pool_details.side_effect = lambda sid: _payload(*box["now"])
    api.set_output.return_value = {"status": "ok", "response": {"cmdID": 77}}

    async def _confirmed(*args, **kwargs):
        box["now"] = box["after"]
        return {"status": "ok", "response": {"cmdID": 77, "status": 9, "detail": "Ok"}}

    api.command_status.side_effect = _confirmed
    box["api"] = api
    return box


@pytest.fixture(autouse=True)
def _no_confirmation_wait():
    with patch("custom_components.klereo.coordinator.asyncio.sleep", AsyncMock()):
        yield


async def _start_heating(hass, box, entry_point):
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        data={CONF_USERNAME: "u", CONF_PASSWORD: "p", "password_hashed": True},
    )
    entry.add_to_hass(hass)
    # An EXISTING installation: the Heating switch is born disabled on new ones (#183), and
    # @nopbop's is an enabled entry that predates that.
    er.async_get(hass).async_get_or_create(
        "switch", DOMAIN, f"{SYS}_output_{OUT_IDX_HEATING}", config_entry=entry,
        suggested_object_id="pool_heating",
    )
    with patch("custom_components.klereo.KlereoApi", return_value=box["api"]):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    # Positive control: all three start from Stopped, or "ends on" would prove nothing.
    assert [hass.states.get(e).state for e in (SWITCH, SELECT, CLIMATE)] == ["off", "Off", "off"]

    domain, service, entity_id, data = entry_point
    await hass.services.async_call(domain, service, {"entity_id": entity_id, **data}, blocking=True)
    await hass.async_block_till_done()
    box["api"].set_output.assert_awaited_once_with(SYS, OUT_IDX_HEATING, HEAT_MODE_HEATING, OUT_STATE_ON)
    return [hass.states.get(e).state for e in (SWITCH, SELECT, CLIMATE)]


@pytest.mark.parametrize("entry_point", ENTRY_POINTS)
async def test_an_agreeing_box_shows_heating_everywhere(hass, enable_custom_integrations, box, entry_point):
    """Reading 1 of #182 refuted: the actuated switch follows its own command."""
    box["after"] = (HEAT_MODE_HEATING, OUT_STATE_ON)

    assert await _start_heating(hass, box, entry_point) == ["on", "Heating", "heat"]


@pytest.mark.parametrize("entry_point", ENTRY_POINTS)
async def test_a_box_answering_mode_without_status_leaves_only_the_switch_off(
    hass, enable_custom_integrations, box, entry_point
):
    """@nopbop's picture — from every entry point, which is what makes it a fact about the payload.

    If his report that the switch follows when he drives the select holds, this case is NOT
    his mechanism either, and the next step is his export, not a change here.
    """
    box["after"] = (HEAT_MODE_HEATING, OUT_STATE_OFF)

    assert await _start_heating(hass, box, entry_point) == ["off", "Heating", "heat"]
