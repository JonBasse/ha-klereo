"""API Client for Klereo."""
import asyncio
import json
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

# API wire constants
API_URL_BASE = "https://connect.klereo.fr/php"
API_URL_LOGIN = f"{API_URL_BASE}/GetJWT.php"
API_URL_GET_INDEX = f"{API_URL_BASE}/GetIndex.php"
API_URL_GET_POOL_DETAILS = f"{API_URL_BASE}/GetPoolDetails.php"
API_URL_SET_OUT = f"{API_URL_BASE}/SetOut.php"
API_URL_SET_PARAM = f"{API_URL_BASE}/SetParam.php"
API_URL_COMMAND_STATUS = f"{API_URL_BASE}/CommandStatus.php"

API_VERSION = "393-J"
API_COM_MODE = 1

# Klereo writes are a TWO-step protocol, not one: `SetOut` / `SetParam` only *queue* the
# command and return a cmdID immediately; a second call reports what actually happened.
# An HTTP 200 on the first step therefore says nothing about execution.
#
# Klereo documents TWO routes for that second call (`docs/klereo-api.md`):
#
#   * `WaitCommand.php`   — waits for the end of execution (BLOCKING)
#   * `CommandStatus.php` — returns immediately (what we use)
#
# We use the non-blocking one and poll. The reporter of GitHub #58 measured the real
# latency at 1 to 2 seconds from `SetOut` to `status: 9`, consistently, which leaves the
# blocking route nothing to buy — it only held a user-facing service call open for the
# whole client timeout.
#
# 🔴 The two halves are inseparable. `CommandStatus` returning immediately means a SINGLE
# call lands on `CMD_STATUS_IN_FLIGHT` almost every time; switching the route without the
# poll in `KlereoCoordinator._async_confirm_command` would report every write as
# unconfirmed, silently, and it would look like a success. See #140.
# Codes from Klereo's own API documentation, relayed by the reporter of GitHub #58.
CMD_STATUS_PENDING = 0
CMD_STATUS_RUNNING = 1
CMD_STATUS_OK = 9

# Statuses that are not yet a verdict: the command is still on its way.
CMD_STATUS_IN_FLIGHT = frozenset({CMD_STATUS_PENDING, CMD_STATUS_RUNNING})

CMD_STATUS_LABELS = {
    CMD_STATUS_PENDING: "pending",
    CMD_STATUS_RUNNING: "running",
    CMD_STATUS_OK: "executed successfully",
    10: "command failed",
    11: "bad parameters",
    12: "unknown command",
    13: "insufficient rights",
    15: "execution timeout",
    16: "aborted",
    17: "pool not connected",
    18: "service unavailable",
    19: "box firmware too old",
}

CMD_POLL_ATTEMPTS = 10
CMD_POLL_INTERVAL_SECONDS = 0.5

TIMEOUT = 10
USER_AGENT = "Jeedom plugin"

# Output modes. Klereo's API documentation lists ten (`docs/klereo-api.md`); the upstream
# plugin, written independently, validates exactly {0,1,2,3,4,6,8,9} for writes
# (klereo.class.php l.1198) — the same ten minus 5 and 7, which the documentation marks
# "USAGE INTERNE !! Ne pas utiliser". Two sources agreeing on that precise exclusion is
# what allowed this table to be widened without measuring the live API (#105).
# Only the eight writable ones are named and labelled: 5 and 7 are deliberately absent, so
# they resolve to no label rather than to a wrong one.
OUT_MODE_MAN = 0
OUT_MODE_TIME_SLOTS = 1
OUT_MODE_TIMER = 2
OUT_MODE_REGUL = 3
OUT_MODE_FILTRATION_SYNC = 4
OUT_MODE_MAINTENANCE = 6
OUT_MODE_PULSE = 8
# "Automate" upstream and in the documentation — a PLC-driven mode, not the AUTO *state*.
OUT_MODE_AUTOMATIC = 9

# Output states (from Jeedom plugin _OUT_STATE_* constants)
OUT_STATE_OFF = 0
OUT_STATE_ON = 1
# Any mode other than Manual reports and expects AUTO rather than ON/OFF.
OUT_STATE_AUTO = 2

# Output 4 (Heating) overloads newMode: it carries the KlereoTherm mode, not
# the output mode. Sending OUT_MODE_MAN (0) there means "Off".
# Source: Jeedom plugin klereo.class.php, _HEAT_MODE_* (l.1377-1380) and the
# `elseif ($outIndex === 4)` branch (l.1525+).
OUT_IDX_HEATING = 4

HEAT_MODE_STOP = 0
HEAT_MODE_AUTO = 1
HEAT_MODE_COOLING = 2
HEAT_MODE_HEATING = 3

HEAT_MODES = {
    HEAT_MODE_STOP: "Off",
    HEAT_MODE_AUTO: "Auto",
    HEAT_MODE_COOLING: "Cooling",
    HEAT_MODE_HEATING: "Heating",
}

# Human-readable output mode labels (int → label)
OUTPUT_MODES = {
    OUT_MODE_MAN: "Manual",
    OUT_MODE_TIME_SLOTS: "Time Slots",
    OUT_MODE_TIMER: "Timer",
    OUT_MODE_REGUL: "Regulation",
    OUT_MODE_FILTRATION_SYNC: "Filtration Sync",
    OUT_MODE_MAINTENANCE: "Maintenance",
    OUT_MODE_PULSE: "Pulse",
    OUT_MODE_AUTOMATIC: "Automatic",
}


