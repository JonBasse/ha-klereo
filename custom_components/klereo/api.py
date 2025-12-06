"""API Client for Klereo."""
import logging
import aiohttp
import async_timeout

from .const import (
    API_URL_LOGIN,
    API_URL_GET_INDEX,
    API_URL_GET_POOL_DETAILS,
    API_URL_SET_OUT,
    API_URL_SET_PARAM,
)

_LOGGER = logging.getLogger(__name__)

class KlereoApi:
    """Klereo API Client."""

    def __init__(self, username, password, session: aiohttp.ClientSession):
        """Initialize the API client."""
        self._username = username
        self._password = password
        self._session = session
        self._token = None

    async def _get_auth_header(self):
        """Get the authorization header, logging in if necessary."""
        if not self._token:
            await self.login()
        return {"Authorization": f"Bearer {self._token}", "User-Agent": "Home Assistant Klereo Integration"}

import hashlib

    async def login(self):
        """Authenticate with the Klereo API."""
        _LOGGER.debug("Logging in to Klereo API")
        try:
            # SHA1 encrypt password
            hashed_password = hashlib.sha1(self._password.encode("utf-8")).hexdigest()
            
            async with async_timeout.timeout(10):
                # Using form data with SHA1 password and extra parameters as found in community forum
                data = {
                    "login": self._username,
                    "password": hashed_password,
                    "version": "391-H",
                    "app": "Api"
                }
                
                response = await self._session.post(
                    API_URL_LOGIN,
                    data=data,
                    headers={
                        "User-Agent": "Home Assistant Klereo Integration",
                        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
                    }
                )
                response.raise_for_status()
                data = await response.json(content_type=None)
                
                # Check for success - the API returns the token directly or in a structure
                # Based on analysis, it returns a JWT token string or object.
                # Assuming it returns a JSON with key 'token' or similar, 
                # OR raw string if it's a simple JWT return.
                # Let's inspect the response structure based on common practices or re-check if needed.
                # The Jeedom code does: $result = json_decode($result, true); if (isset($result['token'])) ...
                
                if "token" in data:
                    self._token = data["token"]
                else:
                    _LOGGER.error(f"Login failed, no token found in response: {data}")
                    raise Exception("Login failed: No token returned")
                    
        except aiohttp.ClientError as err:
            _LOGGER.error(f"Error connecting to Klereo API: {err}")
            raise

    async def get_systems(self):
        """Get list of systems."""
        headers = await self._get_auth_header()
        try:
            async with async_timeout.timeout(10):
                response = await self._session.get(API_URL_GET_INDEX, headers=headers)
                response.raise_for_status()
                return await response.json(content_type=None)
        except aiohttp.ClientResponseError as err:
            if err.status == 401: # Token expired
                self._token = None
                headers = await self._get_auth_header() # Retry login
                async with async_timeout.timeout(10):
                    response = await self._session.get(API_URL_GET_INDEX, headers=headers)
                    response.raise_for_status()
                    return await response.json(content_type=None)
            raise

    async def get_pool_details(self, system_id):
        """Get details for a specific pool."""
        headers = await self._get_auth_header()
        try:
            async with async_timeout.timeout(10):
                response = await self._session.post(
                    API_URL_GET_POOL_DETAILS,
                    data={"idSystem": system_id},
                    headers=headers
                )
                response.raise_for_status()
                return await response.json(content_type=None)
        except aiohttp.ClientResponseError as err:
             if err.status == 401:
                self._token = None
                headers = await self._get_auth_header()
                async with async_timeout.timeout(10):
                    response = await self._session.post(
                        API_URL_GET_POOL_DETAILS,
                        data={"idSystem": system_id},
                        headers=headers
                    )
                    response.raise_for_status()
                    return await response.json(content_type=None)
             raise

    async def set_output(self, system_id, out_number, mode, state, off_delay=0):
        """Set an output state."""
        headers = await self._get_auth_header()
        data = {
            "idSystem": system_id,
            "outNumber": out_number,
            "mode": mode,
            "state": state,
            "offDelay": off_delay
        }
        async with async_timeout.timeout(10):
            response = await self._session.post(API_URL_SET_OUT, data=data, headers=headers)
            response.raise_for_status()
            return await response.json(content_type=None)

    async def set_param(self, system_id, param_number, value):
        """Set a parameter value."""
        headers = await self._get_auth_header()
        data = {
            "idSystem": system_id,
            "parNumber": param_number,
            "consigne": value
        }
        async with async_timeout.timeout(10):
            response = await self._session.post(API_URL_SET_PARAM, data=data, headers=headers)
            response.raise_for_status()
            return await response.json(content_type=None)
