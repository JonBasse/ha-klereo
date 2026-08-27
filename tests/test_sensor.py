"""Tests for Klereo sensor entities."""
from unittest.mock import MagicMock

import pytest

from custom_components.klereo.const import PARAM_COUNTER_TYPES, SENSOR_TYPES
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
        """Should set initial value from RegulModes, under its curated name.

        `ConsigneEau` joined PARAM_NAMES in #128 so that it has a name to fall back to
        when its `number` is refused; before that it rendered as the humanized key.
        """
        sensor = KlereoParamSensor(mock_coordinator, "SYS1", "ConsigneEau", 28)
        assert sensor._attr_name == "Water Setpoint"
        assert sensor._attr_native_value == 28
        assert sensor._attr_unique_id == "SYS1_param_ConsigneEau"

    def test_uncurated_key_falls_back_to_the_humanized_name(self, mock_coordinator):
        """Should split a camelCase key nobody has named. Every curated key now has a
        friendly name, so this path needs a key that is deliberately not one."""
        sensor = KlereoParamSensor(mock_coordinator, "SYS1", "SomethingNew", 3)
        assert sensor._attr_name == "Something New"

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
        """Should expose a `params` key that has a friendly name.

        The stand-in is `ModeRegulPH` rather than a `Consigne*`: since #128 every setpoint
        in PARAM_TYPES leaves this platform as soon as its write is offered, so one of
        them would test the setpoint fallback instead of the curated-name gate.
        """
        details = KlereoPoolDetails(params={"ModeRegulPH": 1})
        uids = [uid for uid, _ in _extract_sensors(mock_coordinator, "SYS1", details)]
        assert uids == ["SYS1_param_ModeRegulPH", "SYS1_alerts"]

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
            regul_modes={"ModeRegulPH": 1}, params={"ModeRegulPH": 2}
        )
        uids = [uid for uid, _ in _extract_sensors(mock_coordinator, "SYS1", details)]
        assert uids == ["SYS1_param_ModeRegulPH", "SYS1_alerts"]

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


