"""Tests for Klereo select entities."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.klereo.api import (
    HEAT_MODE_AUTO,
    HEAT_MODE_HEATING,
    HEAT_MODE_STOP,
    OUT_IDX_HEATING,
    OUT_MODE_MAN,
    OUT_MODE_TIME_SLOTS,
    OUT_MODE_TIMER,
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
from custom_components.klereo.select import KlereoOutputModeSelect, _extract_selects


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


class TestKlereoOutputModeSelect:
    """Tests for KlereoOutputModeSelect."""

    def test_creates_with_known_index(self, mock_coordinator):
        """Should use OUTPUT_NAMES for known indices with ' Mode' suffix."""
        output = _make_output()
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", output)
        assert select._attr_name == "Lighting Mode"
        assert select._attr_unique_id == "SYS1_output_mode_0"

    def test_creates_with_unknown_index(self, mock_coordinator):
        """Should fall back to 'Output N Mode' for unknown indices."""
        output = _make_output(index=99)
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", output)
        assert select._attr_name == "Output 99 Mode"

    # `test_options_list` lived here and asserted exactly four options. It is superseded by
    # `TestDocumentedOutputModes::test_exposes_every_writable_mode` (#105): Klereo
    # documents eight writable modes, so "all four" was a statement about the integration's
    # table, not about the API.

    def test_current_option_manual(self, mock_coordinator):
        """Should read 'Manual' from mode=0."""
        output = _make_output(mode=0)
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", output)
        assert select._attr_current_option == "Manual"

    def test_current_option_timer(self, mock_coordinator):
        """Should read 'Timer' from mode=2."""
        output = _make_output(mode=2)
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", output)
        assert select._attr_current_option == "Timer"

    def test_current_option_string_mode(self, mock_coordinator):
        """Should handle string mode values from API."""
        output = _make_output(mode="3")
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", output)
        assert select._attr_current_option == "Regulation"

    # `test_current_option_none_defaults_manual` lived here and asserted that a missing mode
    # reads as "Manual". That was the defect of #105 written down as an expectation — an
    # absent value rendered as a specific, plausible, wrong one. It is superseded by
    # `TestDocumentedOutputModes::test_a_missing_mode_is_not_reported_as_manual`.

    async def test_select_option_non_manual_sends_auto(self, mock_coordinator):
        """Timer hands control to the box, so newState is AUTO, not the ON/OFF status."""
        output = _make_output(status=1)
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", output)
        select.async_write_ha_state = MagicMock()
        await select.async_select_option("Timer")
        mock_coordinator.async_set_output.assert_called_once_with(
            "SYS1", 0, OUT_MODE_TIMER, OUT_STATE_AUTO
        )
        assert select._attr_current_option == "Timer"

    async def test_select_option_manual_preserves_off_state(self, mock_coordinator):
        """Manual is the one mode that keeps the ON/OFF state."""
        output = _make_output(status=0, mode=OUT_MODE_TIME_SLOTS)
        # Update the coordinator data to match
        mock_coordinator.data["SYS1"].details.output_index[0] = output
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", output)
        select.async_write_ha_state = MagicMock()
        await select.async_select_option("Manual")
        mock_coordinator.async_set_output.assert_called_once_with(
            "SYS1", 0, OUT_MODE_MAN, OUT_STATE_OFF
        )

    def test_handle_coordinator_update_refreshes(self, mock_coordinator):
        """Should update current option from coordinator data."""
        output = _make_output(mode=0)
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", output)
        select.async_write_ha_state = MagicMock()
        # Update the output in coordinator data
        mock_coordinator.data["SYS1"].details.output_index[0] = _make_output(mode=3)
        select._handle_coordinator_update()
        assert select._attr_current_option == "Regulation"
        assert select._attr_available is True

    def test_handle_coordinator_update_missing_system(self, mock_coordinator):
        """Should mark unavailable when system disappears."""
        output = _make_output()
        select = KlereoOutputModeSelect(mock_coordinator, "MISSING", output)
        select.async_write_ha_state = MagicMock()
        select._handle_coordinator_update()
        assert select._attr_available is False

    def test_device_info(self, mock_coordinator):
        """Should return device info from coordinator data."""
        output = _make_output()
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", output)
        info = select.device_info
        assert ("klereo", "SYS1") in info["identifiers"]
        assert info["name"] == "My Pool"

    async def test_select_option_error_propagates(self, mock_coordinator):
        """Should propagate HomeAssistantError from coordinator."""
        from homeassistant.exceptions import HomeAssistantError
        mock_coordinator.async_set_output.side_effect = HomeAssistantError("Failed to set output 0: API down")
        output = _make_output(status=1)
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", output)
        select.async_write_ha_state = MagicMock()
        with pytest.raises(HomeAssistantError, match="Failed to set output"):
            await select.async_select_option("Regulation")


class TestDocumentedOutputModes:
    """Tests the ten output modes Klereo's API documentation describes (#105).

    `OUTPUT_MODES` carried four. The documentation (`docs/klereo-api.md`) lists ten, of
    which two are marked *USAGE INTERNE — ne pas utiliser*. The upstream plugin, written
    independently, validates exactly `{0,1,2,3,4,6,8,9}` for writes — the same ten minus
    the same two (`klereo.class.php:1198`). That agreement is what makes this fixable
    without hardware.

    The defect was not a missing option: it was `self._modes[0]` as a fallback, which
    reported any unknown mode as **Manual** — a plausible, wrong value indistinguishable
    from an output genuinely in Manual.
    """

    def test_exposes_every_writable_mode(self, mock_coordinator):
        """Should offer the eight modes Klereo accepts, in documented order."""
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", _make_output())
        assert select._attr_options == [
            "Manual",
            "Time Slots",
            "Timer",
            "Regulation",
            "Filtration Sync",
            "Maintenance",
            "Pulse",
            "Automatic",
        ]

    def test_does_not_offer_the_internal_use_modes(self, mock_coordinator):
        """Should never offer 5 or 7 — the documentation marks both 'ne pas utiliser'.

        Offering them would let a user send a value Klereo documents as forbidden.
        """
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", _make_output())
        assert len(select._attr_options) == 8

    @pytest.mark.parametrize(
        ("mode", "label"),
        [(4, "Filtration Sync"), (6, "Maintenance"), (8, "Pulse"), (9, "Automatic")],
    )
    def test_reads_the_modes_that_used_to_read_as_manual(self, mock_coordinator, mode, label):
        """Should report the real mode for the four that fell through to Manual."""
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", _make_output(mode=mode))
        assert select._attr_current_option == label

    @pytest.mark.parametrize("mode", [5, 7])
    def test_an_internal_use_mode_is_not_reported_as_manual(self, mock_coordinator, mode):
        """Should report nothing rather than Manual for a mode it cannot offer."""
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", _make_output(mode=mode))
        assert select._attr_current_option is None

    def test_an_unknown_mode_is_not_reported_as_manual(self, mock_coordinator):
        """Absurdity control: a mode absent from the documentation must not read as Manual.

        The documentation is not guaranteed exhaustive, so this is the case that must keep
        working after the table is widened — widening it is not what fixes the defect.
        """
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", _make_output(mode=99))
        assert select._attr_current_option is None

    def test_an_unreadable_mode_is_not_reported_as_manual(self, mock_coordinator):
        """Should report nothing when the API sends a mode that will not parse as an int."""
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", _make_output(mode="banana"))
        assert select._attr_current_option is None

    def test_a_missing_mode_is_not_reported_as_manual(self, mock_coordinator):
        """Should report nothing when the API sends no mode at all.

        Same defect as the others: 'we do not know' rendered as a specific, wrong answer.
        """
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", _make_output(mode=None))
        assert select._attr_current_option is None

    async def test_can_select_a_newly_exposed_mode(self, mock_coordinator):
        """Should write mode 4 with AUTO state — only Manual carries an ON/OFF state."""
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", _make_output())
        select.hass = MagicMock()
        select.async_write_ha_state = MagicMock()

        await select.async_select_option("Filtration Sync")

        mock_coordinator.async_set_output.assert_awaited_once_with("SYS1", 0, 4, 2)

    def test_the_heating_output_keeps_its_four_klereotherm_modes(self, mock_coordinator):
        """Negative control on scope: widening the output table must not touch output 4.

        Output 4 carries the KlereoTherm mode, and upstream validates `{0,1,2,3}` there on
        the very same line that validates the eight elsewhere.
        """
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", _make_output(index=4))
        assert select._attr_options == ["Off", "Auto", "Cooling", "Heating"]


class TestKlereoHeatingModeSelect:
    """Output 4's select must offer KlereoTherm modes, not output modes.

    Upstream: klereo.class.php l.1377-1380 (_HEAT_MODE_*) and l.1525+
    (`elseif ($outIndex === 4)`), where newState = newMode > 0 ? AUTO : OFF.
    Forgejo #55 / GitHub #58.
    """

    @pytest.fixture
    def heating_coordinator(self, mock_coordinator):
        """Swap the fixture's output for the heating one (index 4)."""
        output = _make_output(index=OUT_IDX_HEATING, status=OUT_STATE_AUTO, mode=HEAT_MODE_AUTO)
        details = mock_coordinator.data["SYS1"].details
        details.outs = [output]
        details.output_index = {OUT_IDX_HEATING: output}
        return mock_coordinator

    def test_options_are_heat_modes(self, heating_coordinator):
        """Manual/Time Slots/Timer/Regulation are meaningless on output 4."""
        output = _make_output(index=OUT_IDX_HEATING, mode=HEAT_MODE_AUTO)
        select = KlereoOutputModeSelect(heating_coordinator, "SYS1", output)
        assert select.options == ["Off", "Auto", "Cooling", "Heating"]

    def test_current_option_reads_heat_mode(self, heating_coordinator):
        """mode == 3 is Heating, not Regulation."""
        output = _make_output(index=OUT_IDX_HEATING, mode=HEAT_MODE_HEATING)
        select = KlereoOutputModeSelect(heating_coordinator, "SYS1", output)
        assert select._attr_current_option == "Heating"

    async def test_select_heating_sends_auto_state(self, heating_coordinator):
        """A non-Off heat mode pairs with newState = AUTO (2), never the on/off status."""
        output = _make_output(index=OUT_IDX_HEATING, status=OUT_STATE_OFF, mode=HEAT_MODE_STOP)
        select = KlereoOutputModeSelect(heating_coordinator, "SYS1", output)
        select.async_write_ha_state = MagicMock()
        await select.async_select_option("Heating")
        heating_coordinator.async_set_output.assert_called_once_with(
            "SYS1", OUT_IDX_HEATING, HEAT_MODE_HEATING, OUT_STATE_AUTO
        )

    async def test_select_off_sends_off_state(self, heating_coordinator):
        """Off pairs with newState = OFF (0)."""
        output = _make_output(index=OUT_IDX_HEATING, status=OUT_STATE_AUTO, mode=HEAT_MODE_HEATING)
        select = KlereoOutputModeSelect(heating_coordinator, "SYS1", output)
        select.async_write_ha_state = MagicMock()
        await select.async_select_option("Off")
        heating_coordinator.async_set_output.assert_called_once_with(
            "SYS1", OUT_IDX_HEATING, HEAT_MODE_STOP, OUT_STATE_OFF
        )

    def test_other_outputs_keep_output_modes(self, mock_coordinator):
        """Control: every other output still offers the output modes, not the heating ones.

        Asserted on membership rather than on the full list: this test exists to prove the
        two mode *families* stay apart, and #105 widened the output family from four to
        eight. Pinning the whole list here would make it fail on every future addition for
        a reason that has nothing to do with what it guards. The complete list is asserted
        once, in `TestDocumentedOutputModes`.
        """
        output = _make_output(index=0, mode=0)
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", output)
        assert "Manual" in select.options
        assert "Regulation" in select.options
        # "Off" and "Cooling" exist only in HEAT_MODES — their absence is the discriminator.
        assert "Off" not in select.options
        assert "Cooling" not in select.options


