"""The Heating switch is born disabled on NEW installations, and only there (#183, option D).

On output 4, "on" is not a complete command: `SetOut` needs a KlereoTherm mode, and the switch
picks *Heating* on the user's behalf (@nopbop, GitHub #55). The select and the thermostat
cover the same equipment and SHOW the mode, so a new installation gets those and no entity
that guesses. Removing the switch was refused: it would break every automation built on it,
and the thermostat's own `turn_on` makes the same choice anyway.

🔴 Both directions are tested against the real entity registry, because the second one is the
whole difference between option D and a silent removal: `entity_registry_enabled_default` is
read only when the registry entry is CREATED. If a Home Assistant release ever re-applied it
to existing entries, `test_an_existing_installation_keeps_its_switch_enabled` turns red.
"""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.klereo.const import DOMAIN

SYS = "SYS1"
HEATING_UID = f"{SYS}_output_4"
FILTRATION_UID = f"{SYS}_output_1"


@pytest.fixture
def api():
    api = AsyncMock()
    api.get_systems.return_value = {"response": [{"idSystem": SYS, "poolNickname": "Pool"}]}
    api.get_pool_details.return_value = {
        "response": [
            {
                "access": 10,
                "probes": [],
                "outs": [
                    {"index": 1, "type": 0, "mode": 0, "status": 1},
                    {"index": 4, "type": 8, "mode": 0, "status": 0},
                ],
                "RegulModes": {"ConsigneEau": 28, "HeaterMode": 2},
            }
        ]
    }
    return api


def _entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        data={CONF_USERNAME: "u", CONF_PASSWORD: "p", "password_hashed": True},
    )
    entry.add_to_hass(hass)
    return entry


async def _setup(hass, entry, api):
    with patch("custom_components.klereo.KlereoApi", return_value=api):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


def _switch(hass, unique_id):
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("switch", DOMAIN, unique_id)
    assert entity_id is not None, f"no registry entry for {unique_id}"
    return registry.async_get(entity_id)


async def test_a_new_installation_gets_the_heating_switch_disabled(hass, enable_custom_integrations, api):
    await _setup(hass, _entry(hass), api)

    heating = _switch(hass, HEATING_UID)
    assert heating.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get(heating.entity_id) is None
    # The select and the thermostat still cover the equipment.
    assert hass.states.get("select.pool_heating_mode") is not None
    assert hass.states.get("climate.pool_heating") is not None


async def test_the_other_switches_are_born_enabled(hass, enable_custom_integrations, api):
    """Negative control: the default is on output 4, not on the platform."""
    await _setup(hass, _entry(hass), api)

    filtration = _switch(hass, FILTRATION_UID)
    assert filtration.disabled_by is None
    assert hass.states.get(filtration.entity_id).state == "on"


async def test_an_existing_installation_keeps_its_switch_enabled(hass, enable_custom_integrations, api):
    """The half that makes D differ from a removal: an enabled entry stays enabled."""
    entry = _entry(hass)
    registry = er.async_get(hass)
    existing = registry.async_get_or_create(
        "switch", DOMAIN, HEATING_UID, config_entry=entry, suggested_object_id="pool_heating"
    )
    assert existing.disabled_by is None

    await _setup(hass, entry, api)

    heating = _switch(hass, HEATING_UID)
    assert heating.entity_id == existing.entity_id
    assert heating.disabled_by is None
    assert hass.states.get(heating.entity_id).state == "off"


async def test_a_user_can_enable_it(hass, enable_custom_integrations, api):
    """Disabled by default is an offer withdrawn, not a control taken away."""
    entry = _entry(hass)
    await _setup(hass, entry, api)
    registry = er.async_get(hass)
    heating = _switch(hass, HEATING_UID)

    registry.async_update_entity(heating.entity_id, disabled_by=None)
    with patch("custom_components.klereo.KlereoApi", return_value=api):
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

    assert hass.states.get(heating.entity_id).state == "off"
