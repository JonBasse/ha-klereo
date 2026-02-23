"""The Klereo integration."""
import hashlib
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import KlereoApi
from .const import DOMAIN, SCAN_INTERVAL_MINUTES
from .coordinator import KlereoCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.NUMBER, Platform.SENSOR, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Klereo from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    password = entry.data[CONF_PASSWORD]
    # Migrate plaintext password to SHA-1 hash (Klereo API requirement).
    # Use an explicit flag to avoid misidentifying a 40-char hex password as a hash.
    if not entry.data.get("password_hashed"):
        password_hash = hashlib.sha1(password.encode("utf-8")).hexdigest()
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_PASSWORD: password_hash, "password_hashed": True},
        )
    else:
        password_hash = password

    session = async_get_clientsession(hass)
    api = KlereoApi(entry.data[CONF_USERNAME], password_hash, session)

    scan_interval = entry.options.get("scan_interval", SCAN_INTERVAL_MINUTES)
    coordinator = KlereoCoordinator(hass, api, scan_interval=scan_interval)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
