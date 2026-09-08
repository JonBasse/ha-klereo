"""`switch` and `select` read `status`, not `realStatus` — and this file is the reason.

Forgejo #141. The two fields are now NAMED: `realStatus` is the physical state of the
relay, `status` is the state that was commanded. That is measured, in one payload —
@nopbop's diagnostics export of 2026-09-08, taken while his heat pump was heating. Wherever
the two disagree there, `realStatus` agrees with the run-time counter and `status` does not
(`models.KlereoOutput` carries the measurement).

🔴 Naming the fields is not permission to swap them, and the difference between the two is
exactly what this file holds. `KlereoOutput.from_dict` reads the payload with
`data.get(..., 0)`: an installation that never sends `realStatus` would read `0` there,
which is indistinguishable from a relay that is genuinely open. Swapping would turn OFF
every output of every such installation in order to fix the display of one — a correction
that makes false what was true. Two installations have been read, both carry the key, and
two are not all.

The tests below are written on BEHAVIOUR and go through the wire dict, because that is the
only formulation that catches the swap: an assertion on `KlereoOutput`'s field list is
already made in `tests/test_diagnostics.py`, and it would stay green for a parser that kept
the attribute named `status` while filling it from `realStatus`.

⚠️ The last test asserts the cost of the decision instead of hiding it: on @nopbop's output
4 the switch reports the command and not the world. That is the shape of GitHub #58, it is
known, and it is the price of not breaking every other installation.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.klereo.api import OUT_MODE_MAN, OUT_STATE_ON
from custom_components.klereo.models import (
    KlereoPoolDetails,
    KlereoSystemData,
    KlereoSystemInfo,
)
from custom_components.klereo.select import KlereoOutputModeSelect
from custom_components.klereo.switch import KlereoSwitch

# An `outs[]` element from an installation that does NOT report `realStatus`. The output is
# the filtration pump, really running: `status: 1` and a run-time counter of ~592 days that
# only a relay which actually closes can accumulate.
#
# 🔴 The absence of the key is the whole fixture. The tests assert it explicitly rather than
# trusting this comment, so that adding `realStatus` here cannot quietly make them vacuous.
WIRE_WITHOUT_REAL_STATUS = {
    "index": 1,
    "status": 1,
    "mode": OUT_MODE_MAN,
    "type": 0,
    "totalTime": 51162044,
}

# @nopbop's output 4, VERBATIM from the 2026-09-08 export: commanded on, physically open,
# and never counted a second. The divergence #141 was opened for.
NOPBOP_OUT_4 = {
    "index": 4,
    "status": 1,
    "realStatus": 0,
    "mode": 3,
    "type": 8,
    "map": 31,
    "totalTime": 0,
}


def _coordinator(*out_dicts) -> MagicMock:
    """Build a coordinator whose data comes from wire dicts, not from typed models.

    Parsing here rather than constructing `KlereoOutput` directly is deliberate: the swap
    this file refuses would happen in `from_dict`, so a test that skips it cannot see it.
    """
    details = KlereoPoolDetails.from_dict({"outs": list(out_dicts)})
    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.async_set_output = AsyncMock()
    coordinator.data = {
        "SYS1": KlereoSystemData(
            info=KlereoSystemInfo(id_system="SYS1", pool_nickname="My Pool"),
            details=details,
        )
    }
    return coordinator


class TestAnOutputThatIsReallyOnStaysOn:
    """The negative control #141 made mandatory before any change."""

    def test_the_switch_of_a_running_output_is_on_without_realStatus(self):
        """🔴 An installation that never sends the field keeps its outputs.

        Red the moment `switch` is fed from `realStatus` without handling the absence of
        the key — which is the only way anyone would write the swap.
        """
        assert "realStatus" not in WIRE_WITHOUT_REAL_STATUS

        coordinator = _coordinator(WIRE_WITHOUT_REAL_STATUS)
        output = coordinator.data["SYS1"].details.output_index[1]
        switch = KlereoSwitch(coordinator, "SYS1", output)

        assert switch.is_on is True

    def test_the_select_keeps_the_ON_state_of_a_running_output_without_realStatus(self):
        """Same installation, the other consumer named by the ticket.

        `select` re-sends the current ON/OFF state when it writes Manual mode. Read from an
        absent `realStatus`, that state would collapse to OFF and the mode change would
        STOP the pump — a write, not just a wrong display.
        """
        assert "realStatus" not in WIRE_WITHOUT_REAL_STATUS

        coordinator = _coordinator(WIRE_WITHOUT_REAL_STATUS)
        output = coordinator.data["SYS1"].details.output_index[1]
        select = KlereoOutputModeSelect(coordinator, "SYS1", output)

        assert select._state_for_mode(OUT_MODE_MAN) == OUT_STATE_ON


class TestTheKnownCostOfReadingStatus:
    """What the decision costs, asserted rather than left for the next bug report."""

    def test_a_commanded_output_with_an_open_relay_still_reads_on(self):
        """@nopbop's output 4: `status: 1`, `realStatus: 0`, `totalTime: 0`.

        The switch says on because the command says on. This is the GitHub #58 shape and it
        is NOT fixed here — it is priced. Whoever wants to fix it has to keep the test above
        green at the same time, which means handling an absent `realStatus` explicitly
        instead of defaulting it to `0`.
        """
        coordinator = _coordinator(NOPBOP_OUT_4)
        output = coordinator.data["SYS1"].details.output_index[4]
        switch = KlereoSwitch(coordinator, "SYS1", output)

        assert output.status == 1
        assert switch.is_on is True

    def test_the_physical_field_never_reaches_the_typed_model(self):
        """The parser drops it, so no platform can read it by accident.

        Paired with the behavioural tests rather than standing alone: on its own this is an
        assertion about a field list, and a parser filling `status` from `realStatus` would
        keep it green.
        """
        coordinator = _coordinator(NOPBOP_OUT_4)
        output = coordinator.data["SYS1"].details.output_index[4]

        assert not hasattr(output, "real_status")
        assert not hasattr(output, "realStatus")


@pytest.mark.parametrize(
    ("out_dict", "expected"),
    [
        (WIRE_WITHOUT_REAL_STATUS, True),
        (NOPBOP_OUT_4, True),
    ],
)
def test_both_measured_shapes_report_the_commanded_state(out_dict, expected):
    """One table for the two payload shapes this repository has actually seen.

    The point is that the answer is the SAME on both — the reading does not depend on
    whether the installation sends `realStatus`, which is what makes it safe to ship to
    installations nobody has measured.
    """
    coordinator = _coordinator(out_dict)
    output = coordinator.data["SYS1"].details.output_index[out_dict["index"]]
    switch = KlereoSwitch(coordinator, "SYS1", output)

    assert switch.is_on is expected