class TestRunTimeCounters:
    """Klereo counts what each piece of equipment has DONE, in seconds, in `params`.

    Measured twice: named by an external reporter reading his own diagnostics export
    (GitHub #54, 2026-06-17) and confirmed on a live payload from the Bioul installation
    (2026-08-26). Upstream reads the same keys at `klereo.class.php` l.322-405.

    The value is exposed RAW, in seconds, rather than divided by 3600 the way upstream
    does: the seconds are what the wire carries, Home Assistant renders a duration by
    itself, and a sensor whose value equals the payload is one a bug report can quote.
    Forgejo #54.
    """

    def _extract(self, mock_coordinator, **containers):
        """Install the payload in the coordinator, then discover from it.

        Both halves matter: discovery reads the details it is handed, and the entities
        then read the coordinator. Handing one payload to discovery while the coordinator
        holds another tests a mismatch no installation can produce.
        """
        details = KlereoPoolDetails(**containers)
        mock_coordinator.data["SYS1"].details = details
        return _extract_sensors(mock_coordinator, "SYS1", details)

    def _uids(self, mock_coordinator, **containers):
        return [uid for uid, _ in self._extract(mock_coordinator, **containers)]

    def _sensor(self, mock_coordinator, key, **containers):
        for uid, entity in self._extract(mock_coordinator, **containers):
            if uid == f"SYS1_param_{key}":
                return entity
        return None

    def test_the_exit_criterion_of_the_ticket(self, mock_coordinator):
        """A payload carrying `PHMinus_TodayTime` under `params` creates the sensor."""
        assert self._uids(mock_coordinator, params={"PHMinus_TodayTime": 900}) == [
            "SYS1_param_PHMinus_TodayTime", "SYS1_alerts",
        ]

    def test_a_counter_is_exposed_in_seconds_as_an_increasing_total(self, mock_coordinator):
        """Seconds, `duration`, `total_increasing` — no arithmetic on a wire value."""
        sensor = self._sensor(mock_coordinator, "Filtration_TodayTime",
                              params={"Filtration_TodayTime": 13320})
        assert sensor.native_value == 13320
        assert sensor.native_unit_of_measurement == "s"
        assert sensor.device_class == "duration"
        assert sensor.state_class == "total_increasing"

    def test_the_counter_is_named_after_its_equipment(self, mock_coordinator):
        """Not `_humanize_key`, which would render `Filtration_TodayTime` verbatim."""
        sensor = self._sensor(mock_coordinator, "Chauff_TotalTime",
                              params={"Chauff_TotalTime": 1})
        assert sensor.name == "Heating Time Total"

    def test_electrolysis_production_is_exposed_in_milligrams(self, mock_coordinator):
        """Upstream divides `Elec_GramDone` by 1000 and labels it `g`, so the wire is mg."""
        sensor = self._sensor(mock_coordinator, "Elec_GramDone", params={"Elec_GramDone": 42000})
        assert sensor.native_value == 42000
        assert sensor.native_unit_of_measurement == "mg"
        assert sensor.device_class == "weight"

    def test_the_curated_counter_list_is_exactly_these_keys(self, mock_coordinator):
        """🔴 Pins the curation itself.

        `params` carries 113 keys on the measured installation. The counters are admitted
        BY NAME, never by a suffix pattern — a `*_TodayTime` rule would look identical on
        this payload and admit whatever Klereo adds next, sight unseen. Every name below
        comes from `klereo.class.php`; none is inferred.
        """
        assert set(PARAM_COUNTER_TYPES) == {
            "Filtration_TodayTime", "Filtration_TotalTime",
            "PHMinus_TodayTime", "PHMinus_TotalTime",
            "ElectroChlore_TodayTime", "ElectroChlore_TotalTime",
            "HybChl_TodayTime", "HybChl_TotalTime",
            "Chauff_TodayTime", "Chauff_TotalTime",
            "Elec_GramDone",
        }

    def test_an_uncurated_counter_lookalike_creates_nothing(self, mock_coordinator):
        """🔴 Negative control on the curation: the suffix alone must not admit a key."""
        assert self._uids(mock_coordinator, params={"Backwash_TodayTime": 60}) == ["SYS1_alerts"]

    def test_a_counter_nested_in_an_unread_structure_creates_nothing(self, mock_coordinator):
        """🔴 Negative control on the container: only the three settings containers are read.

        Without this, "the sensor appeared" would be compatible with a reader that walks
        the payload looking for the name anywhere it occurs.
        """
        assert self._uids(mock_coordinator, params={"podinfo": {"PHMinus_TodayTime": 900}}) == [
            "SYS1_alerts",
        ]

    def test_the_hybrid_counter_is_read_from_extra_params(self, mock_coordinator):
        """Upstream reads `HybChl_*` out of `ExtraParams`, not `params` (l.356)."""
        assert self._uids(mock_coordinator, extra_params={"HybChl_TotalTime": 7200}) == [
            "SYS1_param_HybChl_TotalTime", "SYS1_alerts",
        ]


