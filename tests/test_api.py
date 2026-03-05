"""Tests for the Klereo API client."""
import json
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.klereo.api import KlereoApi, KlereoApiError


@pytest.fixture
def mock_session():
    """Create a mock aiohttp session.

    We avoid spec=aiohttp.ClientSession because aiohttp's .post() and
    .request() return context managers, not coroutines.  The code under
    test awaits them directly (``await session.post(...)``), so we need
    AsyncMock children that return our fake responses when awaited.
    """
    session = MagicMock()
    session.post = AsyncMock()
    session.request = AsyncMock()
    return session


@pytest.fixture
def api(mock_session):
    """Create a KlereoApi instance with mock session."""
    return KlereoApi("test@example.com", "a94a8fe5ccb19ba61c4c0873d391e987982fbbd3", mock_session)


def _make_response(data, status=200):
    """Create a mock response."""
    response = AsyncMock()
    response.status = status
    response.raise_for_status = MagicMock()
    if status >= 400:
        response.raise_for_status.side_effect = aiohttp.ClientResponseError(
            request_info=MagicMock(), history=(), status=status
        )
    response.json = AsyncMock(return_value=data)
    response.text = AsyncMock(return_value=json.dumps(data))
    return response


class TestLogin:
    """Tests for the login method."""

    async def test_login_extracts_jwt(self, api, mock_session):
        """Login should extract JWT from 'jwt' key."""
        mock_session.post.return_value = _make_response({"jwt": "my-token"})
        await api.login()
        assert api._token == "my-token"

    async def test_login_extracts_token_key(self, api, mock_session):
        """Login should fall back to 'token' key."""
        mock_session.post.return_value = _make_response({"token": "alt-token"})
        await api.login()
        assert api._token == "alt-token"

    async def test_login_no_token_raises(self, api, mock_session):
        """Login should raise KlereoApiError when no token in response."""
        mock_session.post.return_value = _make_response({"error": "bad"})
        with pytest.raises(KlereoApiError, match="no token"):
            await api.login()

    async def test_login_sends_hashed_password(self, api, mock_session):
        """Login should send the pre-hashed password."""
        mock_session.post.return_value = _make_response({"jwt": "tok"})
        await api.login()
        call_kwargs = mock_session.post.call_args
        assert call_kwargs.kwargs["data"]["password"] == "a94a8fe5ccb19ba61c4c0873d391e987982fbbd3"


class TestRequestWithRetry:
    """Tests for _request_with_retry."""

    async def test_successful_request(self, api, mock_session):
        """Successful request returns parsed JSON."""
        api._token = "valid-token"
        mock_session.request.return_value = _make_response({"data": "value"})
        result = await api._request_with_retry("GET", "https://example.com/api")
        assert result == {"data": "value"}

    async def test_401_triggers_reauth(self, api, mock_session):
        """401 response should trigger re-authentication and retry."""
        api._token = "expired-token"

        # First call fails with 401 (raise_for_status raises ClientResponseError)
        fail_response = _make_response({}, status=401)
        success_response = _make_response({"data": "value"})

        # Login response for re-auth
        login_response = _make_response({"jwt": "new-token"})

        mock_session.request.side_effect = [fail_response, success_response]
        mock_session.post.return_value = login_response

        result = await api._request_with_retry("GET", "https://example.com/api")
        assert result == {"data": "value"}
        assert api._token == "new-token"

    async def test_transient_error_retries(self, api, mock_session):
        """ConnectionError should retry once after 2s backoff."""
        api._token = "valid-token"
        success_response = _make_response({"data": "ok"})
        mock_session.request.side_effect = [
            aiohttp.ClientConnectionError("connection lost"),
            success_response,
        ]
        result = await api._request_with_retry("GET", "https://example.com/api")
        assert result == {"data": "ok"}
        assert mock_session.request.call_count == 2

    async def test_transient_error_retry_fails(self, api, mock_session):
        """If retry also fails with transient error, exception propagates."""
        api._token = "valid-token"
        mock_session.request.side_effect = aiohttp.ClientConnectionError("still broken")
        with pytest.raises(aiohttp.ClientConnectionError):
            await api._request_with_retry("GET", "https://example.com/api")

    async def test_non_401_http_error_propagates(self, api, mock_session):
        """Non-401 HTTP errors should propagate without retry."""
        api._token = "valid-token"
        mock_session.request.return_value = _make_response({}, status=500)
        with pytest.raises(aiohttp.ClientResponseError):
            await api._request_with_retry("GET", "https://example.com/api")


class TestParseResponse:
    """Tests for _parse_response."""

    async def test_valid_json(self, api):
        """Valid JSON response should be parsed."""
        response = _make_response({"key": "value"})
        result = await api._parse_response(response, "https://example.com")
        assert result == {"key": "value"}

    async def test_invalid_json_raises(self, api):
        """Invalid JSON should raise KlereoApiError."""
        response = AsyncMock()
        response.raise_for_status = MagicMock()
        response.text = AsyncMock(return_value="not json at all")
        with pytest.raises(KlereoApiError, match="Invalid JSON"):
            await api._parse_response(response, "https://example.com")

    async def test_http_error_raises(self, api):
        """Non-200 status should raise ClientResponseError via raise_for_status."""
        response = _make_response({}, status=503)
        with pytest.raises(aiohttp.ClientResponseError):
            await api._parse_response(response, "https://example.com")