class TestNonManualModesSendAutoState:
    """Time Slots / Timer / Regulation pair with newState = AUTO on every output.

    Upstream klereo.class.php l.1641-1655: only OUT_MODE_MAN carries the on/off
    state; TIMER and TIME_SLOTS both send _OUT_STATE_AUTO. The filtration branch
    (l.1500+) does the same for REGUL.
    """

    async def test_time_slots_sends_auto(self, mock_coordinator):
        """Time Slots must send AUTO (2), not the preserved on/off status."""
        output = _make_output(index=0, status=OUT_STATE_ON, mode=0)
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", output)
        select.async_write_ha_state = MagicMock()
        await select.async_select_option("Time Slots")
        mock_coordinator.async_set_output.assert_called_once_with(
            "SYS1", 0, OUT_MODE_TIME_SLOTS, OUT_STATE_AUTO
        )

    async def test_regulation_sends_auto(self, mock_coordinator):
        """Regulation must send AUTO (2) too."""
        output = _make_output(index=1, status=OUT_STATE_OFF, mode=0)
        details = mock_coordinator.data["SYS1"].details
        details.outs = [output]
        details.output_index = {1: output}
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", output)
        select.async_write_ha_state = MagicMock()
        await select.async_select_option("Regulation")
        mock_coordinator.async_set_output.assert_called_once_with(
            "SYS1", 1, 3, OUT_STATE_AUTO
        )

    async def test_manual_still_preserves_on_off(self, mock_coordinator):
        """Control: Manual is the one mode that keeps the on/off state."""
        output = _make_output(index=0, status=OUT_STATE_ON, mode=OUT_MODE_TIMER)
        select = KlereoOutputModeSelect(mock_coordinator, "SYS1", output)
        select.async_write_ha_state = MagicMock()
        await select.async_select_option("Manual")
        mock_coordinator.async_set_output.assert_called_once_with(
            "SYS1", 0, 0, OUT_STATE_ON
        )


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
        return sorted(e._output_index for _, e in _extract_selects(coordinator, "SYS1", details))

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
