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
    CMD_POLL_ATTEMPTS,
    CMD_POLL_INTERVAL_SECONDS,
    CMD_STATUS_IN_FLIGHT,
    CMD_STATUS_LABELS,
    CMD_STATUS_OK,
    KlereoApi,
    KlereoApiError,
    extract_system_list,
)
from .const import SCAN_INTERVAL_MIN_MINUTES, SCAN_INTERVAL_MINUTES, SETTING_CONTAINERS
from .models import KlereoPoolDetails, KlereoSystemData, KlereoSystemInfo

_LOGGER = logging.getLogger(__name__)


class KlereoCoordinator(DataUpdateCoordinator[dict[str, KlereoSystemData]]):
    """Klereo data update coordinator."""

    api: KlereoApi

    def __init__(self, hass: HomeAssistant, api: KlereoApi, scan_interval: int = SCAN_INTERVAL_MINUTES) -> None:
        """Initialize the coordinator.

        `scan_interval` is clamped to `SCAN_INTERVAL_MIN_MINUTES` because it arrives from a
        PERSISTED option: an entry configured before the floor existed still carries its old
        value, and bounding only the options form would leave those installs polling faster
        than Klereo allows, silently. See #139.
        """
        super().__init__(
            hass,
            _LOGGER,
            name="klereo",
            update_interval=timedelta(minutes=max(scan_interval, SCAN_INTERVAL_MIN_MINUTES)),
        )
        self.api = api

    async def _async_update_data(self) -> dict[str, KlereoSystemData]:
        """Fetch data from the Klereo API."""
        try:
            systems_response = await self.api.get_systems()
            _LOGGER.debug("Systems response: %s", systems_response)

            system_list = extract_system_list(systems_response)

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
                # The `GetPoolDetails` element, kept apart from the merged view because
                # the diagnostics export publishes it verbatim (#145). `info.raw` already
                # carries the `GetIndex` half; keeping the merged dict here would publish
                # that half twice in every export.
                pool_payload: dict[str, Any] = {}

                if isinstance(result, Exception):
                    _LOGGER.warning(
                        "Failed to get pool details for system %s: %s",
                        sys_id, result,
                    )
                elif isinstance(result, dict):
                    response_data = result.get("response")
                    if isinstance(response_data, list) and response_data:
                        pool_payload = response_data[0]
                        details_raw.update(pool_payload)

                # Which containers the API actually sends is the open question behind
                # #94: `RegulModes` was guessed from one user's log, while the upstream
                # plugin reads every setpoint from `params`. Recording the shape on each
                # refresh turns the next report into a measurement instead of a guess.
                _LOGGER.debug(
                    "Detail payload for system %s carries top-level keys: %s",
                    sys_id, sorted(details_raw),
                )
                # 🔴 The line above answered LESS than it looked like it did. Its first
                # real reading (GitHub #57, 2026-08-26) showed `RegulModes`, `params` and
                # `ExtraParams` all present at once — which retired the question "which
                # container does this install return?" and left the one that actually
                # blocks #54 untouched: which KEYS each of them carries. Top-level names
                # cannot say where `ConsigneEau` or `PHMinus_TodayTime` live.
                #
                # An instrument one level too shallow reads as an answer, which is why
                # this cost a second round-trip to a reporter. Logging the contents makes
                # the NEXT debug log anyone pastes settle it, whatever they pasted it for.
                for container in SETTING_CONTAINERS:
                    contents = details_raw.get(container)
                    if isinstance(contents, dict):
                        _LOGGER.debug(
                            "  %s carries keys: %s", container, sorted(contents),
                        )

                data[sys_id] = KlereoSystemData(
                    info=KlereoSystemInfo.from_dict(system),
                    details=KlereoPoolDetails.from_dict(details_raw, raw=pool_payload),
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
        # Klereo documents `response` as a JSON ARRAY whose elements carry `cmdID` and
        # `poolID` (`docs/klereo-api.md`). #95 shipped without that document and read only
        # the scalar and mapping forms, so the documented one fell through to None — the
        # write then went unverified while reporting nothing (#106).
        if isinstance(response, list):
            response = response[0] if response else None
        if isinstance(response, dict):
            for key in ("cmdID", "cmdId", "cmd_id", "id"):
                if key in response:
                    return response[key]
            return None
        if isinstance(response, int | str):
            return response
        return None

    @staticmethod
    def _command_status(result: Any, cmd_id: Any) -> tuple[Any, str | None]:
        """Return the `(status, detail)` a status response carries for `cmd_id`.

        Three shapes are read, and only the third is measured. #95 shipped reading
        `response` as a bare integer; #106 added the JSON ARRAY `docs/klereo-api.md`
        documents, on the ground that reading both could not regress whichever turned out
        to be real. **Neither is.** The first measured payload (GitHub #55, 2026-08-26)
        carries `response` as a single OBJECT:

            {"status": "ok", "response": {"cmdID": 4351826, "status": 9,
             "startTime": 1787652057, "updateTime": 1787652059, "detail": "Ok"}}

        That object fell through to `None`, so `_async_confirm_command` logged "unreadable
        command status" and returned False for EVERY write on EVERY install — a status 13
        (insufficient rights) was indistinguishable from a success, which is the exact
        silence #95 was built to remove. `_command_id` had read the object form since #106;
        this one had not, and nothing compared the two.

        The match is on `cmdID` rather than on position: the documentation says each
        element represents a command, so a multi-element response is well-formed and
        taking `[0]` would report another command's verdict as ours. `cmdID` DISQUALIFIES
        a verdict proven to belong elsewhere; it is not required to be present, since no
        install has been measured to always send it.
        """
        response = result.get("response") if isinstance(result, dict) else None
        if isinstance(response, int):
            return response, None
        if isinstance(response, dict):
            return KlereoCoordinator._status_of(response, cmd_id)
        if isinstance(response, list):
            entries = [entry for entry in response if isinstance(entry, dict)]
            match = next((entry for entry in entries if entry.get("cmdID") == cmd_id), None)
            entry = match if match is not None else (entries[0] if entries else None)
            if entry is not None:
                return entry.get("status"), entry.get("detail") or None
        return None, None

    @staticmethod
    def _status_of(entry: dict[str, Any], cmd_id: Any) -> tuple[Any, str | None]:
        """Return `(status, detail)` from one command entry, unless it names another command."""
        entry_id = entry.get("cmdID")
        if entry_id is not None and entry_id != cmd_id:
            return None, None
        return entry.get("status"), entry.get("detail") or None

    async def _async_confirm_command(self, result: Any, description: str) -> bool:
        """Raise if a queued command was rejected; return whether it is confirmed done.

        `SetOut` and `SetParam` queue and return immediately, so their HTTP 200 means
        "accepted for execution", never "executed" — a refused command is otherwise
        indistinguishable from a successful one. Upstream calls `waitCommand($cmdID)`
        after every write and refreshes only on status 9 (`klereo.class.php` l.1661-1687).

        We read the verdict from the NON-blocking `CommandStatus` route and poll it, which
        is why the loop below exists: a single non-blocking call lands on an in-flight
        status almost every time. Exhausting the ceiling means UNCONFIRMED, never success —
        and a rejection is a verdict, so it leaves the loop at once rather than being
        polled into an exhaustion. See #140.
        """
        cmd_id = self._command_id(result)
        if cmd_id is None:
            _LOGGER.warning(
                "%s: no command id in the API response, so its outcome cannot be "
                "verified. Response: %s", description, result,
            )
            return False

        for attempt in range(CMD_POLL_ATTEMPTS):
            if attempt:
                await asyncio.sleep(CMD_POLL_INTERVAL_SECONDS)

            try:
                status_result = await self.api.command_status(cmd_id)
            except Exception as err:
                _LOGGER.warning("%s: could not read command status: %s", description, err)
                return False

            status, klereo_detail = self._command_status(status_result, cmd_id)
            if not isinstance(status, int):
                _LOGGER.warning(
                    "%s: unreadable command status. Response: %s", description, status_result,
                )
                return False

            if status == CMD_STATUS_OK:
                _LOGGER.debug("%s: confirmed by Klereo (cmdID %s)", description, cmd_id)
                return True

            if status in CMD_STATUS_IN_FLIGHT:
                _LOGGER.debug(
                    "%s: still %s (cmdID %s)",
                    description, CMD_STATUS_LABELS.get(status, status), cmd_id,
                )
                continue

            break
        else:
            # The ceiling is not a verdict. Klereo answers in 1-2 s in practice, so a
            # command still in flight here is an anomaly worth seeing without debug on.
            _LOGGER.warning(
                "%s: still not confirmed after %s checks (cmdID %s). It may yet run; "
                "Home Assistant will not report on it.",
                description, CMD_POLL_ATTEMPTS, cmd_id,
            )
            return False

        label = CMD_STATUS_LABELS.get(status)
        detail = f"{label} (status {status})" if label else f"status {status}"
        # `detail` is Klereo's own free-text field. It is the only part of a rejection that
        # can name the actual cause, so it is surfaced verbatim when present.
        if klereo_detail:
            detail = f"{detail} — {klereo_detail}"
        raise HomeAssistantError(f"{description} was rejected by Klereo: {detail}")

    async def async_set_output(
        self, system_id: str, out_index: int, mode: int, state: int
    ) -> Any:
        """Send a set-output command, check it ran, and request a data refresh."""
        description = f"Setting output {out_index}"
        _LOGGER.debug("%s: sending mode=%s state=%s to system %s", description, mode, state, system_id)
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
        _LOGGER.debug("%s: sending value=%s to system %s", description, value, system_id)
        try:
            result = await self.api.set_param(system_id, param_id, value)
        except Exception as err:
            raise HomeAssistantError(
                f"Failed to set parameter {param_id}: {err}"
            ) from err
        await self._async_confirm_command(result, description)
        await self.async_request_refresh()
        return result
