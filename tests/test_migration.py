"""The password migration of `async_migrate_entry`, through Home Assistant's own path.

Version 1 entries may hold the password in clear, or already hashed with `password_hashed`
set. Hashing the second kind again would replace a working credential with the hash of a
hash, and the user would meet it as a reauthentication request (#217).
"""
from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.klereo.const import DOMAIN

PLAIN = "test"
HASHED = "a94a8fe5ccb19ba61c4c0873d391e987982fbbd3"  # sha1("test")


async def _set_up(hass, *, version, data):
    entry = MockConfigEntry(domain=DOMAIN, version=version, data={CONF_USERNAME: "u", **data})
    entry.add_to_hass(hass)
    with patch("custom_components.klereo.async_setup_entry", AsyncMock(return_value=True)):
        assert await hass.config_entries.async_setup(entry.entry_id)
    return entry


async def test_a_clear_password_is_hashed(hass, enable_custom_integrations):
    entry = await _set_up(hass, version=1, data={CONF_PASSWORD: PLAIN})

    assert entry.version == 2
    assert entry.data[CONF_PASSWORD] == HASHED
    assert entry.data["password_hashed"] is True


async def test_an_already_hashed_password_is_not_hashed_twice(hass, enable_custom_integrations):
    entry = await _set_up(hass, version=1, data={CONF_PASSWORD: HASHED, "password_hashed": True})

    assert entry.version == 2
    assert entry.data[CONF_PASSWORD] == HASHED

