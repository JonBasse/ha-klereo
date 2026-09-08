"""Tests for the energy counters derived from the run-time counters.

Klereo sends no power and no energy. It sends how long each piece of equipment ran, in
seconds, already parsed and already exposed (`PARAM_COUNTER_TYPES`, #54). The kilowatt-
hours are that time multiplied by a power the USER enters, one option per equipment:

    kWh = <Equipment>_<period>Time × watts / 3600 / 1000

Same pattern as `DERIVED_COUNTER_TYPES`, with a watt where the flow rate is, and the same
rule: each entity is gated on BOTH of its terms being present, never on one with a
fallback.

🔴 The gate on the power is the test that matters. A default power would put a credible
number, in a unit that has a price, into a dashboard the user reads to decide — and an
entity that always returns `0` passes every other assertion here, because it is
indistinguishable from a correct entity on a pump that has not run. Worse, on a
`total_increasing` a `0` is not "unknown" to Home Assistant: it is a counter reset, and it
costs a spurious cycle in the statistics.

Forgejo #163. Asked for by @StephanH27 on GitHub #60, 2026-09-03, who measured the
approximation against his own Linky meter: 751 W of delta for a 750 W pump.
"""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import voluptuous as vol

from custom_components.klereo.config_flow import options_schema
from custom_components.klereo.const import (
    COUNTER_EQUIPMENT,
    ENERGY_COUNTER_TYPES,
    PARAM_COUNTER_TYPES,
    SCAN_INTERVAL_MINUTES,
    power_option_key,
)
from custom_components.klereo.models import (
    KlereoPoolDetails,
    KlereoSystemData,
    KlereoSystemInfo,
)
from custom_components.klereo.sensor import _extract_sensors

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator carrying one system and no probes."""
    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.data = {
        "SYS1": KlereoSystemData(
            info=KlereoSystemInfo(id_system="SYS1", pool_nickname="My Pool"),
            details=KlereoPoolDetails(),
        )
    }
    return coordinator


def _extract(mock_coordinator, options=None, **containers):
    """Install the payload in the coordinator, then discover from it.

    Both halves matter: discovery reads the details it is handed, and the entities then
    read the coordinator. Handing one payload to discovery while the coordinator holds
    another tests a mismatch no installation can produce.
    """
    details = KlereoPoolDetails(**containers)
    mock_coordinator.data["SYS1"].details = details
    return _extract_sensors(mock_coordinator, "SYS1", details, options)


def _uids(mock_coordinator, options=None, **containers):
    return [uid for uid, _ in _extract(mock_coordinator, options, **containers)]


def _energy(mock_coordinator, key, options=None, **containers):
    for uid, entity in _extract(mock_coordinator, options, **containers):
        if uid == f"SYS1_energy_{key}":
            return entity
    return None


class TestNoPowerNoEntity:
    """🔴 The control that carries this ticket.

    Every other assertion in this file is also satisfied by an implementation that
    defaults the power to zero: a pump at rest reads `0.0 kWh` whether the reading is
    right or invented. Only these tests separate the two.
    """

    def test_an_equipment_with_no_power_entered_creates_no_energy_entity(self, mock_coordinator):
        """The counter is on the wire, the watt is not — so the kWh do not exist."""
        uids = _uids(mock_coordinator, params={"Filtration_TotalTime": 5402642})

        assert "SYS1_energy_Filtration_Total" not in uids

    def test_no_options_at_all_creates_no_energy_entity(self, mock_coordinator):
        """An entry that has never opened the options form is the common case, not an edge."""
        uids = _uids(mock_coordinator, None, params={"Filtration_TotalTime": 5402642})

        assert not [uid for uid in uids if uid.startswith("SYS1_energy_")]

    def test_zero_watts_creates_no_energy_entity(self, mock_coordinator):
        """Zero is how the form clears a power, and no equipment consumes zero.

        Honouring it literally would build the exact entity this class exists to refuse.
        """
        uids = _uids(
            mock_coordinator,
            {power_option_key("Filtration"): 0},
            params={"Filtration_TotalTime": 5402642},
        )

        assert "SYS1_energy_Filtration_Total" not in uids

    def test_an_unreadable_power_creates_no_energy_entity(self, mock_coordinator):
        """Options are persisted JSON; a value we cannot read is not a measurement."""
        uids = _uids(
            mock_coordinator,
            {power_option_key("Filtration"): "n/a"},
            params={"Filtration_TotalTime": 5402642},
        )

        assert "SYS1_energy_Filtration_Total" not in uids

    def test_a_power_for_one_equipment_does_not_meter_another(self, mock_coordinator):
        """Positive and negative in one payload: the option is per equipment.

        Without this, "the entity appeared" would be compatible with a single global
        power applied to every counter the payload carries.
        """
        uids = _uids(
            mock_coordinator,
            {power_option_key("Filtration"): 750},
            params={"Filtration_TotalTime": 3600, "Chauff_TotalTime": 3600},
        )

        assert "SYS1_energy_Filtration_Total" in uids
        assert "SYS1_energy_Chauff_Total" not in uids

    def test_a_power_without_its_counter_creates_no_energy_entity(self, mock_coordinator):
        """The other half of the gate: a watt alone describes equipment that never ran.

        And `0` would be the wrong report for it — on a `total_increasing` Home Assistant
        reads a zero as a counter reset, not as "we do not know".
        """
        uids = _uids(
            mock_coordinator,
            {power_option_key("Chauff"): 2500},
            params={"Filtration_TotalTime": 3600},
        )

        assert "SYS1_energy_Chauff_Total" not in uids
        assert "SYS1_energy_Chauff_Today" not in uids


class TestTheEnergyEntity:
    """The arithmetic, and the entity shape the Energy dashboard needs."""

    def test_total_energy_is_run_time_times_power(self, mock_coordinator):
        """3600 s at 750 W is 0.75 kWh — `× watts / 3600 / 1000`."""
        sensor = _energy(
            mock_coordinator, "Filtration_Total",
            options={power_option_key("Filtration"): 750},
            params={"Filtration_TotalTime": 3600},
        )

        assert sensor.native_value == 0.75

    def test_the_daily_counter_is_metered_by_the_same_power(self, mock_coordinator):
        """@StephanH27's own reading: 7869 s of filtration at 750 W."""
        sensor = _energy(
            mock_coordinator, "Filtration_Today",
            options={power_option_key("Filtration"): 750},
            params={"Filtration_TodayTime": 7869},
        )

        assert sensor.native_value == pytest.approx(1.64, abs=0.005)

    def test_the_entity_is_shaped_for_the_energy_dashboard(self, mock_coordinator):
        """kWh, `energy`, `total_increasing` — anything else the dashboard will not offer."""
        sensor = _energy(
            mock_coordinator, "Filtration_Total",
            options={power_option_key("Filtration"): 750},
            params={"Filtration_TotalTime": 3600},
        )

        assert sensor.native_unit_of_measurement == "kWh"
        assert sensor.device_class == "energy"
        assert sensor.state_class == "total_increasing"

    def test_the_entity_is_named_after_its_equipment(self, mock_coordinator):
        """`Heating Energy Total`, beside the existing `Heating Time Total`."""
        sensor = _energy(
            mock_coordinator, "Chauff_Total",
            options={power_option_key("Chauff"): 2500},
            params={"Chauff_TotalTime": 249307},
        )

        assert sensor.name == "Heating Energy Total"

    def test_a_fractional_power_is_not_truncated_to_an_integer(self, mock_coordinator):
        """A plate rating is not always whole, and `int()` on it would be our own error.

        The reading is rounded to the watt-hour, so the case is chosen to separate 750.5
        from both of its neighbours at that resolution: 10 h at 750 W is 7.5 kWh exactly.
        """
        sensor = _energy(
            mock_coordinator, "Filtration_Total",
            options={power_option_key("Filtration"): 750.5},
            params={"Filtration_TotalTime": 36000},
        )

        assert sensor.native_value == 7.505

    def test_the_energy_refreshes_with_the_payload(self, mock_coordinator):
        """Should recompute on update, not pin the value taken at discovery."""
        sensor = _energy(
            mock_coordinator, "Filtration_Total",
            options={power_option_key("Filtration"): 750},
            params={"Filtration_TotalTime": 3600},
        )
        sensor.async_write_ha_state = MagicMock()
        assert sensor.native_value == 0.75

        mock_coordinator.data["SYS1"].details.params["Filtration_TotalTime"] = 7200
        sensor._handle_coordinator_update()

        assert sensor.native_value == 1.5

    def test_a_counter_that_stops_being_readable_is_unknown_not_a_crash(self, mock_coordinator):
        """`None` is the honest report; a number here would be the #105 failure in kWh."""
        sensor = _energy(
            mock_coordinator, "Filtration_Total",
            options={power_option_key("Filtration"): 750},
            params={"Filtration_TotalTime": 3600},
        )
        sensor.async_write_ha_state = MagicMock()

        mock_coordinator.data["SYS1"].details.params["Filtration_TotalTime"] = "n/a"
        sensor._handle_coordinator_update()

        assert sensor.native_value is None

    def test_the_hybrid_counter_is_metered_from_extra_params(self, mock_coordinator):
        """`HybChl_*` arrives in `ExtraParams`, not `params` — the same three containers."""
        sensor = _energy(
            mock_coordinator, "HybChl_Total",
            options={power_option_key("HybChl"): 60},
            extra_params={"HybChl_TotalTime": 3600},
        )

        assert sensor.native_value == 0.06


