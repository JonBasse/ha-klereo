"""Tests for Klereo number entities."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.klereo.models import (
    KlereoPoolDetails,
    KlereoSystemData,
    KlereoSystemInfo,
)
from custom_components.klereo.number import KlereoNumber, _extract_numbers

_ABSENT = object()


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator."""
    coordinator = MagicMock()
    # 🔴 Set EXPLICITLY. Left as a bare MagicMock attribute it is truthy but not `True`,
    # so `assert entity.available is True` would pass for a reason that is not the one
    # under test — `CoordinatorEntity.available` returns this value straight through.
    coordinator.last_update_success = True
    coordinator.async_set_param = AsyncMock()
    coordinator.data = {
        "SYS1": KlereoSystemData(
            info=KlereoSystemInfo(id_system="SYS1", pool_nickname="My Pool"),
            details=KlereoPoolDetails(
                probes=[],
                outs=[],
                regul_modes={"ConsigneEau": 28, "ModeFiltration": 1},
                probe_index={},
                output_index={},
            ),
        )
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
        mock_coordinator.data["SYS1"].details.regul_modes["ConsigneEau"] = 35
        number._handle_coordinator_update()
        assert number._attr_native_value == 35
        assert number.available is True

    def test_device_info(self, mock_coordinator):
        """Should return device info from coordinator data."""
        number = KlereoNumber(mock_coordinator, "SYS1", "ConsigneEau", 28)
        info = number.device_info
        assert ("klereo", "SYS1") in info["identifiers"]
        assert info["name"] == "My Pool"


class TestExtractNumbers:
    """Tests for which payloads do and do not produce a Water Setpoint entity.

    The point of #94 is that a setpoint read from the wrong container exists for nobody —
    silently. A test that only proves the entity *appears* is not enough: the negative
    controls below are what prove the right container is read rather than a neighbouring
    one. (ConsigneEau was the integration's ONLY `number` until #128 added three more;
    those live in `TestAdvancedSetpoints`, with the sensor half in `test_sensor.py`.)
    """

    def _details(self, **kwargs):
        return KlereoPoolDetails(**kwargs)

    def _keys(self, details, coordinator):
        return [uid for uid, _ in _extract_numbers(coordinator, "SYS1", details)]

    def test_created_when_setpoint_only_in_params(self, mock_coordinator):
        """Should create the entity from a payload carrying ConsigneEau only in `params`."""
        details = self._details(params={"ConsigneEau": 28})
        assert self._keys(details, mock_coordinator) == ["SYS1_number_ConsigneEau"]

    def test_created_when_setpoint_only_in_regul_modes(self, mock_coordinator):
        """Should still create it from `RegulModes` — the change only adds a container."""
        details = self._details(regul_modes={"ConsigneEau": 28})
        assert self._keys(details, mock_coordinator) == ["SYS1_number_ConsigneEau"]

    def test_not_created_when_value_is_disabled_sentinel(self, mock_coordinator):
        """Should skip -2000, which upstream reads as 'setpoint disabled'."""
        details = self._details(params={"ConsigneEau": -2000})
        assert self._keys(details, mock_coordinator) == []

    def test_not_created_when_value_is_unknown_sentinel(self, mock_coordinator):
        """Should skip -1000, which upstream reads as 'value unknown'."""
        details = self._details(params={"ConsigneEau": -1000})
        assert self._keys(details, mock_coordinator) == []

    def test_not_created_when_access_below_minimum(self, mock_coordinator):
        """Should skip ConsigneEau for a read-only account (access 5 < 10)."""
        details = self._details(params={"ConsigneEau": 28}, access=5)
        assert self._keys(details, mock_coordinator) == []

    def test_created_when_access_sufficient(self, mock_coordinator):
        """Should create it for an end-customer account (access 10)."""
        details = self._details(params={"ConsigneEau": 28}, access=10)
        assert self._keys(details, mock_coordinator) == ["SYS1_number_ConsigneEau"]

    def test_created_when_access_unknown(self, mock_coordinator):
        """Should create it when the payload carries no access level.

        Unknown must not gate: a payload without the field would otherwise lose an entity
        it has today.
        """
        details = self._details(params={"ConsigneEau": 28}, access=None)
        assert self._keys(details, mock_coordinator) == ["SYS1_number_ConsigneEau"]

    def test_not_created_when_heater_has_no_setpoint(self, mock_coordinator):
        """Should skip ConsigneEau when HeaterMode is 3 — an on/off heat pump.

        Upstream gates on HeaterMode not in {0, 3}: 0 is no heat pump at all, 3 is an
        on/off one that takes no setpoint. Offering a setpoint there invents a control the
        hardware does not have.
        """
        for heater_mode in (0, 3):
            details = self._details(params={"ConsigneEau": 28, "HeaterMode": heater_mode})
            assert self._keys(details, mock_coordinator) == [], f"HeaterMode={heater_mode}"

    def test_created_when_heater_has_a_setpoint(self, mock_coordinator):
        """Should create it for HeaterMode 1 — a heat pump that does take a setpoint."""
        details = self._details(params={"ConsigneEau": 28, "HeaterMode": 1})
        assert self._keys(details, mock_coordinator) == ["SYS1_number_ConsigneEau"]

    def test_bounds_come_from_the_api(self, mock_coordinator):
        """Should prefer the API's EauMin/EauMax over the hard-coded 10-40."""
        details = self._details(params={"ConsigneEau": 28, "EauMin": 15, "EauMax": 32})
        (_, entity), = _extract_numbers(mock_coordinator, "SYS1", details)
        assert entity._attr_native_min_value == 15
        assert entity._attr_native_max_value == 32

    def test_bounds_fall_back_to_defaults(self, mock_coordinator):
        """Should keep 10-40 when the payload carries no bounds."""
        details = self._details(params={"ConsigneEau": 28})
        (_, entity), = _extract_numbers(mock_coordinator, "SYS1", details)
        assert entity._attr_native_min_value == 10
        assert entity._attr_native_max_value == 40

    def test_refreshes_value_from_params_container(self, mock_coordinator):
        """Should refresh from `params` too, not only from `RegulModes`.

        Creating the entity from `params` but refreshing only from `RegulModes` would pin
        it to its first reading forever — an entity that exists and never moves.
        """
        mock_coordinator.data["SYS1"].details.regul_modes = {}
        mock_coordinator.data["SYS1"].details.params = {"ConsigneEau": 28}
        number = KlereoNumber(mock_coordinator, "SYS1", "ConsigneEau", 28)
        number.async_write_ha_state = MagicMock()
        mock_coordinator.data["SYS1"].details.params["ConsigneEau"] = 31
        number._handle_coordinator_update()
        assert number._attr_native_value == 31


# A payload carrying all four writable setpoints and every key their guards read. Written
# as one dict the tests mutate a copy of, so that each negative control differs from the
# positive case by EXACTLY the field it is about — a fixture rebuilt per test drifts, and
# then a control that reddens proves nothing in particular.
FULL_SETPOINTS = {
    "ConsigneEau": 28, "EauMin": 15, "EauMax": 32, "HeaterMode": 1,
    "ConsignePH": 7.2, "pHMin": 6.8, "pHMax": 7.6, "pHMode": 1,
    "ConsigneRedox": 650, "OrpMin": 400, "OrpMax": 850,
    "ConsigneChlore": 1.2,
}

ALL_FOUR = [
    "SYS1_number_ConsigneEau",
    "SYS1_number_ConsignePH",
    "SYS1_number_ConsigneRedox",
    "SYS1_number_ConsigneChlore",
]


class TestAdvancedSetpoints:
    """Tests for the pH, Redox and chlorine setpoints promoted to writable in #128.

    Upstream gates all three on `access >= 16` and the pH one additionally on `pHMode > 0`
    (`klereo.class.php` l.877-880). Each control below moves ONE field and names which
    entity it must remove; a guard that removed more than its own would pass a test that
    only counted.

    ⚠️ What this bench CANNOT do is confirm a write succeeds. No installation in the file
    is known to sit at access 16, so every arm here measures which entity is OFFERED, and
    none measures what the API answers. A refusal would surface as status 13 since #115 —
    but only for someone who tries.
    """

    def _keys(self, coordinator, **overrides):
        settings = dict(FULL_SETPOINTS)
        for key, value in overrides.items():
            if value is _ABSENT:
                settings.pop(key, None)
            else:
                settings[key] = value
        access = settings.pop("_access", None)
        details = KlereoPoolDetails(params=settings, access=access)
        return [uid for uid, _ in _extract_numbers(coordinator, "SYS1", details)]

    def test_all_four_offered_at_advanced_access(self, mock_coordinator):
        """Positive case: access 16 offers every setpoint upstream can write."""
        assert self._keys(mock_coordinator, _access=16) == ALL_FOUR

    def test_bounds_come_from_the_payload(self, mock_coordinator):
        """Should read pHMin/pHMax and OrpMin/OrpMax, never the permissive fallbacks.

        The fallbacks are 0-14 and 0-1000; asserting the payload's narrower pair is what
        proves the right key names were used rather than a plausible neighbour.
        """
        details = KlereoPoolDetails(params=dict(FULL_SETPOINTS), access=16)
        bounds = {
            key.rsplit("_", 1)[-1]: (e._attr_native_min_value, e._attr_native_max_value)
            for key, e in _extract_numbers(mock_coordinator, "SYS1", details)
        }
        assert bounds["ConsignePH"] == (6.8, 7.6)
        assert bounds["ConsigneRedox"] == (400, 850)
        # Chlorine is hard-coded 0-5 upstream and carries NO bounds keys at all.
        assert bounds["ConsigneChlore"] == (0, 5)

    def test_bounds_fall_back_when_the_payload_carries_none(self, mock_coordinator):
        """Should fall back to the PERMISSIVE range, never to a plausible pool window.

        Reachable only on a payload with no pHMin/pHMax or OrpMin/OrpMax — which upstream
        does not handle at all. 0-14 is the total pH scale and 0-1000 the ORP convention:
        both are wide on purpose, because a narrow default silently clamps a real setpoint
        into a value the box never asked for, and the entity still looks healthy.

        This witness exists because a mutation narrowing pH to 6.8-7.8 reddened NOTHING.
        """
        settings = {k: v for k, v in FULL_SETPOINTS.items()
                    if k not in ("pHMin", "pHMax", "OrpMin", "OrpMax")}
        details = KlereoPoolDetails(params=settings, access=16)
        bounds = {
            key.rsplit("_", 1)[-1]: (e._attr_native_min_value, e._attr_native_max_value)
            for key, e in _extract_numbers(mock_coordinator, "SYS1", details)
        }
        assert bounds["ConsignePH"] == (0, 14)
        assert bounds["ConsigneRedox"] == (0, 1000)

    def test_end_customer_access_keeps_only_the_water_setpoint(self, mock_coordinator):
        """Negative control 1 — access 10 removes the three, and ConsigneEau REMAINS.

        The second half is the one that matters: a `min_access` guard written against the
        wrong constant would take the water setpoint down with them, and a test that only
        asserted the three had gone would stay green through it.
        """
        assert self._keys(mock_coordinator, _access=10) == ["SYS1_number_ConsigneEau"]

    def test_ph_mode_off_removes_the_ph_setpoint_alone(self, mock_coordinator):
        """Negative control 2 — pHMode 0 takes ConsignePH and nothing else."""
        assert self._keys(mock_coordinator, _access=16, pHMode=0) == [
            "SYS1_number_ConsigneEau",
            "SYS1_number_ConsigneRedox",
            "SYS1_number_ConsigneChlore",
        ]

    def test_absent_access_and_ph_mode_offer_everything(self, mock_coordinator):
        """Negative control 3 — unknown never bars, in both directions at once.

        This is the arm that decides the whole design: an installation whose payload
        carries neither field must keep every entity, because "we cannot read it" is not
        "the answer is no".
        """
        keys = self._keys(mock_coordinator, _access=_ABSENT, pHMode=_ABSENT)
        assert keys == ALL_FOUR

    def test_unreadable_ph_mode_does_not_bar(self, mock_coordinator):
        """A pHMode that is not a number is as unknown as a missing one."""
        for ph_mode in (None, "auto"):
            keys = self._keys(mock_coordinator, _access=16, pHMode=ph_mode)
            assert "SYS1_number_ConsignePH" in keys, f"pHMode={ph_mode!r}"

    def test_sentinel_removes_its_own_setpoint_only(self, mock_coordinator):
        """A disabled setpoint takes itself down and leaves its neighbours standing.

        Bioul carries `ConsigneEau: -2000` — a real payload, and the reason GitHub #55
        reported a missing entity that was never a defect.
        """
        keys = self._keys(mock_coordinator, _access=16, ConsigneRedox=-2000)
        assert keys == [
            "SYS1_number_ConsigneEau",
            "SYS1_number_ConsignePH",
            "SYS1_number_ConsigneChlore",
        ]


class TestAvailabilityOfNumber:
    """Three witnesses on `.available`, and NEVER on `_attr_available` (#130).

    `CoordinatorEntity.available` is a property returning `coordinator.last_update_success`,
    and a property shadows `_attr_available` completely. Every assertion in this repository
    used to read the attribute the code had just assigned, so it stayed green over a
    mechanism that reported nothing — the same failure as #115, a second time.

    Proof that the distinction is real, and not pedantry: before the fix, the three
    `_attr_available is False` assertions reddened while the three `is True` ones stayed
    green — because `_attr_available` defaults to `True`. They were passing for a reason
    that had nothing to do with the code under test.
    """

    def _entity(self, mock_coordinator, system_id="SYS1"):
        return KlereoNumber(mock_coordinator, system_id, "ConsigneEau", 28)

    def test_available_while_the_payload_carries_it(self, mock_coordinator):
        """Positive control. Without it, "goes unavailable" is compatible with
        "always unavailable", and every other arm here would pass on a broken entity."""
        assert self._entity(mock_coordinator).available is True

    def test_unavailable_when_the_system_disappears(self, mock_coordinator):
        """A system absent from the payload takes its entities with it."""
        assert self._entity(mock_coordinator, "MISSING").available is False

    def test_unavailable_when_the_refresh_fails(self, mock_coordinator):
        """The half that already worked must survive: a failed refresh still bars."""
        mock_coordinator.last_update_success = False
        assert self._entity(mock_coordinator).available is False