class KlereoApiError(Exception):
    """Error from the Klereo API."""


class KlereoApi:
    """Klereo API Client."""

    def __init__(self, username: str, password_hash: str, session: aiohttp.ClientSession):
        """Initialize the API client.

        Args:
            password_hash: SHA-1 hex digest of the password.
        """
        self._username = username
        self._password_hash = password_hash
        self._session = session
        self._token: str | None = None
        self._auth_lock = asyncio.Lock()

    async def login(self) -> None:
        """Authenticate with the Klereo API and obtain a JWT token."""
        _LOGGER.debug("Logging in to Klereo API")
        try:
            async with asyncio.timeout(TIMEOUT):
                response = await self._session.post(
                    API_URL_LOGIN,
                    data={
                        "login": self._username,
                        "password": self._password_hash,
                        "version": API_VERSION,
                    },
                    headers={
                        "User-Agent": USER_AGENT,
                        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    },
                )
                response.raise_for_status()
                data = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.error("Error connecting to Klereo API: %s", err)
            raise

        if "jwt" in data:
            self._token = data["jwt"]
        elif "token" in data:
            self._token = data["token"]
        else:
            _LOGGER.error("Login failed: no token in API response")
            _LOGGER.debug("Login response body: %s", data)
            raise KlereoApiError("Login failed: no token returned")

    async def _get_auth_header(self) -> dict[str, str]:
        """Get the authorization header, logging in if necessary."""
        if not self._token:
            async with self._auth_lock:
                if not self._token:
                    await self.login()
        return {
            "Authorization": f"Bearer {self._token}",
            "User-Agent": USER_AGENT,
        }

    async def _parse_response(self, response: aiohttp.ClientResponse, url: str) -> Any:
        """Parse and validate a JSON response from the API."""
        response.raise_for_status()
        text = await response.text()
        try:
            return json.loads(text)
        except json.JSONDecodeError as err:
            _LOGGER.error("Invalid JSON from %s: %.200s", url, text)
            raise KlereoApiError(f"Invalid JSON response from {url}") from err

    async def _request_with_retry(self, method: str, url: str, **kwargs: Any) -> Any:
        """Make an API request, retrying on 401 and transient errors."""
        headers = await self._get_auth_header()
        try:
            async with asyncio.timeout(TIMEOUT):
                response = await self._session.request(
                    method, url, headers=headers, **kwargs
                )
                return await self._parse_response(response, url)
        except aiohttp.ClientResponseError as err:
            if err.status == 401:
                _LOGGER.debug("Token expired, re-authenticating")
                self._token = None
                headers = await self._get_auth_header()
                async with asyncio.timeout(TIMEOUT):
                    response = await self._session.request(
                        method, url, headers=headers, **kwargs
                    )
                    return await self._parse_response(response, url)
            raise
        except (aiohttp.ClientConnectionError, TimeoutError) as err:
            _LOGGER.debug("Transient error on %s, retrying once: %s", url, err)
            await asyncio.sleep(2)
            headers = await self._get_auth_header()
            async with asyncio.timeout(TIMEOUT):
                response = await self._session.request(
                    method, url, headers=headers, **kwargs
                )
                return await self._parse_response(response, url)

    async def get_systems(self) -> Any:
        """Get list of pool systems."""
        return await self._request_with_retry("GET", API_URL_GET_INDEX)

    async def get_pool_details(self, system_id: str) -> Any:
        """Get details for a specific pool system."""
        return await self._request_with_retry(
            "POST", API_URL_GET_POOL_DETAILS, data={"poolID": system_id}
        )

    async def set_output(
        self, system_id: str, out_index: int, mode: int, state: int
    ) -> Any:
        """Set an output state.

        Args:
            system_id: The pool system ID.
            out_index: Output index (0-15).
            mode: Output mode (OUT_MODE_MAN=0, OUT_MODE_TIME_SLOTS=1, etc.) —
                except on OUT_IDX_HEATING, where it is a HEAT_MODE_* value.
            state: Output state (OUT_STATE_OFF=0, OUT_STATE_ON=1,
                OUT_STATE_AUTO=2 for any non-Manual mode).
        """
        return await self._request_with_retry(
            "POST",
            API_URL_SET_OUT,
            data={
                "poolID": system_id,
                "outIdx": out_index,
                "newMode": mode,
                "newState": state,
                "comMode": API_COM_MODE,
            },
        )

    async def command_status(self, cmd_id: Any) -> Any:
        """Ask what became of a queued command.

        Args:
            cmd_id: The cmdID returned by `set_output` or `set_param`.
        """
        return await self._request_with_retry(
            "POST",
            API_URL_COMMAND_STATUS,
            data={"cmdID": cmd_id, "comMode": API_COM_MODE},
        )

    async def set_param(self, system_id: str, param_id: str, value: Any) -> Any:
        """Set a parameter value.

        Args:
            system_id: The pool system ID.
            param_id: Parameter identifier (e.g. "ConsigneEau").
            value: New value to set.
        """
        return await self._request_with_retry(
            "POST",
            API_URL_SET_PARAM,
            data={
                "poolID": system_id,
                "paramID": param_id,
                "newValue": value,
                "comMode": API_COM_MODE,
            },
        )
