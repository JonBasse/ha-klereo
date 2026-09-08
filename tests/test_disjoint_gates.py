"""The `number` setpoint gate and the `climate` creation gate are DISJOINT — on purpose.

Forgejo #172. This file asserts no new behaviour: it fixes in place a divergence the
repository already has, and that reads like a defect until you follow the two write paths.

| entity                  | endpoint       | payload                         | gate                          |
|-------------------------|----------------|---------------------------------|-------------------------------|
| `number` water setpoint | `SetParam.php` | `poolID`, `paramID`, `newValue` | `is_setpoint_offered`         |
| `climate` heat mode     | `SetOut.php`   | `poolID`, **`outIdx: 4`**, …    | output 4 is in `output_index` |

A setpoint is a parameter OF THE POOL — output 4 appears nowhere in `number.py` →
`coordinator.async_set_param` → `api.set_param`. A heat mode is a property of one output.
Each gate is correct for what its entity writes, and nothing requires them to agree.

🔴 The measured case is the maintainer's own bench: `outs` = 0, 1, 2, 3, 9 — no output 4 —
`HeaterMode: 1`, `access: 10`, `EauMin: 0`, `EauMax: 40`. It carries a writable water
setpoint and no thermostat, and that is what the box describes.

Both "fixes" for the apparent disagreement destroy something, which is why this file exists
instead of one:

- barring `number` on output 4 DELETES a real setpoint from an install that has one — the
  shape of #128 / #135;
- creating `climate` without output 4 INVENTS a thermostat whose mode control writes to an
  output that is not there.

⚠️ Whoever comes to "align" the two gates: the tests below are the reason not to. Neither
direction can be applied without turning at least one of them red — and measured, not
asserted. The blunt alignments are already caught by accident elsewhere (17 and 8 cases),
because unrelated fixtures happen to carry no outputs or no `HeaterMode`. The two written
the way this codebase actually reasons are caught HERE AND NOWHERE ELSE: barring the
setpoint only where the payload does report its outputs — honouring "an unknown answer
never gates" — reddens two cases, both below; widening `climate` to a known `HeaterMode`
with no output 4 reddens exactly one, likewise below. Both would otherwise have shipped.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.klereo.api import OUT_IDX_HEATING, OUT_STATE_AUTO
from custom_components.klereo.climate import _extract_climate
from custom_components.klereo.models import (
    KlereoOutput,
    KlereoPoolDetails,
    KlereoSystemData,
    KlereoSystemInfo,
)
from custom_components.klereo.number import _extract_numbers

# What the bench reports, minus the output that is not there.
BIOUL_OUTPUTS = (0, 1, 2, 3, 9)
BIOUL_PARAMS = {"HeaterMode": 1, "EauMin": 0, "EauMax": 40}


def _details(out_indexes, **params) -> KlereoPoolDetails:
    outs = [
        KlereoOutput(index=i, status=OUT_STATE_AUTO, mode=0, type=0)
        for i in out_indexes
    ]
    return KlereoPoolDetails(
        probes=[],
        outs=outs,
        params={**BIOUL_PARAMS, **params},
        probe_index={},
        output_index={o.index: o for o in outs},
        access=10,
    )


@pytest.fixture
def coordinator():
    c = MagicMock()
    c.last_update_success = True
    c.async_set_param = AsyncMock()
    c.async_set_output = AsyncMock()
    c.data = {"SYS1": KlereoSystemData(
        info=KlereoSystemInfo(id_system="SYS1", pool_nickname="My Pool"),
        details=_details(BIOUL_OUTPUTS, ConsigneEau=28),
    )}
    return c


def _setpoint_keys(coordinator, details):
    coordinator.data["SYS1"].details = details
    return [entity._key for _uid, entity in _extract_numbers(coordinator, "SYS1", details)]


def _climate_uids(coordinator, details):
    coordinator.data["SYS1"].details = details
    return [uid for uid, _entity in _extract_climate(coordinator, "SYS1", details)]


class TestNoOutputFourStillMeansAWritableSetpoint:
    """The `number` gate does not — and must not — look at the outputs at all."""

    @pytest.mark.parametrize("stored", [28, -2000])
    def test_a_box_with_no_output_4_offers_the_water_setpoint(self, coordinator, stored):
        """🔴 Barring this on output 4 would delete a setpoint the box really has.

        Both stored values are exercised because neither is a permission: `-2000` is the
        sentinel #170 measured the box accepting a write over, and the entity exists in
        either case — reading `unknown` for one of them.
        """
        details = _details(BIOUL_OUTPUTS, ConsigneEau=stored)
        assert "ConsigneEau" in _setpoint_keys(coordinator, details)

    def test_the_same_payload_yields_no_thermostat(self, coordinator):
        """The other half of the same payload — one box, two answers, both right."""
        details = _details(BIOUL_OUTPUTS, ConsigneEau=28)
        assert _climate_uids(coordinator, details) == []

    def test_adding_output_4_changes_the_thermostat_and_nothing_else(self, coordinator):
        """The gates move independently: output 4 creates `climate`, `number` is unmoved.

        Asserted on the SAME settings, so the only difference between this payload and the
        one above is the output — which is exactly the input `number` must ignore.
        """
        details = _details((*BIOUL_OUTPUTS, OUT_IDX_HEATING), ConsigneEau=28)
        assert _climate_uids(coordinator, details) == ["SYS1_climate"]
        assert "ConsigneEau" in _setpoint_keys(coordinator, details)


class TestAHeatPumpWithNoOfferedSetpointStillGetsAThermostat:
    """And symmetrically: the `climate` gate does not look at the setpoint.

    `HeaterMode` 0 and 3 carry no setpoint (`HEATER_MODES_WITHOUT_SETPOINT`), so
    `is_setpoint_offered` says no — while output 4 is right there. A thermostat is a
    COMPOSITE object: `climate.async_set_hvac_mode` writes the output, and
    `climate.async_set_temperature` is the one guarded by `is_setpoint_offered`. Gating
    the entity's existence on the setpoint would remove working mode control.
    """

    @pytest.mark.parametrize("heater_mode", [0, 3])
    def test_output_4_creates_the_thermostat_whatever_the_setpoint_gate_says(
        self, coordinator, heater_mode
    ):
        details = _details((*BIOUL_OUTPUTS, OUT_IDX_HEATING), ConsigneEau=28,
                           HeaterMode=heater_mode)
        assert "ConsigneEau" not in _setpoint_keys(coordinator, details)
        assert _climate_uids(coordinator, details) == ["SYS1_climate"]
