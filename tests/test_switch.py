"""Tests for Klereo switch entities."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.klereo.api import (
    HEAT_MODE_HEATING,
    HEAT_MODE_STOP,
    OUT_IDX_HEATING,
    OUT_MODE_MAN,
    OUT_STATE_AUTO,
    OUT_STATE_OFF,
    OUT_STATE_ON,
)
from custom_components.klereo.models import (
    KlereoOutput,
    KlereoPoolDetails,
    KlereoSystemData,
    KlereoSystemInfo,
)
from custom_components.klereo.switch import KlereoSwitch, _extract_switches


def _make_output(**kwargs) -> KlereoOutput:
    """Create a KlereoOutput with defaults."""
    defaults = {"index": 0, "status": 1, "mode": 0, "type": 0}
    defaults.update(kwargs)
    return KlereoOutput(**defaults)


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator."""
    output = _make_output()
    coordinator = MagicMock()
    coordinator.api = AsyncMock()
    coordinator.api.set_output.return_value = {"response": "ok"}
    coordinator.async_request_refresh = AsyncMock()
    coordinator.async_set_output = AsyncMock()
    coordinator.data = {
        "SYS1": KlereoSystemData(
            info=KlereoSystemInfo(id_system="SYS1", pool_nickname="My Pool"),
            details=KlereoPoolDetails(
                probes=[],
                outs=[output],
                regul_modes={},
                probe_index={},
                output_index={0: output},
            ),
        )
    }
    return coordinator


class TestKlereoSwitch:
    """Tests for KlereoSwitch."""

    def test_creates_with_known_index(self, mock_coordinator):
        """Should use OUTPUT_NAMES for known indices."""
        output = _make_output()
        switch = KlereoSwitch(mock_coordinator, "SYS1", output)
        assert switch._attr_name == "Lighting"
        assert switch._attr_unique_id == "SYS1_output_0"

    def test_is_on_when_status_equals_one(self, mock_coordinator):
        """Should be ON when status == OUT_STATE_ON (1)."""
        output = _make_output(status=1)
        switch = KlereoSwitch(mock_coordinator, "SYS1", output)
        assert switch._attr_is_on is True

    def test_is_off_when_status_equals_zero(self, mock_coordinator):
        """Should be OFF when status == 0."""
        output = _make_output(status=0)
        switch = KlereoSwitch(mock_coordinator, "SYS1", output)
        assert switch._attr_is_on is False

    def test_is_on_when_status_is_string_one(self, mock_coordinator):
        """Should be ON when status is string '1' (API may return strings)."""
        output = _make_output(status="1")
        switch = KlereoSwitch(mock_coordinator, "SYS1", output)
        assert switch._attr_is_on is True

    def test_is_off_when_status_is_string_zero(self, mock_coordinator):
        """Should be OFF when status is string '0'."""
        output = _make_output(status="0")
        switch = KlereoSwitch(mock_coordinator, "SYS1", output)
        assert switch._attr_is_on is False

    def test_is_off_when_status_is_none(self, mock_coordinator):
        """Should be OFF when status is None."""
        output = _make_output(status=None)
        switch = KlereoSwitch(mock_coordinator, "SYS1", output)
        assert switch._attr_is_on is False

    async def test_turn_on_calls_api(self, mock_coordinator):
        """turn_on should call async_set_output with correct args."""
        output = _make_output(status=0)
        switch = KlereoSwitch(mock_coordinator, "SYS1", output)
        switch.async_write_ha_state = MagicMock()
        await switch.async_turn_on()
        mock_coordinator.async_set_output.assert_called_once_with(
            "SYS1", 0, OUT_MODE_MAN, OUT_STATE_ON
        )
        assert switch._attr_is_on is True

    async def test_turn_off_calls_api(self, mock_coordinator):
        """turn_off should call async_set_output with correct args."""
        output = _make_output(status=1)
        switch = KlereoSwitch(mock_coordinator, "SYS1", output)
        switch.async_write_ha_state = MagicMock()
        await switch.async_turn_off()
        mock_coordinator.async_set_output.assert_called_once_with(
            "SYS1", 0, OUT_MODE_MAN, OUT_STATE_OFF
        )
        assert switch._attr_is_on is False

    async def test_turn_on_error_raises_ha_error(self, mock_coordinator):
        """turn_on should raise HomeAssistantError on coordinator failure."""
        from homeassistant.exceptions import HomeAssistantError
        mock_coordinator.async_set_output.side_effect = HomeAssistantError("Failed to set output 0: API down")
        output = _make_output(status=0)
        switch = KlereoSwitch(mock_coordinator, "SYS1", output)
        switch.async_write_ha_state = MagicMock()
        with pytest.raises(HomeAssistantError, match="Failed to set output"):
            await switch.async_turn_on()

    def test_find_my_output_uses_index(self, mock_coordinator):
        """Should find output data via output_index."""
        output = _make_output()
        switch = KlereoSwitch(mock_coordinator, "SYS1", output)
        found = switch._find_my_output()
        assert found is not None
        assert found.status == 1


