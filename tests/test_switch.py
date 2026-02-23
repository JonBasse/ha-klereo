"""Tests for Klereo switch entities."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.klereo.switch import KlereoSwitch
from custom_components.klereo.const import OUT_MODE_MAN, OUT_STATE_ON, OUT_STATE_OFF


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator."""
    coordinator = MagicMock()
    coordinator.api = AsyncMock()
    coordinator.api.set_output.return_value = {"response": "ok"}
    coordinator.async_request_refresh = AsyncMock()
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


class TestKlereoSwitch:
    """Tests for KlereoSwitch."""

    def test_creates_with_known_index(self, mock_coordinator):
        """Should use OUTPUT_NAMES for known indices."""
        output = {"index": 0, "status": 1, "mode": 0, "type": 0}
        switch = KlereoSwitch(mock_coordinator, "SYS1", output)
        assert switch._attr_name == "Lighting"
        assert switch._attr_unique_id == "SYS1_output_0"

    def test_is_on_when_status_equals_one(self, mock_coordinator):
        """Should be ON when status == OUT_STATE_ON (1)."""
        output = {"index": 0, "status": 1, "mode": 0, "type": 0}
        switch = KlereoSwitch(mock_coordinator, "SYS1", output)
        assert switch._attr_is_on is True

    def test_is_off_when_status_equals_zero(self, mock_coordinator):
        """Should be OFF when status == 0."""
        output = {"index": 0, "status": 0, "mode": 0, "type": 0}
        switch = KlereoSwitch(mock_coordinator, "SYS1", output)
        assert switch._attr_is_on is False

    def test_is_off_when_status_is_string_zero(self, mock_coordinator):
        """Should be OFF when status is string '0'."""
        output = {"index": 0, "status": "0", "mode": 0, "type": 0}
        switch = KlereoSwitch(mock_coordinator, "SYS1", output)
        assert switch._attr_is_on is False

    def test_is_off_when_status_is_none(self, mock_coordinator):
        """Should be OFF when status is None."""
        output = {"index": 0, "status": None, "mode": 0, "type": 0}
        switch = KlereoSwitch(mock_coordinator, "SYS1", output)
        assert switch._attr_is_on is False

    async def test_turn_on_calls_api(self, mock_coordinator):
        """turn_on should call set_output with correct args."""
        output = {"index": 0, "status": 0, "mode": 0, "type": 0}
        switch = KlereoSwitch(mock_coordinator, "SYS1", output)
        switch.async_write_ha_state = MagicMock()
        await switch.async_turn_on()
        mock_coordinator.api.set_output.assert_called_once_with(
            "SYS1", 0, OUT_MODE_MAN, OUT_STATE_ON
        )
        assert switch._attr_is_on is True

    async def test_turn_off_calls_api(self, mock_coordinator):
        """turn_off should call set_output with correct args."""
        output = {"index": 0, "status": 1, "mode": 0, "type": 0}
        switch = KlereoSwitch(mock_coordinator, "SYS1", output)
        switch.async_write_ha_state = MagicMock()
        await switch.async_turn_off()
        mock_coordinator.api.set_output.assert_called_once_with(
            "SYS1", 0, OUT_MODE_MAN, OUT_STATE_OFF
        )
        assert switch._attr_is_on is False

    async def test_turn_on_error_raises_ha_error(self, mock_coordinator):
        """turn_on should raise HomeAssistantError on API failure."""
        from homeassistant.exceptions import HomeAssistantError
        mock_coordinator.api.set_output.side_effect = Exception("API down")
        output = {"index": 0, "status": 0, "mode": 0, "type": 0}
        switch = KlereoSwitch(mock_coordinator, "SYS1", output)
        switch.async_write_ha_state = MagicMock()
        with pytest.raises(HomeAssistantError, match="Failed to turn on"):
            await switch.async_turn_on()

    def test_find_my_data_uses_index(self, mock_coordinator):
        """Should find output data via _output_index."""
        output = {"index": 0, "status": 1, "mode": 0, "type": 0}
        switch = KlereoSwitch(mock_coordinator, "SYS1", output)
        found = switch._find_my_data()
        assert found is not None
        assert found["status"] == 1
