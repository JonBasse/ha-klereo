"""Diagnostics support for Klereo."""
from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .const import DOMAIN

TO_REDACT = {CONF_PASSWORD, "jwt", "token", "login"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    return {
        "config_entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "coordinator_data": async_redact_data(coordinator.data, TO_REDACT),
    }
