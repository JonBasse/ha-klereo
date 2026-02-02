"""API Client for Klereo."""
import asyncio
import hashlib
import logging

import aiohttp

from .const import (
    API_URL_LOGIN,
    API_URL_GET_INDEX,
    API_URL_GET_POOL_DETAILS,
    API_URL_SET_OUT,
    API_URL_SET_PARAM,
)

_LOGGER = logging.getLogger(__name__)

TIMEOUT = 10
USER_AGENT = "Jeedom plugin"


class KlereoApiError(Exception):
    """Error from the Klereo API."""


class KlereoApi:
    """Klereo API Client."""

    def __init__(self, username: str, password: str, session: aiohttp.ClientSession):
        """Initialize the API client."""
        self._username = username
        self._password = password
        self._session = session
        self._token: str | None = None

    async def login(self):
        """Authenticate with the Klereo API and obtain a JWT token."""
        _LOGGER.debug("Logging in to Klereo API")
        hashed_password = hashlib.sha1(self._password.encode("utf-8")).hexdigest()
        try:
            async with asyncio.timeout(TIMEOUT):
                response = await self._session.post(
                    API_URL_LOGIN,
                    data={
                        "login": self._username,
                        "password": hashed_password,
                        "version": "393-J",
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
            _LOGGER.error("Login failed, no token in response: %s", data)
            raise KlereoApiError("Login failed: no token returned")

    async def _get_auth_header(self) -> dict[str, str]:
        """Get the authorization header, logging in if necessary."""
        if not self._token:
            await self.login()
        return {
            "Authorization": f"Bearer {self._token}",
            "User-Agent": USER_AGENT,
        }

    async def _request_with_retry(self, method: str, url: str, **kwargs):
        """Make an API request, retrying once on 401 (expired token)."""
        headers = await self._get_auth_header()
        try:
            async with asyncio.timeout(TIMEOUT):
                response = await self._session.request(
                    method, url, headers=headers, **kwargs
                )
                response.raise_for_status()
                return await response.json(content_type=None)
        except aiohttp.ClientResponseError as err:
            if err.status == 401:
                _LOGGER.debug("Token expired, re-authenticating")
                self._token = None
                headers = await self._get_auth_header()
                async with asyncio.timeout(TIMEOUT):
                    response = await self._session.request(
                        method, url, headers=headers, **kwargs
                    )
                    response.raise_for_status()
                    return await response.json(content_type=None)
            raise

    async def get_systems(self):
        """Get list of pool systems."""
        return await self._request_with_retry("GET", API_URL_GET_INDEX)

    async def get_pool_details(self, system_id: str):
        """Get details for a specific pool system."""
        return await self._request_with_retry(
            "POST", API_URL_GET_POOL_DETAILS, data={"poolID": system_id}
        )

    async def set_output(
        self, system_id: str, out_index: int, mode: int, state: int
    ):
        """Set an output state.

        Args:
            system_id: The pool system ID.
            out_index: Output index (0-15).
            mode: Output mode (OUT_MODE_MAN=0, OUT_MODE_TIME_SLOTS=1, etc.).
            state: Output state (OUT_STATE_OFF=0, OUT_STATE_ON=1).
        """
        return await self._request_with_retry(
            "POST",
            API_URL_SET_OUT,
            data={
                "poolID": system_id,
                "outIdx": out_index,
                "newMode": mode,
                "newState": state,
                "comMode": 1,
            },
        )

    async def set_param(self, system_id: str, param_id: str, value):
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
                "comMode": 1,
            },
        )
