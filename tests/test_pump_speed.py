"""Tests for the variable-speed ("analogue") Filtration pump.

Source: upstream Jeedom plugin `klereo.class.php` — see the full citation above
`OUT_IDX_FILTRATION` in `api.py`. ✅ `PumpMaxSpeed` is confirmed on five diagnostics
exports from one reporter, all under Regulation; the same exports settled that `status`
does not reliably track the live speed there but `real_status` does (full citation:
`models.KlereoOutput.real_status`). The switch deliberately does NOT follow the speed
under Manual (reverted on request) — only Regulation is special-cased.

What these tests hold throughout is the same property `test_optimistic_siblings.py` holds
for the heating output (#174): `switch.KlereoSwitch`, `select.KlereoOutputModeSelect` and
`number.KlereoPumpSpeedNumber` stay consistent with each other and with every other output.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.klereo.api import (
    OUT_IDX_FILTRATION,
    OUT_MODE_MAN,
    OUT_MODE_REGUL,
    OUT_STATE_OFF,
    KlereoApi,
)
from custom_components.klereo.coordinator import KlereoCoordinator
from custom_components.klereo.models import (
    KlereoOutput,
    KlereoPoolDetails,
    KlereoSystemData,
    KlereoSystemInfo,
)
from custom_components.klereo.number import KlereoPumpSpeedNumber, _extract_numbers
from custom_components.klereo.select import KlereoOutputModeSelect
from custom_components.klereo.switch import KlereoSwitch

SYS1 = "SYS1"


def _make_output(**kwargs) -> KlereoOutput:
    defaults = {"index": OUT_IDX_FILTRATION, "status": 0, "mode": OUT_MODE_MAN, "type": 0}
    defaults.update(kwargs)
    return KlereoOutput(**defaults)


class TestTheModelCarriesPumpMaxSpeed:
    """`PumpMaxSpeed` reaches the platforms through the typed model, never a raw dict."""

    def test_pump_max_speed_is_parsed(self):
        details = KlereoPoolDetails.from_dict({"outs": [], "PumpMaxSpeed": 5})
        assert details.pump_max_speed == 5

    def test_a_numeric_string_is_accepted(self):
        """Klereo has sent numbers as strings elsewhere in this payload (mode, status)."""
        details = KlereoPoolDetails.from_dict({"outs": [], "PumpMaxSpeed": "5"})
        assert details.pump_max_speed == 5

    def test_an_absent_field_stays_none_rather_than_zero(self):
        """🔴 `0` is not a reading — most installations have no analogue pump at all, and
        defaulting to `0` would be indistinguishable from a fixed-speed pump reporting one."""
        details = KlereoPoolDetails.from_dict({"outs": []})
        assert details.pump_max_speed is None

    def test_a_boolean_is_rejected(self):
        """`bool` is an `int` subclass in Python; True/False must not silently read as 1/0."""
        details = KlereoPoolDetails.from_dict({"outs": [], "PumpMaxSpeed": True})
        assert details.pump_max_speed is None

    def test_an_unparseable_value_is_dropped(self):
        details = KlereoPoolDetails.from_dict({"outs": [], "PumpMaxSpeed": "not-a-number"})
        assert details.pump_max_speed is None


class TestTheModelCarriesRealStatus:
    """`realStatus` reaches the platforms through the typed model — see
    `models.KlereoOutput.real_status` for why it is now parsed (the `off_delay` exception:
    a FEATURE reads it, `number.KlereoPumpSpeedNumber` under Regulation)."""

    def test_real_status_is_parsed(self):
        output = KlereoOutput.from_dict({"index": 1, "status": 1, "realStatus": 2})
        assert output.real_status == 2

    def test_an_absent_real_status_stays_none_rather_than_zero(self):
        """🔴 `0` would be indistinguishable from a genuinely stopped pump — the same
        reasoning `off_delay` already uses, applied to this field."""
        output = KlereoOutput.from_dict({"index": 1, "status": 1})
        assert output.real_status is None

    def test_real_status_zero_is_kept_as_a_real_reading(self):
        """Control: an EXPLICIT 0 is a value, only an ABSENT key is unknown."""
        output = KlereoOutput.from_dict({"index": 1, "status": 1, "realStatus": 0})
        assert output.real_status == 0


class TestWhichInstallationsGetTheEntity:
    """🔴 Only an installation whose payload says "analogue pump" gets a speed entity.

    No entity pinned at 0, no fallback: a value we cannot read never invents one — the same
    rule `KlereoAutoOffNumber` already follows for `offDelay` (#128/#135/#138).
    """

    def _details(self, pump_max_speed=None, outs=(OUT_IDX_FILTRATION,)):
        outputs = [_make_output(index=i) for i in outs]
        return KlereoPoolDetails(
            outs=outputs,
            output_index={o.index: o for o in outputs},
            pump_max_speed=pump_max_speed,
        )

    def _uids(self, coordinator, details):
        return [uid for uid, _ in _extract_numbers(coordinator, SYS1, details)]

    def test_created_when_pump_max_speed_is_above_one(self, mock_coordinator):
        details = self._details(pump_max_speed=5)
        assert "SYS1_pump_speed_1" in self._uids(mock_coordinator, details)

    def test_not_created_when_pump_max_speed_is_absent(self, mock_coordinator):
        details = self._details(pump_max_speed=None)
        assert "SYS1_pump_speed_1" not in self._uids(mock_coordinator, details)

    def test_not_created_when_pump_max_speed_is_one(self, mock_coordinator):
        """A fixed-speed pump: `switch.KlereoSwitch`'s plain ON/OFF already covers it."""
        details = self._details(pump_max_speed=1)
        assert "SYS1_pump_speed_1" not in self._uids(mock_coordinator, details)

    def test_not_created_when_pump_max_speed_is_zero(self, mock_coordinator):
        details = self._details(pump_max_speed=0)
        assert "SYS1_pump_speed_1" not in self._uids(mock_coordinator, details)

    def test_not_created_when_there_is_no_filtration_output(self, mock_coordinator):
        """The field says the box has an analogue pump; the payload must still name output 1."""
        details = self._details(pump_max_speed=5, outs=(0, 9))
        assert "SYS1_pump_speed_1" not in self._uids(mock_coordinator, details)

    def test_the_bound_matches_pump_max_speed(self, mock_coordinator):
        details = self._details(pump_max_speed=7)
        (_, entity), = [
            (uid, e) for uid, e in _extract_numbers(mock_coordinator, SYS1, details)
            if uid == "SYS1_pump_speed_1"
        ]
        assert entity._attr_native_max_value == 7


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator, matching test_number.py's fixture shape."""
    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.async_set_output = AsyncMock()
    coordinator.data = {
        SYS1: KlereoSystemData(
            info=KlereoSystemInfo(id_system=SYS1, pool_nickname="My Pool"),
            details=KlereoPoolDetails(outs=[], output_index={}),
        )
    }
    return coordinator


class TestTheSpeedEntity:
    """Unit tests for KlereoPumpSpeedNumber."""

    def _put(self, mock_coordinator, output: KlereoOutput):
        details = mock_coordinator.data[SYS1].details
        details.outs = [output]
        details.output_index = {output.index: output}
        return mock_coordinator

    def test_name_and_unique_id(self, mock_coordinator):
        number = KlereoPumpSpeedNumber(mock_coordinator, SYS1, _make_output(), 5)
        assert number._attr_name == "Filtration Speed"
        assert number._attr_unique_id == "SYS1_pump_speed_1"

    def test_bounds_come_from_pump_max_speed(self, mock_coordinator):
        number = KlereoPumpSpeedNumber(mock_coordinator, SYS1, _make_output(), 7)
        assert number._attr_native_min_value == 0
        assert number._attr_native_max_value == 7
        assert number._attr_native_step == 1

    def test_current_value_under_manual(self, mock_coordinator):
        output = _make_output(status=3, mode=OUT_MODE_MAN)
        number = KlereoPumpSpeedNumber(mock_coordinator, SYS1, output, 5)
        assert number._attr_native_value == 3

    def test_current_value_under_regulation_reads_real_status(self, mock_coordinator):
        """🔴 MEASURED: under Regulation, `real_status` is the reliable reading, not
        `status` — see `models.KlereoOutput.real_status` for the citation."""
        output = _make_output(status=1, real_status=2, mode=OUT_MODE_REGUL)
        number = KlereoPumpSpeedNumber(mock_coordinator, SYS1, output, 5)
        assert number._attr_native_value == 2

    def test_current_value_is_none_under_regulation_without_real_status(self, mock_coordinator):
        """An installation that sends no `realStatus` reports nothing — never falls back
        to `status`, and never invents `0` (see the model's own docstring)."""
        output = _make_output(status=1, real_status=None, mode=OUT_MODE_REGUL)
        number = KlereoPumpSpeedNumber(mock_coordinator, SYS1, output, 5)
        assert number._attr_native_value is None

    def test_current_value_is_none_under_an_unmeasured_mode(self, mock_coordinator):
        """Scope control: Time Slots is a different non-Manual mode nobody has measured —
        widening every non-Manual mode to read a field would repeat exactly the mistake
        the Regulation fix above corrects for."""
        output = _make_output(status=1, real_status=2, mode=4)  # OUT_MODE_FILTRATION_SYNC
        number = KlereoPumpSpeedNumber(mock_coordinator, SYS1, output, 5)
        assert number._attr_native_value is None

    def test_current_value_is_none_for_an_unreadable_status(self, mock_coordinator):
        output = _make_output(status="banana", mode=OUT_MODE_MAN)
        number = KlereoPumpSpeedNumber(mock_coordinator, SYS1, output, 5)
        assert number._attr_native_value is None

    def test_current_value_is_none_for_an_unreadable_real_status(self, mock_coordinator):
        output = _make_output(status=1, real_status="banana", mode=OUT_MODE_REGUL)
        number = KlereoPumpSpeedNumber(mock_coordinator, SYS1, output, 5)
        assert number._attr_native_value is None

    async def test_setting_a_speed_sends_manual_mode(self, mock_coordinator):
        output = _make_output(status=0, mode=OUT_MODE_MAN)
        number = KlereoPumpSpeedNumber(mock_coordinator, SYS1, output, 5)
        number.async_write_ha_state = MagicMock()
        await number.async_set_native_value(3.0)
        mock_coordinator.async_set_output.assert_called_once_with(SYS1, OUT_IDX_FILTRATION, OUT_MODE_MAN, 3)
        assert number._attr_native_value == 3

    async def test_the_written_speed_is_an_integer_on_the_wire(self, mock_coordinator):
        """Home Assistant hands `async_set_native_value` a float; `newState` is an int field."""
        output = _make_output(status=0, mode=OUT_MODE_MAN)
        number = KlereoPumpSpeedNumber(mock_coordinator, SYS1, output, 5)
        number.async_write_ha_state = MagicMock()
        await number.async_set_native_value(3.0)
        (_, _, _, sent), _ = mock_coordinator.async_set_output.call_args
        assert isinstance(sent, int)

    async def test_setting_off_sends_zero(self, mock_coordinator):
        output = _make_output(status=3, mode=OUT_MODE_MAN)
        number = KlereoPumpSpeedNumber(mock_coordinator, SYS1, output, 5)
        number.async_write_ha_state = MagicMock()
        await number.async_set_native_value(0.0)
        mock_coordinator.async_set_output.assert_called_once_with(
            SYS1, OUT_IDX_FILTRATION, OUT_MODE_MAN, OUT_STATE_OFF
        )

    def test_available_while_the_payload_carries_the_output(self, mock_coordinator):
        coordinator = self._put(mock_coordinator, _make_output())
        number = KlereoPumpSpeedNumber(coordinator, SYS1, _make_output(), 5)
        assert number.available is True

    def test_unavailable_when_the_output_disappears(self, mock_coordinator):
        coordinator = self._put(mock_coordinator, _make_output())
        number = KlereoPumpSpeedNumber(coordinator, SYS1, _make_output(), 5)
        coordinator.data[SYS1].details.output_index.clear()
        assert number.available is False


def _out(index, status, mode, type_=0, real_status=None):
    out = {"index": index, "status": status, "mode": mode, "type": type_}
    if real_status is not None:
        out["realStatus"] = real_status
    return out


@pytest.fixture
def payloads():
    """Output 0 is an ordinary light, output 1 the analogue Filtration pump."""
    return {
        SYS1: {
            "probes": [],
            "outs": [
                _out(0, OUT_STATE_OFF, OUT_MODE_MAN),
                _out(OUT_IDX_FILTRATION, OUT_STATE_OFF, OUT_MODE_MAN),
            ],
            "PumpMaxSpeed": 5,
        },
    }


@pytest.fixture
def coordinator(payloads, monkeypatch):
    """A real coordinator over a mocked API — same shape as test_optimistic_siblings.py."""
    monkeypatch.setattr("custom_components.klereo.coordinator.asyncio.sleep", AsyncMock())

    api = AsyncMock(spec=KlereoApi)
    api.get_systems.return_value = {"response": [{"idSystem": SYS1}]}
    api.get_pool_details.side_effect = lambda sid: {"response": [payloads[sid]]}
    api.set_output.return_value = {"status": "ok", "response": {"cmdID": 77}}
    api.command_status.return_value = {
        "status": "ok", "response": {"cmdID": 77, "status": 9, "detail": "Ok"}
    }

    coord = KlereoCoordinator.__new__(KlereoCoordinator)
    coord.api = api
    coord.hass = MagicMock()
    coord.logger = MagicMock()
    coord.name = "klereo"
    coord.update_interval = None
    coord._listeners = {}
    coord._last_listener_id = 0
    coord.data = {}
    coord.last_update_success = True
    coord.async_request_refresh = AsyncMock()
    return coord


async def _refresh(coordinator):
    coordinator.data = await coordinator._async_update_data()
    coordinator.async_update_listeners()


def _bind(coordinator, entity):
    entity.async_write_ha_state = MagicMock()
    coordinator.async_add_listener(entity._handle_coordinator_update)
    return entity


def _switch(coordinator, index=OUT_IDX_FILTRATION):
    output = coordinator.data[SYS1].details.output_index[index]
    return _bind(coordinator, KlereoSwitch(coordinator, SYS1, output))


def _speed(coordinator):
    details = coordinator.data[SYS1].details
    output = details.output_index[OUT_IDX_FILTRATION]
    return _bind(coordinator, KlereoPumpSpeedNumber(coordinator, SYS1, output, details.pump_max_speed))


def _mode(coordinator, index=OUT_IDX_FILTRATION):
    output = coordinator.data[SYS1].details.output_index[index]
    return _bind(coordinator, KlereoOutputModeSelect(coordinator, SYS1, output))


class TestTheSwitchDoesNotFollowSpeedUnderManual:
    """🔴 Reverted on request: the switch does NOT track an analogue pump's speed.

    An earlier draft made `switch.KlereoSwitch` read any non-zero Manual status as "on",
    to follow the speed entity. Reverted: under Manual, the switch stays exactly what it
    was before this feature existed — plain `status == OUT_STATE_ON` (1) — and the speed
    entity is where a speed step actually shows. Only Regulation is special-cased
    (`TestTheSwitchFollowsRegulation` below), because that one is measured to need it.
    """

    async def test_setting_speed_2_does_not_turn_the_switch_on(self, coordinator):
        await _refresh(coordinator)
        switch = _switch(coordinator)
        speed = _speed(coordinator)
        assert switch.is_on is False

        await speed.async_set_native_value(2.0)

        assert switch.is_on is False
        assert speed.native_value == 2

    async def test_setting_plain_on_still_turns_the_switch_on(self, coordinator):
        """Positive control: speed step 1 happens to equal OUT_STATE_ON, so it still shows on."""
        await _refresh(coordinator)
        switch = _switch(coordinator)
        speed = _speed(coordinator)

        await speed.async_set_native_value(1.0)

        assert switch.is_on is True
        assert speed.native_value == 1

    async def test_commanding_the_pump_leaves_its_neighbour_alone(self, coordinator):
        """No lateral spill: output 0 is a plain light and must stay untouched."""
        await _refresh(coordinator)
        neighbour = _switch(coordinator, index=0)
        speed = _speed(coordinator)

        await speed.async_set_native_value(2.0)

        assert neighbour.is_on is False


class TestTheSwitchFollowsRegulation:
    """The Regulation approximation (`TestKlereoFiltrationSwitchUnderRegulation`,
    test_switch.py) exercised end-to-end through the coordinator, alongside the speed
    entity and the Output Mode select."""

    async def test_regulation_turns_the_switch_on_regardless_of_status(self, coordinator):
        await _refresh(coordinator)
        switch = _switch(coordinator)
        mode = _mode(coordinator)
        assert switch.is_on is False

        await mode.async_select_option("Regulation")

        assert switch.is_on is True


class TestModeSelectRoundTripPreservesSpeed:
    """Leaving and returning to Manual through the OTHER select must not reset the speed."""

    async def test_regulation_then_manual_keeps_the_last_speed(self, coordinator):
        await _refresh(coordinator)
        speed = _speed(coordinator)
        mode = _mode(coordinator)
        switch = _switch(coordinator)
        await speed.async_set_native_value(2.0)
        # The switch does not reflect a speed step under Manual (see the class above) —
        # only the speed entity does. That is unaffected by this round trip either way.
        assert speed.native_value == 2

        # Regulation reads as on regardless of status (measured, see test_switch.py).
        await mode.async_select_option("Regulation")
        assert switch.is_on is True
        # The speed itself is not reported here (`native_value` is None under
        # Regulation, asserted in `TestAutoIsStillNotAPumpSpeed` below) — what THIS
        # test holds is that it comes back once Manual owns the output again.

        await mode.async_select_option("Manual")

        assert speed.native_value == 2


class TestAutoIsStillNotAPumpSpeed:
    """Scope control: status 2 under a non-Manual mode is AUTO, never a speed step.

    Without this, widening the Filtration branch to any non-zero status would repeat the
    exact defect `coordinator._show_confirmed_output` already refuses for every other
    output — turning the commanded AUTO into an invented, specific relay reading.
    """

    async def test_regulation_does_not_invent_a_relay_status(self, coordinator):
        """Sending AUTO for Regulation must not overwrite the pump's last known status.

        Speed step 3 (a value we actually commanded under Manual) must not be clobbered by
        AUTO (2) just because Regulation always sends AUTO — the same rule
        `_show_confirmed_output` already holds for every other output, exercised here
        where the two numbers could plausibly be confused with each other.
        """
        await _refresh(coordinator)
        speed = _speed(coordinator)
        mode = _mode(coordinator)
        await speed.async_set_native_value(3.0)

        await mode.async_select_option("Regulation")

        assert mode.current_option == "Regulation"
        # None here because this mocked payload carries no `realStatus` at all — not
        # because Regulation is categorically hidden any more. See
        # `TestRegulationReadsRealStatus` below for the case where the payload does
        # carry it.
        assert speed.native_value is None
        stored = coordinator.data[SYS1].details.output_index[OUT_IDX_FILTRATION]
        assert (stored.mode, stored.status) == (OUT_MODE_REGUL, 3)


class TestRegulationReadsRealStatus:
    """End-to-end: a payload that DOES carry `realStatus` under Regulation.

    🔴 MEASURED, not assumed — see `models.KlereoOutput.real_status` for the citation.
    """

    async def test_a_refresh_under_regulation_reports_real_status_as_the_speed(
        self, coordinator, payloads
    ):
        payloads[SYS1]["outs"][1] = _out(
            OUT_IDX_FILTRATION, status=1, mode=OUT_MODE_REGUL, real_status=2
        )

        await _refresh(coordinator)
        speed = _speed(coordinator)

        assert speed.native_value == 2

    async def test_a_later_refresh_updates_the_reported_speed(self, coordinator, payloads):
        """The reading tracks the LATEST payload, not the one the entity was created from."""
        payloads[SYS1]["outs"][1] = _out(
            OUT_IDX_FILTRATION, status=1, mode=OUT_MODE_REGUL, real_status=1
        )
        await _refresh(coordinator)
        speed = _speed(coordinator)
        assert speed.native_value == 1

        payloads[SYS1]["outs"][1] = _out(
            OUT_IDX_FILTRATION, status=1, mode=OUT_MODE_REGUL, real_status=2
        )
        await _refresh(coordinator)

        assert speed.native_value == 2
