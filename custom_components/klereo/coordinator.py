"""DataUpdateCoordinator for Klereo."""
import asyncio
import logging
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import KlereoApi, KlereoApiError
from .const import SCAN_INTERVAL_MINUTES

_LOGGER = logging.getLogger(__name__)


class KlereoCoordinator(DataUpdateCoordinator):
    """Klereo data update coordinator."""

    api: KlereoApi

    def __init__(self, hass: HomeAssistant, api: KlereoApi, scan_interval: int = SCAN_INTERVAL_MINUTES) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="klereo",
            update_interval=timedelta(minutes=scan_interval),
        )
        self.api = api

    async def _async_update_data(self) -> dict:
        """Fetch data from the Klereo API."""
        try:
            systems_response = await self.api.get_systems()
            _LOGGER.debug("Systems response: %s", systems_response)

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

            # Build system map
            data: dict = {}
            system_map: dict = {}
            for system in system_list:
                sys_id = system.get("idSystem")
                if sys_id:
                    system_map[sys_id] = system

            # Fetch all pool details in parallel
            details_results = await asyncio.gather(
                *(self.api.get_pool_details(sid) for sid in system_map),
                return_exceptions=True,
            )

            for sys_id, result in zip(system_map, details_results):
                system = system_map[sys_id]
                details = system.copy()

                if isinstance(result, Exception):
                    _LOGGER.warning(
                        "Failed to get pool details for system %s: %s",
                        sys_id, result,
                    )
                elif isinstance(result, dict):
                    response_data = result.get("response")
                    if isinstance(response_data, list) and response_data:
                        details.update(response_data[0])

                # Build index dicts for O(1) entity lookup
                probes = details.get("probes", [])
                outs = details.get("outs", [])
                details["_probe_index"] = {p["index"]: p for p in probes if "index" in p}
                details["_output_index"] = {o["index"]: o for o in outs if "index" in o}

                data[sys_id] = {"info": system, "details": details}

            return data

        except KlereoApiError as err:
            raise UpdateFailed(
                f"Klereo API error: {err}"
            ) from err
        except aiohttp.ClientResponseError as err:
            if err.status in (401, 403):
                raise ConfigEntryAuthFailed(
                    "Authentication failed — please re-enter your Klereo credentials"
                ) from err
            raise UpdateFailed(
                f"Error communicating with Klereo API: {err}"
            ) from err

    async def async_set_output(
        self, system_id: str, out_index: int, mode: int, state: int
    ) -> Any:
        """Send a set-output command and request a data refresh."""
        try:
            result = await self.api.set_output(system_id, out_index, mode, state)
        except Exception as err:
            raise HomeAssistantError(
                f"Failed to set output {out_index}: {err}"
            ) from err
        await self.async_request_refresh()
        return result

    async def async_set_param(self, system_id: str, param_id: str, value: Any) -> Any:
        """Send a set-parameter command and request a data refresh."""
        try:
            result = await self.api.set_param(system_id, param_id, value)
        except Exception as err:
            raise HomeAssistantError(
                f"Failed to set parameter {param_id}: {err}"
            ) from err
        await self.async_request_refresh()
        return result
