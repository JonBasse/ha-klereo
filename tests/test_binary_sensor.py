"""Tests for Klereo binary sensor entities."""
from unittest.mock import MagicMock

import pytest

from custom_components.klereo.binary_sensor import KlereoBinarySensor
from custom_components.klereo.models import (
    KlereoPoolDetails,
    KlereoProbe,
    KlereoSystemData,
    KlereoSystemInfo,
)


def _make_probe(**kwargs) -> KlereoProbe:
    """Create a KlereoProbe with binary sensor defaults."""
    defaults = {"index": 0, "type": 10, "filtered_value": 1, "direct_value": 1, "status": 0}
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
                regul_modes={},
                probe_index={0: probe},
                output_index={},
            ),
        )
    }
    return coordinator


class TestKlereoBinarySensor:
    """Tests for KlereoBinarySensor."""

    def test_creates_with_known_type(self, mock_coordinator):
        """Should use BINARY_SENSOR_TYPES mapping for known probe types."""
        probe = _make_probe()
        sensor = KlereoBinarySensor(mock_coordinator, "SYS1", probe)
        assert sensor._attr_name == "Generic"
        assert sensor._attr_unique_id == "SYS1_binary_sensor_0"
        assert sensor._attr_device_class is None

    def test_is_on_when_value_is_one(self, mock_coordinator):
        """Should be ON when filtered_value is 1."""
        probe = _make_probe(filtered_value=1)
        sensor = KlereoBinarySensor(mock_coordinator, "SYS1", probe)
        assert sensor._attr_is_on is True

    def test_is_off_when_value_is_zero(self, mock_coordinator):
        """Should be OFF when filtered_value is 0."""
        probe = _make_probe(filtered_value=0)
        sensor = KlereoBinarySensor(mock_coordinator, "SYS1", probe)
        assert sensor._attr_is_on is False

    def test_falls_back_to_direct_value(self, mock_coordinator):
        """Should use direct_value when filtered_value is None."""
        probe = _make_probe(filtered_value=None, direct_value=1)
        sensor = KlereoBinarySensor(mock_coordinator, "SYS1", probe)
        assert sensor._attr_is_on is True

    def test_is_none_when_no_value(self, mock_coordinator):
        """Should be None when both values are None."""
        probe = _make_probe(filtered_value=None, direct_value=None)
        sensor = KlereoBinarySensor(mock_coordinator, "SYS1", probe)
        assert sensor._attr_is_on is None

    def test_handle_coordinator_update_refreshes(self, mock_coordinator):
        """Should update from coordinator data."""
        probe = _make_probe(filtered_value=0)
        sensor = KlereoBinarySensor(mock_coordinator, "SYS1", probe)
        sensor.async_write_ha_state = MagicMock()
        # Update probe in coordinator
        mock_coordinator.data["SYS1"].details.probe_index[0] = _make_probe(filtered_value=1)
        sensor._handle_coordinator_update()
        assert sensor._attr_is_on is True
        assert sensor._attr_available is True

    def test_handle_coordinator_update_missing_system(self, mock_coordinator):
        """Should mark unavailable when system disappears."""
        probe = _make_probe()
        sensor = KlereoBinarySensor(mock_coordinator, "MISSING", probe)
        sensor.async_write_ha_state = MagicMock()
        sensor._handle_coordinator_update()
        assert sensor._attr_available is False

    def test_device_info(self, mock_coordinator):
        """Should return device info from coordinator data."""
        probe = _make_probe()
        sensor = KlereoBinarySensor(mock_coordinator, "SYS1", probe)
        info = sensor.device_info
        assert ("klereo", "SYS1") in info["identifiers"]
        assert info["name"] == "My Pool"