class TestProductConsumption:
    """What the reporter actually asked for: litres of product, not hours of pump.

    Klereo does not send a volume. It sends a run time and a pump flow rate, and upstream
    multiplies them (`klereo.class.php` l.335-380):

        today = <Equipment>_TodayTime × <rate> / 36      → mL
        total = <Equipment>_TotalTime × <rate> / 36000   → L

    This is the one place arithmetic is unavoidable, and the rule that follows from it is
    the rule for the whole platform: we compute only what the API does not send.

    Both flow-rate keys were confirmed on 2026-08-26 in GitHub #55, on a third
    installation: `PHMinus_Debit` and `Chlore_Debit` sit in `params` beside the counters.
    They are still gated on presence rather than assumed, because the counters follow the
    installed equipment and a pool with no pH- pump has neither — and because that gate is
    a read: no flow rate, no consumption entity, while the run-time sensor stays, since it
    never needed one.
    """

    def _extract(self, mock_coordinator, **containers):
        """Install the payload in the coordinator, then discover from it."""
        details = KlereoPoolDetails(**containers)
        mock_coordinator.data["SYS1"].details = details
        return _extract_sensors(mock_coordinator, "SYS1", details)

    def _uids(self, mock_coordinator, **containers):
        return [uid for uid, _ in self._extract(mock_coordinator, **containers)]

    def _sensor(self, mock_coordinator, key, **containers):
        for uid, entity in self._extract(mock_coordinator, **containers):
            if uid == f"SYS1_consumption_{key}":
                return entity
        return None

    def test_daily_consumption_is_time_times_flow_rate(self, mock_coordinator):
        """900 s at 12 → 300 mL, upstream's `× rate / 36`."""
        sensor = self._sensor(mock_coordinator, "PHMinus_Today",
                              params={"PHMinus_TodayTime": 900, "PHMinus_Debit": 12})
        assert sensor.native_value == 300
        assert sensor.native_unit_of_measurement == "mL"
        assert sensor.device_class == "volume"
        assert sensor.state_class == "total_increasing"

    def test_total_consumption_uses_the_thousandfold_divisor(self, mock_coordinator):
        """The total is litres, not millilitres — upstream's `/ 36000`."""
        sensor = self._sensor(mock_coordinator, "PHMinus_Total",
                              params={"PHMinus_TotalTime": 90000, "PHMinus_Debit": 12})
        assert sensor.native_value == 30
        assert sensor.native_unit_of_measurement == "L"

    def test_the_chlorine_pumps_share_one_flow_rate_key(self, mock_coordinator):
        """Both chlorine pumps are metered by `Chlore_Debit`, not a per-pump key."""
        sensor = self._sensor(mock_coordinator, "ElectroChlore_Today",
                              params={"ElectroChlore_TodayTime": 1800, "Chlore_Debit": 2})
        assert sensor.native_value == 100

    def test_the_hybrid_pump_crosses_two_containers(self, mock_coordinator):
        """`HybChl_*` is in `ExtraParams` and its flow rate is in `params`.

        Reading `params` alone — as this ticket originally proposed — would compute
        nothing for a hybrid installation, and the failure would look like absent hardware.
        """
        sensor = self._sensor(mock_coordinator, "HybChl_Today",
                              extra_params={"HybChl_TodayTime": 900},
                              params={"Chlore_Debit": 12})
        assert sensor.native_value == 300

    def test_no_flow_rate_means_no_consumption_but_keeps_the_run_time(self, mock_coordinator):
        """🔴 The gate. A payload with the counter and no rate loses only the derived one."""
        assert self._uids(mock_coordinator, params={"PHMinus_TodayTime": 900}) == [
            "SYS1_param_PHMinus_TodayTime", "SYS1_alerts",
        ]

    def test_no_counter_means_no_consumption(self, mock_coordinator):
        """🔴 A flow rate on its own describes a pump that has not run and is not metered."""
        assert self._uids(mock_coordinator, params={"PHMinus_Debit": 12}) == ["SYS1_alerts"]

    def test_only_the_pump_the_payload_carries_is_metered(self, mock_coordinator):
        """The two chlorine pumps are exclusive, and the payload already says which.

        Upstream branches on `HybrideMode == 1` to choose between them. We do not read it:
        the counters follow the installed equipment — Bioul carries `ElectroChlore_*` and
        no `HybChl_*` — so keying on the counter's presence is a reading where reading
        `HybrideMode` would be a second, weaker source for the same fact.
        """
        uids = self._uids(mock_coordinator,
                          params={"ElectroChlore_TodayTime": 1800, "Chlore_Debit": 2})
        assert "SYS1_consumption_ElectroChlore_Today" in uids
        assert "SYS1_consumption_HybChl_Today" not in uids

    def test_consumption_refreshes_with_the_payload(self, mock_coordinator):
        """Should recompute on update, not pin the value taken at discovery."""
        sensor = self._sensor(mock_coordinator, "PHMinus_Today",
                              params={"PHMinus_TodayTime": 900, "PHMinus_Debit": 12})
        sensor.async_write_ha_state = MagicMock()
        assert sensor.native_value == 300
        mock_coordinator.data["SYS1"].details.params["PHMinus_TodayTime"] = 1800
        sensor._handle_coordinator_update()
        assert sensor.native_value == 600

    def test_an_unreadable_reading_is_unknown_not_a_crash(self, mock_coordinator):
        """A non-numeric flow rate yields None, the honest report, not a traceback.

        Same rule as `_label_for_mode` in #105: we do not turn "we cannot read this" into
        a specific, plausible, wrong number.
        """
        sensor = self._sensor(mock_coordinator, "PHMinus_Today",
                              params={"PHMinus_TodayTime": 900, "PHMinus_Debit": "n/a"})
        assert sensor.native_value is None


