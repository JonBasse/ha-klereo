"""DataUpdateCoordinator for Klereo."""
import asyncio
import logging
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    CMD_STATUS_IN_FLIGHT,
    CMD_STATUS_LABELS,
    CMD_STATUS_OK,
    KlereoApi,
    KlereoApiError,
)
from .const import SCAN_INTERVAL_MINUTES
from .models import KlereoPoolDetails, KlereoSystemData, KlereoSystemInfo

_LOGGER = logging.getLogger(__name__)


class KlereoCoordinator(DataUpdateCoordinator[dict[str, KlereoSystemData]]):
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

    async def _async_update_data(self) -> dict[str, KlereoSystemData]:
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
            data: dict[str, KlereoSystemData] = {}
            system_map: dict[str, dict] = {}
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
                details_raw = system.copy()

                if isinstance(result, Exception):
                    _LOGGER.warning(
                        "Failed to get pool details for system %s: %s",
                        sys_id, result,
                    )
                elif isinstance(result, dict):
                    response_data = result.get("response")
                    if isinstance(response_data, list) and response_data:
                        details_raw.update(response_data[0])

                data[sys_id] = KlereoSystemData(
                    info=KlereoSystemInfo.from_dict(system),
                    details=KlereoPoolDetails.from_dict(details_raw),
                )

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

    @staticmethod
    def _command_id(result: Any) -> Any:
        """Return the cmdID a queued write answered with, or None.

        The response shape is NOT measured — this reads the plausible ones and gives up
        quietly on anything else. An expired JWT, for one, answers
        `{"status": "error", "detail": ...}` with no `response` key at all. Turning a
        guessed shape into a hard failure would break every write on an assumption, which
        is exactly the defect #94 records.
        """
        if not isinstance(result, dict):
            return None
        response = result.get("response")
        if isinstance(response, dict):
            for key in ("cmdID", "cmdId", "cmd_id", "id"):
                if key in response:
                    return response[key]
            return None
        if isinstance(response, int | str):
            return response
        return None

    async def _async_confirm_command(self, result: Any, description: str) -> bool:
        """Raise if a queued command was rejected; return whether it is confirmed done.

        `SetOut` and `SetParam` queue and return immediately, so their HTTP 200 means
        "accepted for execution", never "executed" — a refused command is otherwise
        indistinguishable from a successful one. Upstream calls `waitCommand($cmdID)`
        after every write and refreshes only on status 9 (`klereo.class.php` l.1661-1687).
        """
        cmd_id = self._command_id(result)
        if cmd_id is None:
            _LOGGER.warning(
                "%s: no command id in the API response, so its outcome cannot be "
                "verified. Response: %s", description, result,
            )
            return False

        try:
            status_result = await self.api.command_status(cmd_id)
        except Exception as err:
            _LOGGER.warning("%s: could not read command status: %s", description, err)
            return False

        status = status_result.get("response") if isinstance(status_result, dict) else None
        if not isinstance(status, int):
            _LOGGER.warning(
                "%s: unreadable command status. Response: %s", description, status_result,
            )
            return False

        if status == CMD_STATUS_OK:
            return True

        if status in CMD_STATUS_IN_FLIGHT:
            _LOGGER.debug(
                "%s: still %s", description, CMD_STATUS_LABELS.get(status, status),
            )
            return False

        label = CMD_STATUS_LABELS.get(status)
        detail = f"{label} (status {status})" if label else f"status {status}"
        raise HomeAssistantError(f"{description} was rejected by Klereo: {detail}")

    async def async_set_output(
        self, system_id: str, out_index: int, mode: int, state: int
    ) -> Any:
        """Send a set-output command, check it ran, and request a data refresh."""
        description = f"Setting output {out_index}"
        try:
            result = await self.api.set_output(system_id, out_index, mode, state)
        except Exception as err:
            raise HomeAssistantError(
                f"Failed to set output {out_index}: {err}"
            ) from err
        await self._async_confirm_command(result, description)
        await self.async_request_refresh()
        return result

    async def async_set_param(self, system_id: str, param_id: str, value: Any) -> Any:
        """Send a set-parameter command, check it ran, and request a data refresh."""
        description = f"Setting parameter {param_id}"
        try:
            result = await self.api.set_param(system_id, param_id, value)
        except Exception as err:
            raise HomeAssistantError(
                f"Failed to set parameter {param_id}: {err}"
            ) from err
        await self._async_confirm_command(result, description)
        await self.async_request_refresh()
        return result
