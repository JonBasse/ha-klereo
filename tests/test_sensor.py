"""Tests for Klereo sensor entities."""
from unittest.mock import MagicMock

import pytest

from custom_components.klereo.models import (
    KlereoPoolDetails,
    KlereoProbe,
    KlereoSystemData,
    KlereoSystemInfo,
)
from custom_components.klereo.sensor import KlereoParamSensor, KlereoSensor


def _make_probe(**kwargs) -> KlereoProbe:
    """Create a KlereoProbe with defaults."""
    defaults = {"index": 0, "type": 5, "filtered_value": 28.5, "direct_value": 28.4, "status": 0}
    defaults.update(kwargs)
    return KlereoProbe(**defaults)


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator."""
    probe = _make_probe()
    coordinator = MagicMock()
    coordinator.data = {
        "SYS1": KlereoSystemData(
            info=KlereoSystemInfo(id_system="SYS1", pool_nickname="My Pool"),
            details=KlereoPoolDetails(
                probes=[probe],
                outs=[],
                regul_modes={"ConsigneEau": 28},
                probe_index={0: probe},
                output_index={},
            ),
        )
    }
    return coordinator


class TestKlereoSensor:
    """Tests for KlereoSensor."""

    def test_creates_with_known_type(self, mock_coordinator):
        """Should use SENSOR_TYPES mapping for known probe types."""
        probe = _make_probe()
        sensor = KlereoSensor(mock_coordinator, "SYS1", probe)
        assert sensor._attr_name == "Water Temperature"
        assert sensor._attr_native_unit_of_measurement == "°C"
        assert sensor._attr_device_class == "temperature"
        assert sensor._attr_unique_id == "SYS1_sensor_0"

    def test_creates_with_unknown_type(self, mock_coordinator):
        """Should use fallback name for unknown probe types."""
        probe = _make_probe(index=99, type=999, filtered_value=50.0)
        sensor = KlereoSensor(mock_coordinator, "SYS1", probe)
        assert sensor._attr_name == "Sensor 99"

    def test_uses_filtered_value(self, mock_coordinator):
        """Should prefer filteredValue over directValue."""
        probe = _make_probe(filtered_value=28.5, direct_value=28.4)
        sensor = KlereoSensor(mock_coordinator, "SYS1", probe)
        assert sensor._attr_native_value == 28.5

    def test_falls_back_to_direct_value(self, mock_coordinator):
        """Should use directValue when filteredValue is None."""
        probe = _make_probe(filtered_value=None, direct_value=28.4)
        sensor = KlereoSensor(mock_coordinator, "SYS1", probe)
        assert sensor._attr_native_value == 28.4

    def test_find_my_probe_uses_index(self, mock_coordinator):
        """Should find probe data via probe_index."""
        probe = _make_probe()
        sensor = KlereoSensor(mock_coordinator, "SYS1", probe)
        found = sensor._find_my_probe()
        assert found is not None
        assert found.filtered_value == 28.5

    def test_find_my_probe_missing_system(self, mock_coordinator):
        """Should return None for missing system."""
        probe = _make_probe()
        sensor = KlereoSensor(mock_coordinator, "MISSING", probe)
        assert sensor._find_my_probe() is None


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
