"""Diagnostics support for Klereo."""
from dataclasses import asdict

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
    coordinator_data = {
        sys_id: asdict(system_data)
        for sys_id, system_data in coordinator.data.items()
    }
    return {
        "config_entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "coordinator_data": async_redact_data(coordinator_data, TO_REDACT),
    }