class TestKlereoHeatingSwitch:
    """Output 4 carries the KlereoTherm mode in newMode, not the output mode.

    Upstream: MrWaloo/jeedom-klereo core/class/klereo.class.php, _HEAT_MODE_*
    at l.1377-1380 and the `elseif ($outIndex === 4)` branch at l.1525+.
    Forgejo #55 / GitHub #58.
    """

    @pytest.fixture
    def heating_coordinator(self, mock_coordinator):
        """Swap the fixture's output for the heating one (index 4)."""
        output = _make_output(index=OUT_IDX_HEATING, status=0, mode=0)
        details = mock_coordinator.data["SYS1"].details
        details.outs = [output]
        details.output_index = {OUT_IDX_HEATING: output}
        return mock_coordinator

    async def test_turn_on_sends_heat_mode_not_manual(self, heating_coordinator):
        """turn_on must send HEAT_MODE_HEATING/AUTO, never OUT_MODE_MAN (= Off here)."""
        output = _make_output(index=OUT_IDX_HEATING, status=0, mode=0)
        switch = KlereoSwitch(heating_coordinator, "SYS1", output)
        switch.async_write_ha_state = MagicMock()
        await switch.async_turn_on()
        heating_coordinator.async_set_output.assert_called_once_with(
            "SYS1", OUT_IDX_HEATING, HEAT_MODE_HEATING, OUT_STATE_AUTO
        )
        assert switch._attr_is_on is True

    async def test_turn_off_sends_heat_mode_stop(self, heating_coordinator):
        """turn_off must send HEAT_MODE_STOP/OFF."""
        output = _make_output(index=OUT_IDX_HEATING, status=2, mode=3)
        switch = KlereoSwitch(heating_coordinator, "SYS1", output)
        switch.async_write_ha_state = MagicMock()
        await switch.async_turn_off()
        heating_coordinator.async_set_output.assert_called_once_with(
            "SYS1", OUT_IDX_HEATING, HEAT_MODE_STOP, OUT_STATE_OFF
        )
        assert switch._attr_is_on is False

    async def test_other_outputs_keep_manual_mode(self, mock_coordinator):
        """Control: the generic branch is untouched — this is why the light works."""
        output = _make_output(index=0, status=0)
        switch = KlereoSwitch(mock_coordinator, "SYS1", output)
        switch.async_write_ha_state = MagicMock()
        await switch.async_turn_on()
        mock_coordinator.async_set_output.assert_called_once_with(
            "SYS1", 0, OUT_MODE_MAN, OUT_STATE_ON
        )

    def test_is_on_when_heating_state_is_auto(self, heating_coordinator):
        """status == 2 (AUTO) means the KlereoTherm is running, not off."""
        output = _make_output(index=OUT_IDX_HEATING, status=OUT_STATE_AUTO, mode=3)
        switch = KlereoSwitch(heating_coordinator, "SYS1", output)
        assert switch._attr_is_on is True

    def test_is_off_when_heating_state_is_off(self, heating_coordinator):
        """status == 0 means stopped."""
        output = _make_output(index=OUT_IDX_HEATING, status=OUT_STATE_OFF, mode=0)
        switch = KlereoSwitch(heating_coordinator, "SYS1", output)
        assert switch._attr_is_on is False


class TestProOutputsAreGatedOnAccess:
    """Tests that outputs 2, 3, 8 and 15 stop being offered to accounts that cannot use them.

    Klereo's documentation says `newMode` is "NON VALABLE POUR LES SORTIES 2,3,4,8,15".
    1.5.3 handled output 4; the other four were never handled. Upstream does not try to
    reinterpret `newMode` there either — it refuses to command them below professional
    access (`klereo.class.php:1188`), which is the only defensible position while the
    semantics on those outputs remain unknown.

    Since #95 a write to one of them surfaces status 13 instead of failing silently, so
    the user now sees errors on entities that should never have been offered.
    """

    def _details(self, access, indices=(0, 2, 3, 4, 8, 15)):
        return KlereoPoolDetails(
            outs=[_make_output(index=i) for i in indices],
            access=access,
        )

    def _indices(self, coordinator, details):
        return sorted(e._output_index for _, e in _extract_switches(coordinator, "SYS1", details))

    def test_pro_outputs_are_dropped_below_professional_access(self, mock_coordinator):
        """Should not offer 2, 3, 8 and 15 to an end-customer account."""
        result = self._indices(mock_coordinator, self._details(access=10))
        assert result == [0, 4]

    def test_pro_outputs_are_kept_at_professional_access(self, mock_coordinator):
        """Positive control: access 20 keeps every output.

        Without this, "the entities are gone" would be compatible with a gate that removes
        them for everyone — which would be a worse bug than the one being fixed.
        """
        result = self._indices(mock_coordinator, self._details(access=20))
        assert result == [0, 2, 3, 4, 8, 15]

    def test_pro_outputs_are_kept_above_professional_access(self, mock_coordinator):
        """Should compare on ordering, not equality — Klereo accounts are 25 and above."""
        result = self._indices(mock_coordinator, self._details(access=25))
        assert result == [0, 2, 3, 4, 8, 15]

    def test_an_unknown_access_never_gates(self, mock_coordinator):
        """🔴 Should keep every output when `access` is absent from the payload.

        `access` is optional (`models.py`), and "we do not know" must never remove an
        entity a working installation already has. This mirrors `_is_offered` in
        `number.py`, whose docstring states the same rule: only a value we can read, and
        that says no, removes anything.
        """
        result = self._indices(mock_coordinator, self._details(access=None))
        assert result == [0, 2, 3, 4, 8, 15]

    def test_ordinary_outputs_are_never_gated(self, mock_coordinator):
        """Absurdity control: a read-only account keeps lighting, filtration and heating."""
        details = self._details(access=5, indices=(0, 1, 4, 5))
        assert self._indices(mock_coordinator, details) == [0, 1, 4, 5]
