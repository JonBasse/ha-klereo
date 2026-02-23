"""DataUpdateCoordinator for Klereo."""
import logging
from datetime import timedelta

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import KlereoApi, KlereoApiError
from .const import SCAN_INTERVAL_MINUTES

_LOGGER = logging.getLogger(__name__)


class KlereoCoordinator(DataUpdateCoordinator):
    """Klereo data update coordinator."""

    api: KlereoApi

    def __init__(self, hass: HomeAssistant, api: KlereoApi) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="klereo",
            update_interval=timedelta(minutes=SCAN_INTERVAL_MINUTES),
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

            data: dict = {}
            for system in system_list:
                sys_id = system.get("idSystem")
                if not sys_id:
                    continue

                details = system.copy()

                try:
                    details_response = await self.api.get_pool_details(sys_id)
                    if isinstance(details_response, dict):
                        response_data = details_response.get("response")
                        if isinstance(response_data, list) and response_data:
                            details.update(response_data[0])
                except (aiohttp.ClientError, KlereoApiError, TimeoutError):
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