class TestEveryMeteredEquipmentIsOfferedOne:
    """The table is built from `COUNTER_EQUIPMENT`, so it cannot drift away from it."""

    def test_each_equipment_and_period_has_an_energy_counter(self):
        assert set(ENERGY_COUNTER_TYPES) == {
            f"{prefix}_{period}"
            for prefix in COUNTER_EQUIPMENT
            for period in ("Today", "Total")
        }

    def test_every_energy_counter_reads_an_existing_time_counter(self):
        """🔴 Its source must be a key the platform already parses, not a guessed name.

        A source nobody sends produces an entity nobody sees, and the failure looks like
        absent hardware rather than a typo.
        """
        assert {spec["source"] for spec in ENERGY_COUNTER_TYPES.values()} <= set(
            PARAM_COUNTER_TYPES
        )

    def test_the_electrolysis_production_counter_is_not_metered(self):
        """`Elec_GramDone` is milligrams of chlorine, not seconds. Multiplying it by a
        watt would yield a number in kWh that means nothing at all."""
        assert "Elec_GramDone" not in {
            spec["source"] for spec in ENERGY_COUNTER_TYPES.values()
        }


class TestTheExistingTimeSensorsAreIntact:
    """We add beside, we never replace.

    `Filtration Time Today` and its four siblings are entities people have already wired
    into their automations. An energy entity that took their place would answer #163 by
    breaking every install that reads them.
    """

    def test_the_time_counter_survives_a_power_being_entered(self, mock_coordinator):
        uids = _uids(
            mock_coordinator,
            {power_option_key("Filtration"): 750},
            params={"Filtration_TodayTime": 7869, "Filtration_TotalTime": 5402642},
        )

        assert "SYS1_param_Filtration_TodayTime" in uids
        assert "SYS1_param_Filtration_TotalTime" in uids

    def test_the_time_counter_is_untouched_by_the_power(self, mock_coordinator):
        """Still seconds, still a duration — the watt changes the new entity, not this one."""
        sensor = next(
            entity
            for uid, entity in _extract(
                mock_coordinator,
                {power_option_key("Filtration"): 750},
                params={"Filtration_TotalTime": 3600},
            )
            if uid == "SYS1_param_Filtration_TotalTime"
        )

        assert sensor.native_value == 3600
        assert sensor.native_unit_of_measurement == "s"
        assert sensor.device_class == "duration"


