"""Tests for the Klereo climate entity.

Requested in GitHub #59 by the reporter of GH #55, tracked as Forgejo #118. The entity
aggregates four things the integration already exposes separately — the water probe, the
`ConsigneEau` setpoint, the KlereoTherm mode and the on/off write — and Home Assistant's
`climate` platform exists for exactly that.

🔴 What this bench CANNOT verify, said before measuring rather than after: the one
installation this repository has direct access to has **no output 4 at all** (`outs` =
0, 1, 2, 3, 9). It therefore cannot exercise a heat-pump entity end to end. Every test
here builds its payload from what reporters measured; none of them proves that a command
reaches a real heat pump. GH #55 is still open on precisely that.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.climate import ClimateEntityFeature, HVACMode

from custom_components.klereo.api import (
    HEAT_MODE_AUTO,
    HEAT_MODE_COOLING,
    HEAT_MODE_HEATING,
    HEAT_MODE_STOP,
    OUT_IDX_HEATING,
    OUT_STATE_AUTO,
    OUT_STATE_OFF,
)
from custom_components.klereo.climate import _extract_climate
from custom_components.klereo.models import (
    KlereoOutput,
    KlereoPoolDetails,
    KlereoProbe,
    KlereoSystemData,
    KlereoSystemInfo,
)


def _probe(**kwargs) -> KlereoProbe:
    defaults = {"index": 16, "type": 5, "filtered_value": 27.0, "direct_value": 27.0, "status": 0}
    defaults.update(kwargs)
    return KlereoProbe(**defaults)


def _output(**kwargs) -> KlereoOutput:
    defaults = {"index": OUT_IDX_HEATING, "status": OUT_STATE_AUTO, "mode": HEAT_MODE_HEATING,
                "type": 0}
    defaults.update(kwargs)
    return KlereoOutput(**defaults)


def _details(outs=None, probes=None, params=None, regulation_probes=None, **kw) -> KlereoPoolDetails:
    outs = [_output()] if outs is None else outs
    probes = [_probe()] if probes is None else probes
    return KlereoPoolDetails(
        probes=probes,
        outs=outs,
        params=params or {},
        probe_index={p.index: p for p in probes},
        output_index={o.index: o for o in outs},
        regulation_probes=regulation_probes or {},
        **kw,
    )


@pytest.fixture
def coordinator():
    c = MagicMock()
    # Explicit, not left as a MagicMock attribute: `CoordinatorEntity.available` returns
    # this value, and a truthy mock makes `available is True` pass for the wrong reason.
    c.last_update_success = True
    c.async_set_output = AsyncMock()
    c.async_set_param = AsyncMock()
    c.data = {"SYS1": KlereoSystemData(
        info=KlereoSystemInfo(id_system="SYS1", pool_nickname="My Pool"),
        details=_details(),
    )}
    return c


def _build(coordinator, **kw):
    """Install a payload and return the climate entity it produces, or None."""
    details = _details(**kw)
    coordinator.data["SYS1"].details = details
    items = _extract_climate(coordinator, "SYS1", details)
    return items[0][1] if items else None


class TestTheEntityExistsOnlyWhereTheHardwareDoes:
    """Output 4 is the heat pump. No output 4, no thermostat."""

    def test_an_installation_without_output_4_gets_no_entity(self, coordinator):
        """🔴 The measured local installation: `outs` = 0, 1, 2, 3, 9 and no heating.

        A thermostat on a pool with no heat pump would be inert in the exact way #124
        describes — it would accept commands and change nothing.
        """
        outs = [_output(index=i) for i in (0, 1, 2, 3, 9)]
        assert _build(coordinator, outs=outs) is None

    def test_an_installation_with_output_4_gets_one(self, coordinator):
        entity = _build(coordinator)
        assert entity is not None
        assert entity.unique_id == "SYS1_climate"

    def test_the_existing_entities_are_not_replaced(self, coordinator):
        """The switch, select and number stay — they are what people already wired.

        This platform only ever adds one entity, so discovering it cannot remove another.
        Asserted on the count so that adding a second climate entity has to be deliberate.
        """
        assert len(_extract_climate(coordinator, "SYS1", _details())) == 1


class TestHvacModesComeFromTheSharedTable:
    """The `hvac_modes` list IS #124's filter, not a second copy of it.

    The four KlereoTherm modes map one for one onto Home Assistant's: 0 Off, 1 Auto,
    2 Cooling, 3 Heating. A thermostat offering `cool` on an on/off heater would be #124
    again, more visible — so both entities read `offered_heat_modes`.
    """

    def test_a_real_heat_pump_offers_all_four(self, coordinator):
        entity = _build(coordinator, params={"HeaterMode": 2})
        assert entity.hvac_modes == [HVACMode.OFF, HVACMode.AUTO, HVACMode.COOL, HVACMode.HEAT]

    @pytest.mark.parametrize("heater_mode", [0, 1, 3])
    def test_a_heat_only_type_is_not_offered_cool(self, coordinator, heater_mode):
        """🔴 The #124 defect, in the form that would be far more visible."""
        entity = _build(coordinator, params={"HeaterMode": heater_mode})
        assert entity.hvac_modes == [HVACMode.OFF, HVACMode.HEAT]

    def test_an_unknown_heater_mode_never_bars(self, coordinator):
        """🔴 Same rule, same direction as #124: a missing reading removes nothing."""
        entity = _build(coordinator, params={})
        assert entity.hvac_modes == [HVACMode.OFF, HVACMode.AUTO, HVACMode.COOL, HVACMode.HEAT]

    def test_the_list_re_evaluates_on_a_later_payload(self, coordinator):
        entity = _build(coordinator, params={})
        entity.async_write_ha_state = MagicMock()
        assert HVACMode.COOL in entity.hvac_modes
        coordinator.data["SYS1"].details.params = {"HeaterMode": 1}
        entity._handle_coordinator_update()
        assert HVACMode.COOL not in entity.hvac_modes


