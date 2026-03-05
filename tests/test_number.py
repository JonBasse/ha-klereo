"""Tests for Klereo number entities."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.klereo.number import KlereoNumber


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator."""
    coordinator = MagicMock()
    coordinator.async_set_param = AsyncMock()
    coordinator.data = {
        "SYS1": {
            "info": {"idSystem": "SYS1", "poolNickname": "My Pool"},
            "details": {
                "RegulModes": {"ConsigneEau": 28, "ModeFiltration": 1},
            },
        }
    }
    return coordinator


class TestKlereoNumber:
    """Tests for KlereoNumber."""

    def test_creates_with_param_type(self, mock_coordinator):
        """Should use PARAM_TYPES mapping for known parameters."""
        number = KlereoNumber(mock_coordinator, "SYS1", "ConsigneEau", 28)
        assert number._attr_name == "Water Setpoint"
        assert number._attr_native_unit_of_measurement == "°C"
        assert number._attr_native_min_value == 10
        assert number._attr_native_max_value == 40
        assert number._attr_native_step == 0.5
        assert number._attr_unique_id == "SYS1_number_ConsigneEau"

    def test_initial_value(self, mock_coordinator):
        """Should set initial value from constructor."""
        number = KlereoNumber(mock_coordinator, "SYS1", "ConsigneEau", 32.5)
        assert number._attr_native_value == 32.5

    async def test_set_native_value(self, mock_coordinator):
        """Should update state optimistically and call coordinator."""
        number = KlereoNumber(mock_coordinator, "SYS1", "ConsigneEau", 28)
        number.async_write_ha_state = MagicMock()
        await number.async_set_native_value(30.0)
        assert number._attr_native_value == 30.0
        number.async_write_ha_state.assert_called_once()
        mock_coordinator.async_set_param.assert_called_once_with("SYS1", "ConsigneEau", 30.0)

    def test_handle_coordinator_update_refreshes_value(self, mock_coordinator):
        """Should update value from coordinator data."""
        number = KlereoNumber(mock_coordinator, "SYS1", "ConsigneEau", 28)
        number.async_write_ha_state = MagicMock()
        mock_coordinator.data["SYS1"]["details"]["RegulModes"]["ConsigneEau"] = 35
        number._handle_coordinator_update()
        assert number._attr_native_value == 35
        assert number._attr_available is True

    def test_handle_coordinator_update_missing_system(self, mock_coordinator):
        """Should mark unavailable when system disappears."""
        number = KlereoNumber(mock_coordinator, "MISSING", "ConsigneEau", 28)
        number.async_write_ha_state = MagicMock()
        number._handle_coordinator_update()
        assert number._attr_available is False

    def test_device_info(self, mock_coordinator):
        """Should return device info from coordinator data."""
        number = KlereoNumber(mock_coordinator, "SYS1", "ConsigneEau", 28)
        info = number.device_info
        assert ("klereo", "SYS1") in info["identifiers"]
        assert info["name"] == "My Pool"