class TestTheOptionsForm:
    """The watt is a user entry, so the form is half the feature."""

    def test_a_power_can_be_entered_for_each_metered_equipment(self):
        schema = options_schema(current=SCAN_INTERVAL_MINUTES)
        entered = {"scan_interval": SCAN_INTERVAL_MINUTES} | {
            power_option_key(prefix): 750 for prefix in COUNTER_EQUIPMENT
        }

        assert schema(entered) == entered

    def test_leaving_every_power_blank_stores_none_of_them(self):
        """🔴 The form half of the negative control.

        A `vol.Optional` carrying a default would write a power into the entry the user
        never entered, and the gate downstream would then be reading our own invention.
        """
        schema = options_schema(current=SCAN_INTERVAL_MINUTES)

        assert schema({"scan_interval": SCAN_INTERVAL_MINUTES}) == {
            "scan_interval": SCAN_INTERVAL_MINUTES
        }

    def test_a_negative_power_is_refused(self):
        schema = options_schema(current=SCAN_INTERVAL_MINUTES)

        with pytest.raises(vol.Invalid):
            schema({"scan_interval": SCAN_INTERVAL_MINUTES,
                    power_option_key("Filtration"): -750})

    def test_zero_is_accepted_by_the_form_and_means_no_entity(self):
        """The way to remove an energy entity is to clear its power, so the form must
        take the value back. `TestNoPowerNoEntity` holds the other end."""
        schema = options_schema(current=SCAN_INTERVAL_MINUTES)

        assert schema({"scan_interval": SCAN_INTERVAL_MINUTES,
                       power_option_key("Filtration"): 0})[
            power_option_key("Filtration")
        ] == 0

    def test_an_entered_power_is_offered_back_on_the_next_visit(self):
        """A form that forgets what is stored invites the user to re-enter it, or to
        assume it was never saved and clear it."""
        schema = options_schema(
            current=SCAN_INTERVAL_MINUTES,
            options={power_option_key("Filtration"): 750},
        )
        marker = next(
            key for key in schema.schema if str(key) == power_option_key("Filtration")
        )

        assert marker.description["suggested_value"] == 750


class TestTheFormExplainsWhereTheWattComesFrom:
    """A power field with no explanation reads as something the integration measures.

    Same reasoning as the scan-interval floor: the places that must agree are checked, not
    trusted.
    """

    def _strings(self, name):
        return json.loads(
            (REPO_ROOT / "custom_components/klereo" / name).read_text(encoding="utf-8")
        )["options"]["step"]["init"]

    @pytest.mark.parametrize("name", ["strings.json", "translations/en.json"])
    def test_every_power_field_is_labelled(self, name):
        labels = self._strings(name)["data"]

        for prefix in COUNTER_EQUIPMENT:
            assert power_option_key(prefix) in labels

    @pytest.mark.parametrize("name", ["strings.json", "translations/en.json"])
    def test_the_form_says_the_power_is_the_user_s_own_figure(self, name):
        descriptions = self._strings(name)["data_description"]

        for prefix in COUNTER_EQUIPMENT:
            assert power_option_key(prefix) in descriptions