class TestRegulationReferenceProbes:
    """Klereo names which probe drives each regulation loop; nothing read it until now.

    `docs/klereo-api.md` documents four top-level fields carrying a `probes[].index`:
    `EauCapteur` (water temperature), `pHCapteur` (pH), `TraitCapteur` (disinfectant) and
    `PressionCapteur` (pressure). A pool can carry several temperature probes and nothing
    told the user which one the box actually regulates on — they had to guess, and the
    probe list differs between installations.

    Measured on a live `GetIndex` in GitHub #57 (2026-08-26): `EauCapteur: 16`,
    `pHCapteur: 17`, `TraitCapteur: 18`, `PressionCapteur: -1`, with probes 16, 17 and 18
    all present and of the matching types.

    It is an ATTRIBUTE, not a new entity: the reading is already exposed, it is its role
    that was missing. Forgejo #107.
    """

    def _probe_attrs(self, mock_coordinator, index, probes, **fields):
        details = KlereoPoolDetails(
            probes=probes,
            probe_index={p.index: p for p in probes},
            regulation_probes=fields,
        )
        mock_coordinator.data["SYS1"].details = details
        sensor = KlereoSensor(mock_coordinator, "SYS1", details.probe_index[index])
        return sensor.extra_state_attributes

    def _measured(self):
        """The three probes of the measured payload, with their real types."""
        return [
            _make_probe(index=16, type=5, filtered_value=27.0),
            _make_probe(index=17, type=3, filtered_value=7.22),
            _make_probe(index=18, type=4, filtered_value=655),
        ]

    def test_the_measured_payload_marks_its_three_reference_probes(self, mock_coordinator):
        """Probe 16 drives water temperature, 17 the pH, 18 the disinfectant."""
        probes = self._measured()
        fields = {"water_temperature": 16, "ph": 17, "disinfectant": 18, "pressure": -1}
        assert self._probe_attrs(mock_coordinator, 16, probes, **fields)[
            "regulation_reference"] == ["water_temperature"]
        assert self._probe_attrs(mock_coordinator, 17, probes, **fields)[
            "regulation_reference"] == ["ph"]
        assert self._probe_attrs(mock_coordinator, 18, probes, **fields)[
            "regulation_reference"] == ["disinfectant"]

    def test_a_probe_no_regulation_names_carries_no_attribute(self, mock_coordinator):
        """The key is absent, not present and empty — an empty list reads as a claim."""
        probes = [*self._measured(), _make_probe(index=1, type=1, filtered_value=23.7)]
        attrs = self._probe_attrs(mock_coordinator, 1, probes, water_temperature=16)
        assert "regulation_reference" not in attrs
        assert attrs["type"] == 1

    def test_minus_one_means_no_reference_probe_and_is_not_an_anomaly(
        self, mock_coordinator, caplog
    ):
        """🔴 `-1` says "this regulation has no reference sensor", not "unknown".

        Both end up creating no attribute, so the attribute alone cannot tell them apart.
        The discriminator is the log: a regulation with no probe is a NORMAL installation
        and must stay at debug, while an index naming a probe the payload does not carry
        is a payload that contradicts itself and earns a warning. Confusing the two would
        cry wolf on every pool without a pressure sensor.
        """
        with caplog.at_level("DEBUG", logger="custom_components.klereo.sensor"):
            self._probe_attrs(mock_coordinator, 16, self._measured(),
                              water_temperature=16, pressure=-1)
        assert not [r for r in caplog.records if r.levelname == "WARNING"]
        assert "pressure" in caplog.text

    def test_an_index_naming_no_probe_warns(self, mock_coordinator, caplog):
        """🔴 A reference pointing at a probe the payload does not carry IS an anomaly."""
        with caplog.at_level("DEBUG", logger="custom_components.klereo.sensor"):
            attrs = self._probe_attrs(mock_coordinator, 16, self._measured(),
                                      water_temperature=16, ph=99)
        assert attrs["regulation_reference"] == ["water_temperature"]
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1
        assert "99" in warnings[0].getMessage()

    def test_a_probe_named_by_two_regulations_lists_both(self, mock_coordinator):
        """The attribute is always a list, so the unseen case needs no special path."""
        probes = self._measured()
        attrs = self._probe_attrs(mock_coordinator, 16, probes,
                                  water_temperature=16, pressure=16)
        assert attrs["regulation_reference"] == ["pressure", "water_temperature"]

    def test_no_fields_at_all_marks_nothing(self, mock_coordinator):
        """⚠️ The four fields are optional. A payload without them loses no entity."""
        attrs = self._probe_attrs(mock_coordinator, 16, self._measured())
        assert "regulation_reference" not in attrs

    def test_the_reference_follows_a_later_payload(self, mock_coordinator):
        """The box can be reconfigured; the attribute must not pin the first reading."""
        probes = self._measured()
        details = KlereoPoolDetails(
            probes=probes,
            probe_index={p.index: p for p in probes},
            regulation_probes={"water_temperature": 16},
        )
        mock_coordinator.data["SYS1"].details = details
        sensor = KlereoSensor(mock_coordinator, "SYS1", probes[0])
        sensor.async_write_ha_state = MagicMock()
        assert sensor.extra_state_attributes["regulation_reference"] == ["water_temperature"]
        details.regulation_probes = {"water_temperature": 17}
        sensor._handle_coordinator_update()
        assert "regulation_reference" not in sensor.extra_state_attributes


