"""The Klereo integration."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import KlereoApi
from .const import DOMAIN
from .coordinator import KlereoCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Klereo from a config entry."""
    import hashlib

    hass.data.setdefault(DOMAIN, {})

    password = entry.data[CONF_PASSWORD]
    # Migrate plaintext password to hash (SHA-1 hex is always 40 lowercase hex chars)
    if len(password) != 40 or not all(c in "0123456789abcdef" for c in password):
        password_hash = hashlib.sha1(password.encode("utf-8")).hexdigest()
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_PASSWORD: password_hash},
        )
    else:
        password_hash = password

    session = async_get_clientsession(hass)
    api = KlereoApi(entry.data[CONF_USERNAME], password_hash, session)

    coordinator = KlereoCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
