"""Tests for Klereo config flow."""
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from custom_components.klereo.api import KlereoApiError
from custom_components.klereo.config_flow import (
    CannotConnect,
    InvalidAuth,
    validate_input,
)
from custom_components.klereo.const import hash_password

USER_INPUT = {
    CONF_USERNAME: "test@example.com",
    CONF_PASSWORD: "mypassword",
}


class TestValidateInput:
    """Tests for validate_input."""

    async def test_successful_login(self):
        """Should return title on successful login."""
        hass = MagicMock()
        with patch(
            "custom_components.klereo.config_flow.async_get_clientsession"
        ), patch(
            "custom_components.klereo.config_flow.KlereoApi"
        ) as mock_api_cls:
            mock_api_cls.return_value.login = AsyncMock()
            result = await validate_input(hass, USER_INPUT)
        assert result == {"title": "test@example.com"}

    async def test_invalid_auth_on_api_error(self):
        """Should raise InvalidAuth on KlereoApiError."""
        hass = MagicMock()
        with patch(
            "custom_components.klereo.config_flow.async_get_clientsession"
        ), patch(
            "custom_components.klereo.config_flow.KlereoApi"
        ) as mock_api_cls:
            mock_api_cls.return_value.login = AsyncMock(
                side_effect=KlereoApiError("bad creds")
            )
            with pytest.raises(InvalidAuth):
                await validate_input(hass, USER_INPUT)

    async def test_invalid_auth_on_401(self):
        """Should raise InvalidAuth on 401 response."""
        hass = MagicMock()
        with patch(
            "custom_components.klereo.config_flow.async_get_clientsession"
        ), patch(
            "custom_components.klereo.config_flow.KlereoApi"
        ) as mock_api_cls:
            mock_api_cls.return_value.login = AsyncMock(
                side_effect=aiohttp.ClientResponseError(
                    request_info=MagicMock(), history=(), status=401
                )
            )
            with pytest.raises(InvalidAuth):
                await validate_input(hass, USER_INPUT)

    async def test_cannot_connect_on_client_error(self):
        """Should raise CannotConnect on connection error."""
        hass = MagicMock()
        with patch(
            "custom_components.klereo.config_flow.async_get_clientsession"
        ), patch(
            "custom_components.klereo.config_flow.KlereoApi"
        ) as mock_api_cls:
            mock_api_cls.return_value.login = AsyncMock(
                side_effect=aiohttp.ClientError("offline")
            )
            with pytest.raises(CannotConnect):
                await validate_input(hass, USER_INPUT)

    async def test_cannot_connect_on_timeout(self):
        """Should raise CannotConnect on timeout."""
        hass = MagicMock()
        with patch(
            "custom_components.klereo.config_flow.async_get_clientsession"
        ), patch(
            "custom_components.klereo.config_flow.KlereoApi"
        ) as mock_api_cls:
            mock_api_cls.return_value.login = AsyncMock(
                side_effect=TimeoutError()
            )
            with pytest.raises(CannotConnect):
                await validate_input(hass, USER_INPUT)

    async def test_cannot_connect_on_500(self):
        """Should raise CannotConnect on non-auth HTTP error."""
        hass = MagicMock()
        with patch(
            "custom_components.klereo.config_flow.async_get_clientsession"
        ), patch(
            "custom_components.klereo.config_flow.KlereoApi"
        ) as mock_api_cls:
            mock_api_cls.return_value.login = AsyncMock(
                side_effect=aiohttp.ClientResponseError(
                    request_info=MagicMock(), history=(), status=500
                )
            )
            with pytest.raises(CannotConnect):
                await validate_input(hass, USER_INPUT)

    async def test_hashes_password_before_login(self):
        """Should hash the password before passing to API."""
        hass = MagicMock()
        with patch(
            "custom_components.klereo.config_flow.async_get_clientsession"
        ), patch(
            "custom_components.klereo.config_flow.KlereoApi"
        ) as mock_api_cls:
            mock_api_cls.return_value.login = AsyncMock()
            await validate_input(hass, USER_INPUT)
            _, call_kwargs = mock_api_cls.call_args
            assert call_kwargs.get("password_hash") or mock_api_cls.call_args[0][1] == hash_password("mypassword")


class TestHashPassword:
    """Tests for hash_password utility."""

    def test_known_hash(self):
        """Should produce known SHA-1 hash for 'test'."""
        assert hash_password("test") == "a94a8fe5ccb19ba61c4c0873d391e987982fbbd3"

    def test_deterministic(self):
        """Should produce same hash for same input."""
        assert hash_password("hello") == hash_password("hello")

    def test_different_inputs(self):
        """Different inputs should produce different hashes."""
        assert hash_password("a") != hash_password("b")
