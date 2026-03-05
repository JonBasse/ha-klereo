"""Tests for Klereo diagnostics."""
from unittest.mock import MagicMock

from custom_components.klereo.diagnostics import (
    TO_REDACT,
    async_get_config_entry_diagnostics,
)


class TestDiagnostics:
    """Tests for diagnostics output."""

    async def test_returns_config_and_coordinator_data(self):
        """Should include both config_entry and coordinator_data sections."""
        hass = MagicMock()
        entry = MagicMock()
        entry.as_dict.return_value = {
            "data": {"username": "test@example.com", "password": "secret_hash"},
            "options": {},
        }
        coordinator = MagicMock()
        coordinator.data = {
            "SYS1": {
                "info": {"idSystem": "SYS1", "poolNickname": "My Pool"},
                "details": {"probes": []},
            }
        }
        hass.data = {"klereo": {entry.entry_id: coordinator}}

        result = await async_get_config_entry_diagnostics(hass, entry)
        assert "config_entry" in result
        assert "coordinator_data" in result

    async def test_redacts_sensitive_fields(self):
        """Password and token fields should be redacted."""
        hass = MagicMock()
        entry = MagicMock()
        entry.as_dict.return_value = {
            "data": {"password": "secret", "jwt": "tok123", "login": "user"},
            "options": {},
        }
        coordinator = MagicMock()
        coordinator.data = {"token": "should_be_redacted"}
        hass.data = {"klereo": {entry.entry_id: coordinator}}

        result = await async_get_config_entry_diagnostics(hass, entry)
        config = result["config_entry"]
        assert config["data"]["password"] == "**REDACTED**"
        assert config["data"]["jwt"] == "**REDACTED**"
        assert config["data"]["login"] == "**REDACTED**"

    def test_to_redact_contains_expected_keys(self):
        """TO_REDACT should include all sensitive field names."""
        assert "password" in TO_REDACT
        assert "jwt" in TO_REDACT
        assert "token" in TO_REDACT
        assert "login" in TO_REDACT