class TestRegulationReferenceParsing:
    """The four fields are read off the top level of the details payload."""

    def test_the_measured_field_names_are_parsed(self):
        """Klereo's own names, verbatim from `docs/klereo-api.md` and GitHub #57."""
        details = KlereoPoolDetails.from_dict({
            "EauCapteur": 16, "pHCapteur": 17, "TraitCapteur": 18, "PressionCapteur": -1,
        })
        assert details.regulation_probes == {
            "water_temperature": 16, "ph": 17, "disinfectant": 18, "pressure": -1,
        }

    def test_an_absent_field_is_absent_not_zero(self):
        """🔴 A missing field must not become `0`, which is a valid probe index."""
        details = KlereoPoolDetails.from_dict({"EauCapteur": 16})
        assert details.regulation_probes == {"water_temperature": 16}

    def test_an_unreadable_index_is_dropped(self):
        """A non-integer index resolves to nothing and must not reach the lookup."""
        details = KlereoPoolDetails.from_dict({"EauCapteur": "16", "pHCapteur": None})
        assert details.regulation_probes == {"water_temperature": 16}

class TestProbeTypeNamesAreNotInverted:
    """🔴 Pins the two probe types that were once mapped to each other's names.

    A release before v1.5.2 mapped type 1 to Water and type 5 to Air. Fixing it repaired
    the displayed name and nothing else: Home Assistant derives an `entity_id` from the
    name at CREATION and never revisits it, so every installation created under the wrong
    mapping still carries `sensor.klereo_water_temperature` on its air probe — for good
    (Forgejo #121, measured on a live 1.5.2 installation).

    That is why this guard is worth its two lines. An entity name is a public API from the
    first install onwards, more frozen than any constant in this repository: inverting
    these two again would be invisible on screen for existing users and permanent for new
    ones. The negative control is that swapping the two entries reddens this test alone.
    """

    def test_type_1_is_air_and_type_5_is_water(self):
        assert SENSOR_TYPES[1]["name"] == "Air Temperature"
        assert SENSOR_TYPES[5]["name"] == "Water Temperature"


