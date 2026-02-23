"""DataUpdateCoordinator for Klereo."""
import asyncio
import logging
from datetime import timedelta

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
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
            raise ConfigEntryAuthFailed(
                "Authentication failed — please re-enter your Klereo credentials"
            ) from err
        except aiohttp.ClientResponseError as err:
            if err.status in (401, 403):
                raise ConfigEntryAuthFailed(
                    "Authentication failed — please re-enter your Klereo credentials"
                ) from err
            raise UpdateFailed(
                f"Error communicating with Klereo API: {err}"
            ) from err
        except Exception as err:
            raise UpdateFailed(
                f"Error communicating with Klereo API: {err}"
            ) from err
