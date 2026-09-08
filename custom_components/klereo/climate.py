"""Climate platform for Klereo.

One entity per installation that has a heat pump, aggregating four things this integration
already exposed separately: the water probe, the `ConsigneEau` setpoint, the KlereoTherm
mode and the on/off write. Requested in GitHub #59, tracked as Forgejo #118.

The existing `switch`, `select` and `number` entities are deliberately left alone — they
are what people have already wired into their automations. This one is added beside them.
"""
import logging

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import (
    HEAT_MODE_AUTO,
    HEAT_MODE_COOLING,
    HEAT_MODE_HEATING,
    HEAT_MODE_STOP,
    OUT_IDX_HEATING,
    state_for_heat_mode,
)
from .const import PARAM_SENTINELS, PARAM_TYPES, WATER_TEMPERATURE_PROBE_TYPE
from .entity import (
    KlereoEntity,
    is_output_offered,
    is_setpoint_offered,
    offered_heat_modes,
    setup_discovery,
)
from .models import KlereoPoolDetails

_LOGGER = logging.getLogger(__name__)

# The four KlereoTherm modes map one for one onto Home Assistant's. This is a rename, not
# an adaptation — which is what made #118 worth doing at all.
HVAC_BY_HEAT_MODE = {
    HEAT_MODE_STOP: HVACMode.OFF,
    HEAT_MODE_AUTO: HVACMode.AUTO,
    HEAT_MODE_COOLING: HVACMode.COOL,
    HEAT_MODE_HEATING: HVACMode.HEAT,
}
HEAT_MODE_BY_HVAC = {v: k for k, v in HVAC_BY_HEAT_MODE.items()}

_SETPOINT = "ConsigneEau"


