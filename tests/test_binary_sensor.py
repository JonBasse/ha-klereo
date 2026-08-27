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
    # 🔴 Set EXPLICITLY. Left as a bare MagicMock attribute it is truthy but not `True`,
    # so `assert entity.available is True` would pass for a reason that is not the one
    # under test — `CoordinatorEntity.available` returns this value straight through.
    coordinator.last_update_success = True
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
        assert sensor.available is True

    def test_device_info(self, mock_coordinator):
        """Should return device info from coordinator data."""
        probe = _make_probe()
        sensor = KlereoBinarySensor(mock_coordinator, "SYS1", probe)
        info = sensor.device_info
        assert ("klereo", "SYS1") in info["identifiers"]
        assert info["name"] == "My Pool"


class TestAvailabilityOfBinarySensor:
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
        probe = _make_probe()
        return KlereoBinarySensor(mock_coordinator, system_id, probe)

    def test_available_while_the_payload_carries_it(self, mock_coordinator):
        """Positive control. Without it, "goes unavailable" is compatible with
        "always unavailable", and every other arm here would pass on a broken entity."""
        assert self._entity(mock_coordinator).available is True

    def test_unavailable_when_the_system_disappears(self, mock_coordinator):
        """A system absent from the payload takes its entities with it."""
        assert self._entity(mock_coordinator, "MISSING").available is False

    def test_unavailable_when_the_probe_disappears(self, mock_coordinator):
        """The narrower half: the system is still there, this probe is not.

        Distinct from the arm above on purpose — the base property only checks the system,
        so a subclass that forgot to narrow it would pass that one and fail this.
        """
        entity = self._entity(mock_coordinator)
        mock_coordinator.data["SYS1"].details.probe_index.clear()
        assert entity.available is False

    def test_unavailable_when_the_refresh_fails(self, mock_coordinator):
        """The half that already worked must survive: a failed refresh still bars."""
        mock_coordinator.last_update_success = False
        assert self._entity(mock_coordinator).available is False
