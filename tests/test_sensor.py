"""Tests for Klereo sensor entities."""
from unittest.mock import MagicMock

import pytest

from custom_components.klereo.models import (
    KlereoPoolDetails,
    KlereoProbe,
    KlereoSystemData,
    KlereoSystemInfo,
)
from custom_components.klereo.sensor import KlereoParamSensor, KlereoSensor, _extract_sensors


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


class TestParamSensorDiscovery:
    """Tests for which setting keys become read-only sensors.

    `params` is a large container upstream reads at 40+ sites, so taking every key from it
    would create dozens of entities in every install. Only curated keys are exposed.
    """

    def test_creates_sensor_for_curated_params_key(self, mock_coordinator):
        """Should expose a `params` key that has a friendly name."""
        details = KlereoPoolDetails(params={"ConsignePH": 7.2})
        uids = [uid for uid, _ in _extract_sensors(mock_coordinator, "SYS1", details)]
        assert uids == ["SYS1_param_ConsignePH"]

    def test_ignores_uncurated_params_key(self, mock_coordinator):
        """Should NOT expose an unknown `params` key.

        This is the control that keeps the container change additive rather than an entity
        flood: `params` carries consumption counters, bounds and internal flags.
        """
        details = KlereoPoolDetails(params={"PHMinus_Debit": 12, "EauMin": 15})
        uids = [uid for uid, _ in _extract_sensors(mock_coordinator, "SYS1", details)]
        assert uids == []

    def test_still_exposes_uncurated_regul_modes_key(self, mock_coordinator):
        """Should keep exposing unknown `RegulModes` keys — removing one deletes an entity."""
        details = KlereoPoolDetails(regul_modes={"SomethingNew": 3})
        uids = [uid for uid, _ in _extract_sensors(mock_coordinator, "SYS1", details)]
        assert uids == ["SYS1_param_SomethingNew"]

    def test_does_not_duplicate_a_key_present_in_both(self, mock_coordinator):
        """Should create one sensor when both containers carry the same key."""
        details = KlereoPoolDetails(
            regul_modes={"ConsignePH": 7.2}, params={"ConsignePH": 7.4}
        )
        uids = [uid for uid, _ in _extract_sensors(mock_coordinator, "SYS1", details)]
        assert uids == ["SYS1_param_ConsignePH"]

    def test_param_sensor_refreshes_from_params_container(self, mock_coordinator):
        """Should refresh a params-sourced sensor, not pin it to its first reading."""
        mock_coordinator.data["SYS1"].details.regul_modes = {}
        mock_coordinator.data["SYS1"].details.params = {"ConsignePH": 7.2}
        sensor = KlereoParamSensor(mock_coordinator, "SYS1", "ConsignePH", 7.2)
        sensor.async_write_ha_state = MagicMock()
        mock_coordinator.data["SYS1"].details.params["ConsignePH"] = 7.4
        sensor._handle_coordinator_update()
        assert sensor._attr_native_value == 7.4