class TestTheReportedMode:
    """What the box says it is doing right now."""

    @pytest.mark.parametrize("mode,expected", [
        (HEAT_MODE_STOP, HVACMode.OFF),
        (HEAT_MODE_AUTO, HVACMode.AUTO),
        (HEAT_MODE_COOLING, HVACMode.COOL),
        (HEAT_MODE_HEATING, HVACMode.HEAT),
    ])
    def test_each_klereotherm_mode_maps_to_its_hvac_mode(self, coordinator, mode, expected):
        assert _build(coordinator, outs=[_output(mode=mode)]).hvac_mode == expected

    def test_an_undocumented_mode_is_unknown_not_off(self, coordinator):
        """🔴 `None`, never `HVACMode.OFF`.

        Reporting a mode we cannot read as "off" would be a specific, plausible, wrong
        answer, indistinguishable from a heat pump genuinely stopped — the #105 failure.
        """
        assert _build(coordinator, outs=[_output(mode=7)]).hvac_mode is None

    def test_a_mode_outside_the_offered_list_is_still_reported(self, coordinator):
        """Offering is narrowed, reading is not — the #124 rule, carried over.

        A heat-only installation reporting Cooling is the only signal that our gate is
        mis-typed for it; hiding it would cost exactly that signal.
        """
        entity = _build(coordinator, outs=[_output(mode=HEAT_MODE_COOLING)],
                        params={"HeaterMode": 1})
        assert entity.hvac_mode == HVACMode.COOL
        assert HVACMode.COOL not in entity.hvac_modes


class TestCurrentTemperature:
    """Which probe the thermostat reads — the one Klereo regulates on."""

    def test_it_reads_the_probe_klereo_regulates_on(self, coordinator):
        """🔴 `EauCapteur` (#107), not merely the first probe that reports °C.

        A pool can carry two water-temperature probes; picking one by position would be a
        guess, and the box already answers the question.
        """
        probes = [_probe(index=16, filtered_value=22.0), _probe(index=20, filtered_value=28.3)]
        entity = _build(coordinator, probes=probes, regulation_probes={"water_temperature": 20})
        assert entity.current_temperature == 28.3

    def test_it_falls_back_to_a_water_probe_when_klereo_names_none(self, coordinator):
        """Not every installation sends `EauCapteur`; one water probe is unambiguous."""
        entity = _build(coordinator, probes=[_probe(index=16, filtered_value=27.0)])
        assert entity.current_temperature == 27.0

    def test_it_is_unknown_when_there_is_no_water_probe(self, coordinator):
        entity = _build(coordinator, probes=[_probe(index=1, type=1, filtered_value=23.7)])
        assert entity.current_temperature is None

    def test_a_named_probe_the_payload_lacks_falls_back(self, coordinator):
        """A reference naming an absent probe must not blank a reading we do have."""
        entity = _build(coordinator, probes=[_probe(index=16, filtered_value=27.0)],
                        regulation_probes={"water_temperature": 99})
        assert entity.current_temperature == 27.0