# Same four setpoints as `tests/test_number.py::FULL_SETPOINTS`, and deliberately the same
# shape: these tests are the OTHER half of each control there. Every arm below asserts
# that what `number` refused, `sensor` kept.
SETPOINT_PAYLOAD = {
    "ConsigneEau": 28, "EauMin": 15, "EauMax": 32, "HeaterMode": 1,
    "ConsignePH": 7.2, "pHMin": 6.8, "pHMax": 7.6, "pHMode": 1,
    "ConsigneRedox": 650, "OrpMin": 400, "OrpMax": 850,
    "ConsigneChlore": 1.2,
}


class TestSetpointFallsBackToAReadOnlySensor:
    """Tests that a REFUSED write leaves the reading in place (#128).

    Before #128 this platform excluded a key on `key in PARAM_TYPES` alone, without asking
    whether the `number` had actually been created. Promoting the three advanced setpoints
    would then have DELETED them from every account below access 16 — including the
    account of the reporter who asked for the feature, who says he has a standard one.

    The uid lists are exact on purpose, and `SYS1_alerts` is spelled out rather than
    filtered: an entity nobody asked for has to show up as a failure here.
    """

    def _uids(self, coordinator, access, **overrides):
        settings = dict(SETPOINT_PAYLOAD)
        settings.update(overrides)
        details = KlereoPoolDetails(params=settings, access=access)
        return [uid for uid, _ in _extract_sensors(coordinator, "SYS1", details)]

    def test_advanced_access_leaves_no_setpoint_sensor(self, mock_coordinator):
        """Positive control: at access 16 all four are writable, so none is a sensor.

        Without this arm the three tests below are compatible with a fallback that never
        yields — a sensor kept for everyone would pass them all.
        """
        assert self._uids(mock_coordinator, access=16) == ["SYS1_alerts"]

    def test_end_customer_access_keeps_the_three_as_sensors(self, mock_coordinator):
        """access 10: the three refused writes stay readable; ConsigneEau does not.

        ConsigneEau's absence is the discriminator. It is writable at 10, so it leaves
        this platform — a fallback keyed on the wrong thing would keep it here too.
        """
        assert self._uids(mock_coordinator, access=10) == [
            "SYS1_param_ConsignePH",
            "SYS1_param_ConsigneRedox",
            "SYS1_param_ConsigneChlore",
            "SYS1_alerts",
        ]

    def test_ph_mode_off_keeps_the_ph_setpoint_as_a_sensor(self, mock_coordinator):
        """pHMode 0 at access 16: the pH reading survives, alone."""
        assert self._uids(mock_coordinator, access=16, pHMode=0) == [
            "SYS1_param_ConsignePH",
            "SYS1_alerts",
        ]

    def test_read_only_account_keeps_all_four(self, mock_coordinator):
        """access 5: nothing is writable, so every setpoint falls back to a sensor.

        ⚠️ ConsigneEau appearing here is NEW behaviour, and an addition rather than a
        deletion: a read-only account used to see no water setpoint at all. It is the
        accepted cost of sharing one guard between the two platforms instead of two.
        """
        assert self._uids(mock_coordinator, access=5) == [
            "SYS1_param_ConsigneEau",
            "SYS1_param_ConsignePH",
            "SYS1_param_ConsigneRedox",
            "SYS1_param_ConsigneChlore",
            "SYS1_alerts",
        ]

    def test_heater_without_setpoint_keeps_the_water_reading(self, mock_coordinator):
        """HeaterMode 3 at access 16: no water setpoint to write, but still one to read."""
        assert self._uids(mock_coordinator, access=16, HeaterMode=3) == [
            "SYS1_param_ConsigneEau",
            "SYS1_alerts",
        ]

    def test_fallback_reaches_the_regul_modes_container_too(self, mock_coordinator):
        """The fallback must not depend on which container the setpoint arrived in.

        `RegulModes` is read by a different loop, and that loop carries no PARAM_NAMES
        gate — so a fix applied to one loop only would look correct on every payload that
        happens to put its setpoints in `params`, which is all three measured so far.
        """
        details = KlereoPoolDetails(regul_modes={"ConsignePH": 7.2}, access=10)
        uids = [uid for uid, _ in _extract_sensors(mock_coordinator, "SYS1", details)]
        assert uids == ["SYS1_param_ConsignePH", "SYS1_alerts"]
