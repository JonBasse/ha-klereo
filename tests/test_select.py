"""Tests for Klereo select entities."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.klereo.api import (
    OUT_MODE_TIME_SLOTS,
    OUT_MODE_TIMER,
    OUT_STATE_ON,
)
from custom_components.klereo.select import KlereoOutputModeSelect


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator."""
    coordinator = MagicMock()
    coordinator.async_set_output = AsyncMock()
    coordinator.data = {
        "SYS1": {
            "info": {"idSystem": "SYS1", "poolNickname": "My Pool"},
            "details": {
                "outs": [{"index": 0, "status": 1, "mode": 0, "type": 0}],
                "_output_index": {
                    0: {"index": 0, "status": 1, "mode": 0, "type": 0},
                },
            },
        }
    }
    return coordinator


class TestKlereoOutputModeSelect:
    """Tests for KlereoOutputModeSelect."""

    def test_creates_with_known_index(self, mock_coordinator):
        """Should use OUTPUT_NAMES for known indices with ' Mode' suffix."""
        output = {"index": 0, "status": 1, "mode": 0, "type": 0}
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", output)
        assert select._attr_name == "Lighting Mode"
        assert select._attr_unique_id == "SYS1_output_mode_0"

    def test_creates_with_unknown_index(self, mock_coordinator):
        """Should fall back to 'Output N Mode' for unknown indices."""
        output = {"index": 99, "status": 0, "mode": 0, "type": 0}
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", output)
        assert select._attr_name == "Output 99 Mode"

    def test_options_list(self, mock_coordinator):
        """Should expose all four mode options."""
        output = {"index": 0, "status": 0, "mode": 0, "type": 0}
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", output)
        assert select._attr_options == ["Manual", "Time Slots", "Timer", "Regulation"]

    def test_current_option_manual(self, mock_coordinator):
        """Should read 'Manual' from mode=0."""
        output = {"index": 0, "status": 1, "mode": 0, "type": 0}
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", output)
        assert select._attr_current_option == "Manual"

    def test_current_option_timer(self, mock_coordinator):
        """Should read 'Timer' from mode=2."""
        output = {"index": 0, "status": 1, "mode": 2, "type": 0}
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", output)
        assert select._attr_current_option == "Timer"

    def test_current_option_string_mode(self, mock_coordinator):
        """Should handle string mode values from API."""
        output = {"index": 0, "status": 1, "mode": "3", "type": 0}
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", output)
        assert select._attr_current_option == "Regulation"

    def test_current_option_none_defaults_manual(self, mock_coordinator):
        """Should default to Manual when mode is None."""
        output = {"index": 0, "status": 1, "mode": None, "type": 0}
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", output)
        assert select._attr_current_option == "Manual"

    async def test_select_option_preserves_state(self, mock_coordinator):
        """Should send new mode with current ON/OFF state preserved."""
        output = {"index": 0, "status": 1, "mode": 0, "type": 0}
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", output)
        select.async_write_ha_state = MagicMock()
        await select.async_select_option("Timer")
        mock_coordinator.async_set_output.assert_called_once_with(
            "SYS1", 0, OUT_MODE_TIMER, OUT_STATE_ON
        )
        assert select._attr_current_option == "Timer"

    async def test_select_option_off_state(self, mock_coordinator):
        """Should preserve OFF state when changing mode."""
        mock_coordinator.data["SYS1"]["details"]["_output_index"][0]["status"] = 0
        output = {"index": 0, "status": 0, "mode": 0, "type": 0}
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", output)
        select.async_write_ha_state = MagicMock()
        await select.async_select_option("Time Slots")
        mock_coordinator.async_set_output.assert_called_once_with(
            "SYS1", 0, OUT_MODE_TIME_SLOTS, 0
        )

    def test_handle_coordinator_update_refreshes(self, mock_coordinator):
        """Should update current option from coordinator data."""
        output = {"index": 0, "status": 1, "mode": 0, "type": 0}
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", output)
        select.async_write_ha_state = MagicMock()
        mock_coordinator.data["SYS1"]["details"]["_output_index"][0]["mode"] = 3
        select._handle_coordinator_update()
        assert select._attr_current_option == "Regulation"
        assert select._attr_available is True

    def test_handle_coordinator_update_missing_system(self, mock_coordinator):
        """Should mark unavailable when system disappears."""
        output = {"index": 0, "status": 1, "mode": 0, "type": 0}
        select = KlereoOutputModeSelect(mock_coordinator, "MISSING", output)
        select.async_write_ha_state = MagicMock()
        select._handle_coordinator_update()
        assert select._attr_available is False

    def test_device_info(self, mock_coordinator):
        """Should return device info from coordinator data."""
        output = {"index": 0, "status": 1, "mode": 0, "type": 0}
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", output)
        info = select.device_info
        assert ("klereo", "SYS1") in info["identifiers"]
        assert info["name"] == "My Pool"

    async def test_select_option_error_propagates(self, mock_coordinator):
        """Should propagate HomeAssistantError from coordinator."""
        from homeassistant.exceptions import HomeAssistantError
        mock_coordinator.async_set_output.side_effect = HomeAssistantError("Failed to set output 0: API down")
        output = {"index": 0, "status": 1, "mode": 0, "type": 0}
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", output)
        select.async_write_ha_state = MagicMock()
        with pytest.raises(HomeAssistantError, match="Failed to set output"):
            await select.async_select_option("Regulation")
