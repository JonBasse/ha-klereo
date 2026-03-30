"""Tests for Klereo switch entities."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.klereo.api import OUT_MODE_MAN, OUT_STATE_OFF, OUT_STATE_ON
from custom_components.klereo.models import (
    KlereoOutput,
    KlereoPoolDetails,
    KlereoSystemData,
    KlereoSystemInfo,
)
from custom_components.klereo.switch import KlereoSwitch


def _make_output(**kwargs) -> KlereoOutput:
    """Create a KlereoOutput with defaults."""
    defaults = {"index": 0, "status": 1, "mode": 0, "type": 0}
    defaults.update(kwargs)
    return KlereoOutput(**defaults)


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator."""
    output = _make_output()
    coordinator = MagicMock()
    coordinator.api = AsyncMock()
    coordinator.api.set_output.return_value = {"response": "ok"}
    coordinator.async_request_refresh = AsyncMock()
    coordinator.async_set_output = AsyncMock()
    coordinator.data = {
        "SYS1": KlereoSystemData(
            info=KlereoSystemInfo(id_system="SYS1", pool_nickname="My Pool"),
            details=KlereoPoolDetails(
                probes=[],
                outs=[output],
                regul_modes={},
                probe_index={},
                output_index={0: output},
            ),
        )
    }
    return coordinator


class TestKlereoSwitch:
    """Tests for KlereoSwitch."""

    def test_creates_with_known_index(self, mock_coordinator):
        """Should use OUTPUT_NAMES for known indices."""
        output = _make_output()
        switch = KlereoSwitch(mock_coordinator, "SYS1", output)
        assert switch._attr_name == "Lighting"
        assert switch._attr_unique_id == "SYS1_output_0"

    def test_is_on_when_status_equals_one(self, mock_coordinator):
        """Should be ON when status == OUT_STATE_ON (1)."""
        output = _make_output(status=1)
        switch = KlereoSwitch(mock_coordinator, "SYS1", output)
        assert switch._attr_is_on is True

    def test_is_off_when_status_equals_zero(self, mock_coordinator):
        """Should be OFF when status == 0."""
        output = _make_output(status=0)
        switch = KlereoSwitch(mock_coordinator, "SYS1", output)
        assert switch._attr_is_on is False

    def test_is_on_when_status_is_string_one(self, mock_coordinator):
        """Should be ON when status is string '1' (API may return strings)."""
        output = _make_output(status="1")
        switch = KlereoSwitch(mock_coordinator, "SYS1", output)
        assert switch._attr_is_on is True

    def test_is_off_when_status_is_string_zero(self, mock_coordinator):
        """Should be OFF when status is string '0'."""
        output = _make_output(status="0")
        switch = KlereoSwitch(mock_coordinator, "SYS1", output)
        assert switch._attr_is_on is False

    def test_is_off_when_status_is_none(self, mock_coordinator):
        """Should be OFF when status is None."""
        output = _make_output(status=None)
        switch = KlereoSwitch(mock_coordinator, "SYS1", output)
        assert switch._attr_is_on is False

    async def test_turn_on_calls_api(self, mock_coordinator):
        """turn_on should call async_set_output with correct args."""
        output = _make_output(status=0)
        switch = KlereoSwitch(mock_coordinator, "SYS1", output)
        switch.async_write_ha_state = MagicMock()
        await switch.async_turn_on()
        mock_coordinator.async_set_output.assert_called_once_with(
            "SYS1", 0, OUT_MODE_MAN, OUT_STATE_ON
        )
        assert switch._attr_is_on is True

    async def test_turn_off_calls_api(self, mock_coordinator):
        """turn_off should call async_set_output with correct args."""
        output = _make_output(status=1)
        switch = KlereoSwitch(mock_coordinator, "SYS1", output)
        switch.async_write_ha_state = MagicMock()
        await switch.async_turn_off()
        mock_coordinator.async_set_output.assert_called_once_with(
            "SYS1", 0, OUT_MODE_MAN, OUT_STATE_OFF
        )
        assert switch._attr_is_on is False

    async def test_turn_on_error_raises_ha_error(self, mock_coordinator):
        """turn_on should raise HomeAssistantError on coordinator failure."""
        from homeassistant.exceptions import HomeAssistantError
        mock_coordinator.async_set_output.side_effect = HomeAssistantError("Failed to set output 0: API down")
        output = _make_output(status=0)
        switch = KlereoSwitch(mock_coordinator, "SYS1", output)
        switch.async_write_ha_state = MagicMock()
        with pytest.raises(HomeAssistantError, match="Failed to set output"):
            await switch.async_turn_on()

    def test_find_my_output_uses_index(self, mock_coordinator):
        """Should find output data via output_index."""
        output = _make_output()
        switch = KlereoSwitch(mock_coordinator, "SYS1", output)
        found = switch._find_my_output()
        assert found is not None
        assert found.status == 1