def _extract_climate(coordinator, system_id, details: KlereoPoolDetails):
    """Create the thermostat, but only where there is a heat pump to drive.

    🔴 Gated on output 4 actually being reported. The one installation this repository has
    direct access to carries `outs` = 0, 1, 2, 3, 9 — no heating output at all — and a
    thermostat there would be inert in the exact way #124 describes: it would accept every
    command and change nothing.

    🔴 DISJOINT from `is_setpoint_offered` BY CONSTRUCTION — do not "align" the two
    (Forgejo #172). This gate asks about an OUTPUT because `async_set_hvac_mode` writes
    `SetOut.php` with `outIdx: 4`; the setpoint gate asks about a POOL PARAMETER because
    `async_set_temperature` — and `number` — write `SetParam.php`, which carries no output
    index at all. That is why this class calls both, separately, a few dozen lines below.
    Widening this one to "a setpoint is offered" would INVENT a thermostat whose mode
    control writes to an output the box does not report. `tests/test_disjoint_gates.py`
    turns red on either alignment.
    """
    if OUT_IDX_HEATING not in details.output_index:
        _LOGGER.debug("No heating output on system %s: no climate entity", system_id)
        return []
    if not is_output_offered(OUT_IDX_HEATING, details):
        return []
    return [(f"{system_id}_climate", KlereoClimate(coordinator, system_id))]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Klereo climate entity."""
    setup_discovery(hass, entry, async_add_entities, _extract_climate)


class KlereoClimate(KlereoEntity, ClimateEntity):
    """The KlereoTherm heat pump as a thermostat."""

    _attr_name = "Heating"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5

    def __init__(self, coordinator, system_id):
        """Initialize the thermostat."""
        super().__init__(coordinator, system_id)
        self._attr_unique_id = f"{system_id}_climate"

    @property
    def available(self) -> bool:
        """Return whether the payload still reports the heat pump this drives.

        🔴 A PROPERTY, not `self._attr_available = ...` in the update callback.
        `CoordinatorEntity.available` is itself a property returning
        `coordinator.last_update_success`, so it shadows `_attr_available` entirely and
        assigning to that attribute changes nothing an entity ever reports. Measured
        2026-08-26, when this was the only platform doing it correctly; the other five
        assigned the attribute and their entities never went unavailable. Fixed for all
        of them in #130, which also moved the shared half onto `KlereoEntity.available` —
        so `super()` here now checks the system before this checks the output.

        `super().available` is kept in the conjunction: a failed refresh still makes the
        entity unavailable, which is the half that does work today.
        """
        return super().available and self._output() is not None

    # ── reading ─────────────────────────────────────────────────────────────

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Advertise a target temperature where the box will ACCEPT one.

        🔴 This used to be derived from `target_temperature is not None`, which conflated
        two different questions — and measurement split them (Forgejo #170). The target is
        a READING, and a sentinel means there is nothing to read yet. The feature is a
        PERMISSION, and the box grants it: on 2026-09-07 it accepted `SetParam ConsigneEau`
        over a stored `-2000`, answered `status: 9`, and its own front panel went from
        `Arrêté` to `25.0 °C` (GitHub #55). Deriving one from the other left the reporter
        with a thermostat that could never be given a target, on a box that would have
        taken one — and, being unwritable, the value stayed `-2000` forever.

        `is_setpoint_offered` is the same judgement `number` makes, deliberately: the two
        must not disagree about whether this installation may write its water setpoint.
        It keeps the gates that ARE measured — access below end-customer, and a `HeaterMode`
        whose hardware carries no setpoint at all (#124).
        """
        features = ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        if self._setpoint_is_writable():
            features |= ClimateEntityFeature.TARGET_TEMPERATURE
        return features

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return the modes this installation's hardware can be set to.

        The table is `offered_heat_modes`, shared with the `select` entity. A thermostat
        offering `cool` on an on/off heater would be #124 again, more visible — and a
        second copy of that table is a drift waiting to happen.
        """
        details = self._details()
        if details is None:
            return list(HVAC_BY_HEAT_MODE.values())
        return [HVAC_BY_HEAT_MODE[mode] for mode in offered_heat_modes(details)]

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return what the box says it is doing, or None when there is no honest answer.

        Never `HVACMode.OFF` for a mode we cannot read: that would be a specific,
        plausible, wrong answer, indistinguishable from a heat pump genuinely stopped
        (#105). A mode outside `hvac_modes` is still reported — offering is narrowed,
        reading is not (#124), and such a report is the only signal that our gate is
        mis-typed for this installation.
        """
        output = self._output()
        if output is None:
            return None
        try:
            code = int(output.mode)
        except (TypeError, ValueError):
            return None
        mode = HVAC_BY_HEAT_MODE.get(code)
        if mode is None:
            _LOGGER.debug("Heating output reports mode %s, which Klereo does not document", code)
        return mode

    @property
    def current_temperature(self) -> float | None:
        """Return the water temperature Klereo regulates on.

        `EauCapteur` names that probe (#107) — a pool can carry two probes reading °C, and
        picking one by position would be a guess when the box already answers. Falling
        back to a water probe when it names none, or names one this payload does not
        carry: a reference we cannot resolve must not blank a reading we do have.
        """
        details = self._details()
        if details is None:
            return None
        index = details.regulation_probes.get("water_temperature")
        probe = details.probe_index.get(index) if index is not None else None
        if probe is None:
            probe = next(
                (p for p in details.probes if p.type == WATER_TEMPERATURE_PROBE_TYPE), None
            )
        if probe is None:
            return None
        return probe.filtered_value if probe.filtered_value is not None else probe.direct_value

    @property
    def target_temperature(self) -> float | None:
        """Return `ConsigneEau`, unless it carries a sentinel."""
        value = self._settings().get(_SETPOINT)
        if value is None or value in PARAM_SENTINELS:
            return None
        return value

    @property
    def min_temp(self) -> float:
        """Return the API's own lower bound, falling back to the documented default."""
        return self._settings().get("EauMin", PARAM_TYPES[_SETPOINT]["min"])

    @property
    def max_temp(self) -> float:
        """Return the API's own upper bound, falling back to the documented default."""
        return self._settings().get("EauMax", PARAM_TYPES[_SETPOINT]["max"])

    # ── writing ─────────────────────────────────────────────────────────────

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the KlereoTherm mode.

        The `newState` that goes with each mode is `state_for_heat_mode`, shared with the
        `switch` and the `select` — measured on the official client rather than inferred
        (Forgejo #166). It is deliberately not a property of "above Off": Heating sends ON
        and Auto sends AUTO, and both are above Off.
        """
        mode = HEAT_MODE_BY_HVAC[hvac_mode]
        state = state_for_heat_mode(mode)
        await self.coordinator.async_set_output(
            self.system_id, OUT_IDX_HEATING, mode, state
        )

    async def async_turn_on(self) -> None:
        """Turn the heat pump on — as Heating, never Auto.

        🔴 The 1.5.3 fix, carried over rather than re-decided. Turning the heating on used
        to send heat mode 0 (Off) to the heat pump, so it turned OFF (Forgejo #55 / GitHub
        #58). Heating is right for every heating type, including the ones #124 shows
        cannot do Auto at all.
        """
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        """Turn the heat pump off."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_temperature(self, **kwargs) -> None:
        """Write `ConsigneEau`.

        🔴 The refusal here used to fire on a sentinel, and its stated reason — "the write
        would be discarded by the box" — is REFUTED by measurement (Forgejo #170). It was
        carried over from #124 by analogy: there, an on/off heater accepts `Cooling`,
        answers status 9 and does nothing. A disabled setpoint is not that case, and this
        refusal is what kept GitHub #55 stuck.

        A service call can still reach an entity that does not advertise the feature, so
        the guard stays — on the question that is actually measured: may this installation
        write this setpoint at all.
        """
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        if not self._setpoint_is_writable():
            _LOGGER.warning(
                "Refusing to write %s: this installation cannot be offered it", _SETPOINT
            )
            return
        await self.coordinator.async_set_param(self.system_id, _SETPOINT, temperature)

    # ── helpers ─────────────────────────────────────────────────────────────

    def _details(self) -> KlereoPoolDetails | None:
        system = self.coordinator.data.get(self.system_id)
        return system.details if system else None

    def _settings(self) -> dict:
        details = self._details()
        return details.settings if details else {}

    def _setpoint_is_writable(self) -> bool:
        """Return whether this installation may be offered a water setpoint.

        ⚠️ An unreadable payload NEVER gates — same rule as everywhere else in this
        integration. A refresh that failed must not silently remove the dial from a
        thermostat that has one.
        """
        details = self._details()
        if details is None:
            return True
        return is_setpoint_offered(_SETPOINT, details)

    def _output(self):
        details = self._details()
        return details.output_index.get(OUT_IDX_HEATING) if details else None
