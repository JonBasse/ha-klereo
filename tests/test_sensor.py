"""Tests for Klereo sensor entities."""
from unittest.mock import MagicMock

import pytest

from custom_components.klereo.models import (
    KlereoAlert,
    KlereoPoolDetails,
    KlereoProbe,
    KlereoSystemData,
    KlereoSystemInfo,
)
from custom_components.klereo.sensor import (
    KlereoAlertSensor,
    KlereoParamSensor,
    KlereoSensor,
    _extract_sensors,
)


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

    These assert the WHOLE uid list rather than filtering it, and that is deliberate — an
    exact list is what catches an entity nobody asked for. `SYS1_alerts` appears in every
    expectation because the alert sensor is created unconditionally (#57); it is spelled
    out here rather than filtered away so that a future always-on entity has to be
    declared in these tests too, instead of slipping past a filter.
    """

    def test_creates_sensor_for_curated_params_key(self, mock_coordinator):
        """Should expose a `params` key that has a friendly name."""
        details = KlereoPoolDetails(params={"ConsignePH": 7.2})
        uids = [uid for uid, _ in _extract_sensors(mock_coordinator, "SYS1", details)]
        assert uids == ["SYS1_param_ConsignePH", "SYS1_alerts"]

    def test_ignores_uncurated_params_key(self, mock_coordinator):
        """Should NOT expose an unknown `params` key.

        This is the control that keeps the container change additive rather than an entity
        flood: `params` carries consumption counters, bounds and internal flags.
        """
        details = KlereoPoolDetails(params={"PHMinus_Debit": 12, "EauMin": 15})
        uids = [uid for uid, _ in _extract_sensors(mock_coordinator, "SYS1", details)]
        assert uids == ["SYS1_alerts"]

    def test_still_exposes_uncurated_regul_modes_key(self, mock_coordinator):
        """Should keep exposing unknown `RegulModes` keys — removing one deletes an entity."""
        details = KlereoPoolDetails(regul_modes={"SomethingNew": 3})
        uids = [uid for uid, _ in _extract_sensors(mock_coordinator, "SYS1", details)]
        assert uids == ["SYS1_param_SomethingNew", "SYS1_alerts"]

    def test_does_not_duplicate_a_key_present_in_both(self, mock_coordinator):
        """Should create one sensor when both containers carry the same key."""
        details = KlereoPoolDetails(
            regul_modes={"ConsignePH": 7.2}, params={"ConsignePH": 7.4}
        )
        uids = [uid for uid, _ in _extract_sensors(mock_coordinator, "SYS1", details)]
        assert uids == ["SYS1_param_ConsignePH", "SYS1_alerts"]

    def test_param_sensor_refreshes_from_params_container(self, mock_coordinator):
        """Should refresh a params-sourced sensor, not pin it to its first reading."""
        mock_coordinator.data["SYS1"].details.regul_modes = {}
        mock_coordinator.data["SYS1"].details.params = {"ConsignePH": 7.2}
        sensor = KlereoParamSensor(mock_coordinator, "SYS1", "ConsignePH", 7.2)
        sensor.async_write_ha_state = MagicMock()
        mock_coordinator.data["SYS1"].details.params["ConsignePH"] = 7.4
        sensor._handle_coordinator_update()
        assert sensor._attr_native_value == 7.4


# The one payload anyone has measured, quoted from GitHub #57 (@sbdomo, 2026-08-26). Its
# value is that nothing in it was chosen by us: the string `updateTime`, the undocumented
# `level`, and `alertCount` disagreeing with `len(alerts)` are all properties of the API,
# and every one of them would have been got wrong by a fixture written from the issue text.
MEASURED_ALERT = {
    "index": 0,
    "code": 29,
    "param": 0,
    "updateTime": "2026-08-26 11:24:58",
    "level": 2,
}


def _alert_coordinator(alerts=None, reported=None, probes=None) -> MagicMock:
    """Build a coordinator whose single system carries the given alerts."""
    probes = probes or []
    coordinator = MagicMock()
    coordinator.data = {
        "SYS1": KlereoSystemData(
            info=KlereoSystemInfo(id_system="SYS1", pool_nickname="My Pool"),
            details=KlereoPoolDetails(
                probes=probes,
                alerts=alerts or [],
                reported_alert_count=reported,
                probe_index={p.index: p for p in probes},
            ),
        )
    }
    return coordinator


class TestAlertSensor:
    """Tests for the alert sensor requested in GitHub #57."""

    def test_reads_the_measured_payload_verbatim(self):
        """Should render the one real alert anyone has reported, label and all.

        Positive control on the whole chain — parse, label, param semantics, attributes —
        against a payload we did not invent. Code 29 is also the only alert code confirmed
        against reality: the reporter wrote "Here, the pump is stopped (code 29)".
        """
        details = KlereoPoolDetails.from_dict({"alerts": [MEASURED_ALERT], "alertCount": 0})
        coordinator = _alert_coordinator(details.alerts, reported=0)
        sensor = KlereoAlertSensor(coordinator, "SYS1")

        assert sensor._attr_native_value == 1
        alert = sensor._attr_extra_state_attributes["alerts"][0]
        assert alert["code"] == 29
        assert alert["label"] == "Filtration in MANUAL-OFF mode"
        assert alert["level"] == 2
        assert alert["updated"] == "2026-08-26 11:24:58"

    def test_state_is_the_array_length_not_the_reported_count(self):
        """🔴 Should count the alerts it renders, never trust `alertCount`.

        THE test of this entity. The measured payload carries `alertCount: 0` beside one
        active alert — the reporter noticed it himself. Reading that field would show a
        healthy `0` over a real alert: a false green, on the entity whose whole job is to
        not be one. Upstream computes the count the same way (`klereo.class.php` l.511).
        """
        coordinator = _alert_coordinator([KlereoAlert(code=29)], reported=0)
        sensor = KlereoAlertSensor(coordinator, "SYS1")

        assert sensor._attr_native_value == 1
        assert sensor._attr_extra_state_attributes["reported_alert_count"] == 0

    def test_reports_zero_when_the_key_is_absent(self):
        """Should exist and read 0 on a healthy pool, where `alerts` is not sent at all.

        The reporter measured that the key is ABSENT when there is nothing to report, not
        present and empty. An entity keyed on it would exist only while something is
        wrong, and take its history with it when the pool recovers.
        """
        details = KlereoPoolDetails.from_dict({"probes": [], "outs": []})
        coordinator = _alert_coordinator(details.alerts)
        sensor = KlereoAlertSensor(coordinator, "SYS1")

        assert sensor._attr_native_value == 0
        assert sensor._attr_extra_state_attributes["alerts"] == []

    def test_is_created_even_with_no_alerts(self, mock_coordinator):
        """Should be discovered unconditionally, not on the presence of alerts."""
        details = KlereoPoolDetails()
        uids = [uid for uid, _ in _extract_sensors(mock_coordinator, "SYS1", details)]
        assert "SYS1_alerts" in uids

    def test_refreshes_when_an_alert_clears(self):
        """Should follow the coordinator down as well as up.

        Negative control on the refresh path: an entity that only ever counts up would
        pass every test above and still pin a cleared alert on the dashboard forever.
        """
        coordinator = _alert_coordinator([KlereoAlert(code=29), KlereoAlert(code=14)])
        sensor = KlereoAlertSensor(coordinator, "SYS1")
        sensor.async_write_ha_state = MagicMock()
        assert sensor._attr_native_value == 2

        coordinator.data["SYS1"].details.alerts = []
        sensor._handle_coordinator_update()

        assert sensor._attr_native_value == 0
        assert sensor._attr_extra_state_attributes["alerts"] == []

    def test_names_an_unknown_code_by_its_number(self):
        """Should count and show a code absent from the table, never map it to a neighbour.

        The upstream table has real gaps (4, 9, 15-20, 24, 27, 32, 33) and Klereo can add
        codes. Dropping an unknown alert would hide a real one; naming it after code 61
        because 62 is missing would be worse.
        """
        coordinator = _alert_coordinator([KlereoAlert(code=999, param=3)])
        sensor = KlereoAlertSensor(coordinator, "SYS1")

        assert sensor._attr_native_value == 1
        assert sensor._attr_extra_state_attributes["alerts"][0]["label"] == (
            "Unknown alert code 999"
        )


class TestAlertParamSemantics:
    """Tests for `param`, which means a different thing per alert code.

    🔴 This is the actual work of #57 — not the labels. A sensor rendering `param` raw
    would be wrong for most codes: it is a probe index for 1, 7, 8, 10 and 36, a flow id
    for 13 and 14, an output index for 35, an error code for 50-52, 54 and 61, and a pump
    id for 53. Five families, one field.
    """

    def test_resolves_a_probe_param_against_this_installation(self):
        """Should name the probe from the install's own payload, not a ported lookup table.

        Upstream carries a fixed CapteurID→label map; we already parse the probes, so
        reading them is one source of truth instead of two. @sbdomo's payload happens to
        confirm both agree — his probe 16 is the water temperature in each.
        """
        probe = KlereoProbe(index=16, type=5, filtered_value=27.0)
        coordinator = _alert_coordinator([KlereoAlert(code=1, param=16)], probes=[probe])
        sensor = KlereoAlertSensor(coordinator, "SYS1")

        assert sensor._attr_extra_state_attributes["alerts"][0]["label"] == (
            "Sensor failure - Water Temperature"
        )

    def test_falls_back_to_the_number_when_the_probe_is_absent(self):
        """Should say `sensor 42` rather than drop the alert or name the wrong probe."""
        coordinator = _alert_coordinator([KlereoAlert(code=1, param=42)])
        sensor = KlereoAlertSensor(coordinator, "SYS1")

        assert sensor._attr_extra_state_attributes["alerts"][0]["label"] == (
            "Sensor failure - sensor 42"
        )

    def test_resolves_an_output_param_to_its_output_name(self):
        """Should name output 4 as Heating, the name already used everywhere else."""
        coordinator = _alert_coordinator([KlereoAlert(code=35, param=4)])
        sensor = KlereoAlertSensor(coordinator, "SYS1")

        assert sensor._attr_extra_state_attributes["alerts"][0]["label"] == (
            "Maintenance - Heating"
        )

    @pytest.mark.parametrize(
        ("code", "param", "expected"),
        [
            (13, 2, "Excess water consumption - flow 2"),
            (14, 1, "Water leak - flow 1"),
            (53, 3, "Filtration link failure - pump 3"),
            (50, 7, "Heat pump - error code 7"),
            (61, 12, "Heat pump fault - error code 12"),
            (40, 5, "Electrolyser - BSVError 5"),
            (41, 2, "Heat pump link failure - Communication 2"),
            (5, 99, "Low batteries - RFID"),
            (6, 0, "Calibration - pH"),
            (6, 1, "Calibration - Disinfectant"),
        ],
    )
    def test_describes_each_param_family(self, code, param, expected):
        """Should render each documented `param` family in its own terms."""
        coordinator = _alert_coordinator([KlereoAlert(code=code, param=param)])
        sensor = KlereoAlertSensor(coordinator, "SYS1")

        assert sensor._attr_extra_state_attributes["alerts"][0]["label"] == expected

    def test_says_nothing_about_an_undocumented_param(self):
        """🔴 Should leave `param` undescribed when no source says what it means.

        Negative control, and the rule this repository keeps relearning: a plausible
        wrong description is worse than none. Code 29 carries `param: 0` in the measured
        payload and nothing anywhere says what that 0 is.
        """
        coordinator = _alert_coordinator([KlereoAlert(code=29, param=0)])
        sensor = KlereoAlertSensor(coordinator, "SYS1")

        alert = sensor._attr_extra_state_attributes["alerts"][0]
        assert alert["label"] == "Filtration in MANUAL-OFF mode"
        assert alert["param"] == 0

    def test_an_unknown_code_gets_no_param_description(self):
        """Absurdity control: an unnamed code cannot have a known param meaning."""
        coordinator = _alert_coordinator([KlereoAlert(code=999, param=16)])
        sensor = KlereoAlertSensor(coordinator, "SYS1")

        assert sensor._attr_extra_state_attributes["alerts"][0]["label"] == (
            "Unknown alert code 999"
        )
