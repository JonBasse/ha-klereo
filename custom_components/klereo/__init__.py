"""The Klereo integration."""
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import KlereoApi
from .const import DOMAIN, SCAN_INTERVAL_MINUTES

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Klereo from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    session = async_get_clientsession(hass)
    api = KlereoApi(entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD], session)

    async def async_update_data():
        """Fetch data from the Klereo API."""
        try:
            systems_response = await api.get_systems()
            _LOGGER.debug("Systems response: %s", systems_response)

            # Parse system list from response — the API wraps it differently
            # depending on context (direct list, {"response": [...]}, or
            # {"list_systems": [...]}).
            if isinstance(systems_response, dict):
                system_list = systems_response.get(
                    "response", systems_response.get("list_systems", [])
                )
            elif isinstance(systems_response, list):
                system_list = systems_response
            else:
                system_list = []

            if not isinstance(system_list, list):
                system_list = []

            data = {}
            for system in system_list:
                sys_id = system.get("idSystem")
                if not sys_id:
                    continue

                # Start with the system-level data from GetIndex
                details = system.copy()

                # Merge in full details from GetPoolDetails
                try:
                    details_response = await api.get_pool_details(sys_id)
                    if isinstance(details_response, dict):
                        response_data = details_response.get("response")
                        if isinstance(response_data, list) and response_data:
                            details.update(response_data[0])
                except Exception:
                    _LOGGER.warning(
                        "Failed to get pool details for system %s",
                        sys_id,
                        exc_info=True,
                    )

                data[sys_id] = {"info": system, "details": details}

            return data

        except Exception as err:
            raise UpdateFailed(
                f"Error communicating with Klereo API: {err}"
            ) from err

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="klereo",
        update_method=async_update_data,
        update_interval=timedelta(minutes=SCAN_INTERVAL_MINUTES),
    )
    coordinator.api = api

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
