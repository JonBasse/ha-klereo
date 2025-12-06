"""The Klereo integration."""
import asyncio
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, SCAN_INTERVAL_MINUTES
from .api import KlereoApi

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Klereo from a config entry."""
    
    hass.data.setdefault(DOMAIN, {})
    
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    session = async_get_clientsession(hass)
    
    api = KlereoApi(username, password, session)
    
    # Coordinator to fetch data
    async def async_update_data():
        """Fetch data from API endpoint."""
        try:
            # First ensure we have systems
            systems = await api.get_systems()
            _LOGGER.debug(f"Systems response: {systems}")
            
            # For each system, get details. 
            # We will store data as a dict keyed by system ID.
            data = {}
            
            # Handle if get_systems returns a list or something else.
            # Assuming it returns a list of systems or a dict with a list.
            # Jeedom loop: foreach ($result['list_systems'] as $system)
            
            if "list_systems" in systems:
                system_list = systems["list_systems"]
            else:
                 # Fallback if structure is different
                 system_list = systems if isinstance(systems, list) else []

            _LOGGER.debug(f"Parsed system list: {system_list}")

            for system in system_list:
                # System object likely has an 'id'
                sys_id = system.get("id")
                if sys_id:
                    details = await api.get_pool_details(sys_id)
                    _LOGGER.debug(f"Details for system {sys_id}: {details}")
                    data[sys_id] = {
                        "info": system,
                        "details": details
                    }
            
            return data
            
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}")

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="klereo",
        update_method=async_update_data,
        update_interval=timedelta(minutes=SCAN_INTERVAL_MINUTES),
    )
    
    coordinator.api = api # Attach API client to coordinator for use in platform entities

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