class TestTargetTemperature:
    """`ConsigneEau`, with the API's own bounds — and what happens when it is disabled."""

    def test_it_reads_the_setpoint_and_its_bounds(self, coordinator):
        entity = _build(coordinator, params={"ConsigneEau": 28, "EauMin": 15, "EauMax": 32})
        assert entity.target_temperature == 28
        assert entity.min_temp == 15
        assert entity.max_temp == 32
        assert entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE

    def test_a_disabled_setpoint_keeps_the_entity_and_drops_the_target(self, coordinator):
        """🔴 The measured case: `ConsigneEau: -2000` means the setpoint is disabled.

        Both installations this repository has read carry it. The thermostat still shows
        the water temperature and still switches the pump — it simply offers no target,
        rather than pinning one to -2000 °C or vanishing entirely.
        """
        entity = _build(coordinator, params={"ConsigneEau": -2000})
        assert entity.target_temperature is None
        assert not entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE
        assert entity.hvac_modes

    def test_an_unknown_setpoint_is_treated_the_same(self, coordinator):
        """`-1000` is Klereo's "unknown"; both sentinels are already known here."""
        entity = _build(coordinator, params={"ConsigneEau": -1000}).target_temperature
        assert entity is None

    def test_bounds_fall_back_when_the_payload_sends_none(self, coordinator):
        entity = _build(coordinator, params={"ConsigneEau": 28})
        assert entity.min_temp == 10
        assert entity.max_temp == 40


class TestWrites:
    """Every write goes through a coordinator method, never `coordinator.api`."""

    async def test_setting_heat_sends_the_mode_and_auto_state(self, coordinator):
        entity = _build(coordinator)
        entity.async_write_ha_state = MagicMock()
        await entity.async_set_hvac_mode(HVACMode.HEAT)
        coordinator.async_set_output.assert_called_once_with(
            "SYS1", OUT_IDX_HEATING, HEAT_MODE_HEATING, OUT_STATE_AUTO)

    async def test_setting_off_sends_the_off_state(self, coordinator):
        entity = _build(coordinator)
        entity.async_write_ha_state = MagicMock()
        await entity.async_set_hvac_mode(HVACMode.OFF)
        coordinator.async_set_output.assert_called_once_with(
            "SYS1", OUT_IDX_HEATING, HEAT_MODE_STOP, OUT_STATE_OFF)

    async def test_turn_on_sends_heating_not_auto(self, coordinator):
        """🔴 The 1.5.3 fix, carried over rather than re-decided.

        Turning the heating on used to send heat mode 0 — Off — to the heat pump
        (Forgejo #55 / GitHub #58). `Heating` is the answer that was measured, and it is
        right for every heating type, including the ones that cannot do Auto.
        """
        entity = _build(coordinator)
        entity.async_write_ha_state = MagicMock()
        await entity.async_turn_on()
        coordinator.async_set_output.assert_called_once_with(
            "SYS1", OUT_IDX_HEATING, HEAT_MODE_HEATING, OUT_STATE_AUTO)

    async def test_turn_off_sends_stop(self, coordinator):
        entity = _build(coordinator)
        entity.async_write_ha_state = MagicMock()
        await entity.async_turn_off()
        coordinator.async_set_output.assert_called_once_with(
            "SYS1", OUT_IDX_HEATING, HEAT_MODE_STOP, OUT_STATE_OFF)

    async def test_setting_a_temperature_writes_the_setpoint(self, coordinator):
        entity = _build(coordinator, params={"ConsigneEau": 28})
        entity.async_write_ha_state = MagicMock()
        await entity.async_set_temperature(temperature=29.5)
        coordinator.async_set_param.assert_called_once_with("SYS1", "ConsigneEau", 29.5)

    async def test_a_temperature_write_is_refused_when_the_setpoint_is_disabled(self, coordinator):
        """🔴 A service call can reach an entity that does not advertise the feature."""
        entity = _build(coordinator, params={"ConsigneEau": -2000})
        entity.async_write_ha_state = MagicMock()
        await entity.async_set_temperature(temperature=29.5)
        coordinator.async_set_param.assert_not_called()


class TestAvailability:
    """🔴 Asserted on `.available`, never on `_attr_available`.

    `CoordinatorEntity.available` is a property returning `last_update_success`, so it
    shadows `_attr_available` completely: an entity that assigns to that attribute reports
    the assignment to nobody. Measured 2026-08-26 — a probe removed from the payload
    leaves `_attr_available = False` and `.available = True` on this integration's other
    five platforms, whose tests assert the attribute they set rather than the behaviour.
    Asserting the attribute here would be a test that is green over an inert mechanism,
    which is the failure #115 already cost this repository once.
    """

    def test_it_goes_unavailable_when_the_output_disappears(self, coordinator):
        entity = _build(coordinator)
        coordinator.data["SYS1"].details.output_index = {}
        assert entity.available is False

    def test_it_is_available_while_the_output_is_reported(self, coordinator):
        """Positive control: without it, "unavailable" is compatible with always-off."""
        assert _build(coordinator).available is True

    def test_a_failed_refresh_still_makes_it_unavailable(self, coordinator):
        """The half of the mechanism that does work today must survive the override."""
        entity = _build(coordinator)
        coordinator.last_update_success = False
        assert entity.available is False
