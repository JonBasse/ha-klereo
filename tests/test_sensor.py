"""Tests for Klereo sensor entities."""
from unittest.mock import MagicMock

import pytest

from custom_components.klereo.sensor import KlereoParamSensor, KlereoSensor


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator."""
    coordinator = MagicMock()
    coordinator.data = {
        "SYS1": {
            "info": {"idSystem": "SYS1", "poolNickname": "My Pool"},
            "details": {
                "probes": [
                    {"index": 0, "type": 5, "filteredValue": 28.5, "directValue": 28.4, "status": 0},
                ],
                "_probe_index": {
                    0: {"index": 0, "type": 5, "filteredValue": 28.5, "directValue": 28.4, "status": 0},
                },
                "RegulModes": {"ConsigneEau": 28},
            },
        }
    }
    return coordinator


class TestKlereoSensor:
    """Tests for KlereoSensor."""

    def test_creates_with_known_type(self, mock_coordinator):
        """Should use SENSOR_TYPES mapping for known probe types."""
        probe = {"index": 0, "type": 5, "filteredValue": 28.5, "status": 0}
        sensor = KlereoSensor(mock_coordinator, "SYS1", probe)
        assert sensor._attr_name == "Water Temperature"
        assert sensor._attr_native_unit_of_measurement == "°C"
        assert sensor._attr_device_class == "temperature"
        assert sensor._attr_unique_id == "SYS1_sensor_0"

    def test_creates_with_unknown_type(self, mock_coordinator):
        """Should use fallback name for unknown probe types."""
        probe = {"index": 99, "type": 999, "filteredValue": 50.0, "status": 0}
        sensor = KlereoSensor(mock_coordinator, "SYS1", probe)
        assert sensor._attr_name == "Sensor 99"

    def test_uses_filtered_value(self, mock_coordinator):
        """Should prefer filteredValue over directValue."""
        probe = {"index": 0, "type": 5, "filteredValue": 28.5, "directValue": 28.4, "status": 0}
        sensor = KlereoSensor(mock_coordinator, "SYS1", probe)
        assert sensor._attr_native_value == 28.5

    def test_falls_back_to_direct_value(self, mock_coordinator):
        """Should use directValue when filteredValue is None."""
        probe = {"index": 0, "type": 5, "filteredValue": None, "directValue": 28.4, "status": 0}
        sensor = KlereoSensor(mock_coordinator, "SYS1", probe)
        assert sensor._attr_native_value == 28.4

    def test_find_my_data_uses_index(self, mock_coordinator):
        """Should find probe data via _probe_index."""
        probe = {"index": 0, "type": 5, "filteredValue": 28.5, "status": 0}
        sensor = KlereoSensor(mock_coordinator, "SYS1", probe)
        found = sensor._find_my_data()
        assert found is not None
        assert found["filteredValue"] == 28.5

    def test_find_my_data_missing_system(self, mock_coordinator):
        """Should return None for missing system."""
        probe = {"index": 0, "type": 5, "filteredValue": 28.5, "status": 0}
        sensor = KlereoSensor(mock_coordinator, "MISSING", probe)
        assert sensor._find_my_data() is None


class TestKlereoParamSensor:
    """Tests for KlereoParamSensor."""

    def test_creates_with_initial_value(self, mock_coordinator):
        """Should set initial value from RegulModes."""
        sensor = KlereoParamSensor(mock_coordinator, "SYS1", "ConsigneEau", 28)
        assert sensor._attr_name == "Consigne Eau"
        assert sensor._attr_native_value == 28
        assert sensor._attr_unique_id == "SYS1_param_ConsigneEau"

    def test_device_info(self, mock_coordinator):
        """Should return device info from coordinator data."""
        sensor = KlereoParamSensor(mock_coordinator, "SYS1", "ConsigneEau", 28)
        info = sensor.device_info
        assert ("klereo", "SYS1") in info["identifiers"]
        assert info["name"] == "My Pool"
