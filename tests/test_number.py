"""Tests for Klereo number entities."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.klereo.models import (
    KlereoPoolDetails,
    KlereoSystemData,
    KlereoSystemInfo,
)
from custom_components.klereo.number import KlereoNumber, _extract_numbers


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator."""
    coordinator = MagicMock()
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


class TestExtractNumbers:
    """Tests for which payloads do and do not produce a Water Setpoint entity.

    The point of #94 is that this entity is the integration's only `number`, so if the
    wrong container is read it exists for nobody — silently. A test that only proves the
    entity *appears* is not enough: the negative controls below are what prove the right
    container is read rather than a neighbouring one.
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
