"""Number platform for Klereo."""
import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import OUT_IDX_FILTRATION, OUT_MODE_MAN, OUT_MODE_REGUL
from .const import (
    AUTO_OFF_MAX_MINUTES,
    AUTO_OFF_MIN_MINUTES,
    OUTPUT_NAMES,
    PARAM_TYPES,
)
from .entity import KlereoEntity, is_setpoint_offered, setpoint_reading, setup_discovery
from .models import KlereoOutput, KlereoPoolDetails

_LOGGER = logging.getLogger(__name__)


def _extract_numbers(coordinator, system_id, details: KlereoPoolDetails):
    """Extract number entities from system details."""
    items = []
    settings = details.settings
    for key, value in settings.items():
        if key not in PARAM_TYPES:
            continue
        # The guard lives in `entity` because `sensor` needs the SAME answer: whatever it
        # refuses here keeps its read-only sensor there, instead of vanishing (#128).
        if not is_setpoint_offered(key, details):
            continue
        uid = f"{system_id}_number_{key}"
        items.append((uid, KlereoNumber(coordinator, system_id, key, value, settings)))
    for output in details.outs:
        # 🔴 Only an output that REPORTS a timer gets one. No entity pinned at 0, no
        # fallback: a value we cannot read never invents an entity (#128, #135, #138).
        # Bioul's five outputs all carry `offDelay`, but `plans` already does not cover
        # every output, so nothing here treats the field as universal.
        #
        # ⚠️ Deliberately NOT gated on `is_output_offered`. That gate exists because
        # `newMode` has no documented meaning on outputs 2, 3, 8 and 15 (`const.py`), and
        # `SetAutoOff` carries no `newMode` at all — it is a different endpoint with a
        # different payload. Nothing measured says this write needs professional access;
        # the one measurement there is says the opposite (`status: 9` at `access: 10`).
        # An unknown answer never gates, exactly as in `is_output_offered` itself.
        if output.off_delay is None:
            continue
        uid = f"{system_id}_auto_off_{output.index}"
        items.append((uid, KlereoAutoOffNumber(coordinator, system_id, output)))

    # An analogue Filtration pump — upstream's own gate, `PumpMaxSpeed > 1`
    # (`klereo.class.php` l.632, see api.py). Absent or `<= 1` (or on an installation
    # with no Filtration output at all) yields no entity: `switch.KlereoSwitch`'s plain
    # ON/OFF already covers a fixed-speed pump, unchanged.
    if details.pump_max_speed is not None and details.pump_max_speed > 1:
        pump = details.output_index.get(OUT_IDX_FILTRATION)
        if pump is not None:
            uid = f"{system_id}_pump_speed_{OUT_IDX_FILTRATION}"
            items.append(
                (uid, KlereoPumpSpeedNumber(coordinator, system_id, pump, details.pump_max_speed))
            )
    return items


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Klereo number entities."""
    setup_discovery(hass, entry, async_add_entities, _extract_numbers)


class KlereoNumber(KlereoEntity, NumberEntity):
    """Representation of a Klereo adjustable parameter."""

    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, system_id, key, initial_value, settings=None):
        """Initialize the number entity."""
        super().__init__(coordinator, system_id)
        self._key = key
        param = PARAM_TYPES[key]
        settings = settings or {}

        # The API sends the real bounds for this installation; the hard-coded pair is only
        # a fallback for a payload that carries none.
        self._attr_unique_id = f"{system_id}_number_{key}"
        self._attr_name = param["name"]
        self._attr_native_unit_of_measurement = param.get("unit")
        self._attr_native_min_value = settings.get(param.get("min_key"), param.get("min", 0))
        self._attr_native_max_value = settings.get(param.get("max_key"), param.get("max", 100))
        self._attr_native_step = param.get("step", 1)
        # A sentinel reads as `unknown`, never as a number: since #170 the guard no longer
        # refuses the entity on one, so `-2000` would otherwise land here and pin a Water
        # Setpoint at -2000 °C — outside its own 10-40 bounds, and the pinned-nonsense
        # control 1.9.0 refused to create. Mapped, not barred: the write is still offered,
        # because the box accepts it (#170).
        self._attr_native_value = setpoint_reading(initial_value)

    @callback
    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        system = self._system()
        if system is None:
            return super()._handle_coordinator_update()
        settings = system.details.settings
        if self._key in settings:
            # Mapped on the refresh path too: a setpoint disabled on the box AFTER setup
            # would otherwise pin the live entity at -2000.
            self._attr_native_value = setpoint_reading(settings[self._key])
        super()._handle_coordinator_update()

    async def async_set_native_value(self, value: float) -> None:
        """Set the parameter value."""
        self._attr_native_value = value
        self.async_write_ha_state()
        await self.coordinator.async_set_param(self.system_id, self._key, value)


class KlereoAutoOffNumber(KlereoEntity, NumberEntity):
    """The automatic-off timer of one output — Klereo's « Temps minuterie », in minutes.

    ⚠️ What this timer MEANS on an output that is not in Manual mode is unmeasured (#162):
    Bioul's output 1 runs under regulation (`mode 3`, `status 1`) and still reports
    `offDelay: 5`. The entity therefore reports the delay wherever the payload carries one
    and says nothing about when it fires — it is deliberately not hidden, not disabled and
    not annotated on non-manual outputs, since all three would assert an answer nobody has.
    """

    _attr_mode = NumberMode.BOX
    _attr_native_unit_of_measurement = "min"
    _attr_native_min_value = AUTO_OFF_MIN_MINUTES
    _attr_native_max_value = AUTO_OFF_MAX_MINUTES
    _attr_native_step = 1

    def __init__(self, coordinator, system_id, output: KlereoOutput):
        """Initialize the auto-off timer."""
        super().__init__(coordinator, system_id)
        self._output_index = output.index

        self._attr_unique_id = f"{system_id}_auto_off_{self._output_index}"
        name = OUTPUT_NAMES.get(self._output_index, f"Output {self._output_index}")
        self._attr_name = f"{name} Auto-Off Timer"
        self._attr_native_value = output.off_delay

    def _find_my_output(self) -> KlereoOutput | None:
        """Find this output's data in the coordinator data."""
        system = self._system()
        if system is None:
            return None
        return system.details.output_index.get(self._output_index)

    @property
    def available(self) -> bool:
        """Return False once the payload stops carrying this output.

        Narrows the base property the way the switch does: an output that vanishes must
        not leave its timer pinned to a last reading forever (#130).
        """
        return super().available and self._find_my_output() is not None

    @callback
    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        output = self._find_my_output()
        # An output that stops reporting `offDelay` keeps its last reading rather than
        # dropping to None: the entity goes unavailable through the property above, and
        # blanking the value here would say "no timer" where we simply stopped reading.
        if output is not None and output.off_delay is not None:
            self._attr_native_value = output.off_delay
        super()._handle_coordinator_update()

    async def async_set_native_value(self, value: float) -> None:
        """Set the automatic-off timer."""
        # Home Assistant hands every number a float; `offDelay` is an integer field on the
        # wire, and the step is 1, so there is no fraction to preserve.
        minutes = int(value)
        self._attr_native_value = minutes
        self.async_write_ha_state()
        await self.coordinator.async_set_auto_off(
            self.system_id, self._output_index, minutes
        )


class KlereoPumpSpeedNumber(KlereoEntity, NumberEntity):
    """Speed setpoint for a variable-speed ("analogue") Filtration pump (output 1).

    Bounded `0..PumpMaxSpeed`, sent verbatim as `newState` under `newMode=Manual` — see
    the sourcing comment above `OUT_IDX_FILTRATION` in `api.py` for the full citation
    (upstream Jeedom plugin; ✅ `PumpMaxSpeed` confirmed on five diagnostics exports).
    Created only when a payload carries the field above 1 (`_extract_numbers`), the
    "never invent, only read" rule `KlereoAutoOffNumber` follows for `offDelay`.

    Reports a value under Manual AND under Regulation — see `_update_from_output` for
    which field each reads and why. Every other mode still reports nothing.
    """

    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 0
    _attr_native_step = 1

    def __init__(self, coordinator, system_id, output: KlereoOutput, max_speed: int):
        """Initialize the pump-speed entity."""
        super().__init__(coordinator, system_id)
        self._output_index = output.index

        self._attr_unique_id = f"{system_id}_pump_speed_{self._output_index}"
        name = OUTPUT_NAMES.get(self._output_index, f"Output {self._output_index}")
        self._attr_name = f"{name} Speed"
        self._attr_icon = "mdi:pump"
        self._attr_native_max_value = max_speed

        self._update_from_output(output)

    @property
    def available(self) -> bool:
        """Return False once the payload stops carrying this output.

        Same narrowing as `KlereoAutoOffNumber.available` — see its docstring (#130).
        """
        return super().available and self._find_my_output() is not None

    @callback
    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        output = self._find_my_output()
        if output is not None:
            self._update_from_output(output)
        super()._handle_coordinator_update()

    def _update_from_output(self, output: KlereoOutput):
        """Update the reported speed from output data.

        Manual reads `status`; Regulation reads `real_status` instead — MEASURED, see
        `models.KlereoOutput.real_status` for the citation. Every other mode reports
        nothing, same as `switch.KlereoSwitch`.
        """
        try:
            mode = int(output.mode)
        except (ValueError, TypeError):
            mode = None

        if mode == OUT_MODE_MAN:
            raw = output.status
        elif mode == OUT_MODE_REGUL:
            raw = output.real_status
        else:
            raw = None

        if raw is None:
            self._attr_native_value = None
            return

        try:
            self._attr_native_value = int(raw)
        except (ValueError, TypeError):
            _LOGGER.warning(
                "Unexpected speed reading %r for output %s", raw, self._output_index
            )
            self._attr_native_value = None

    def _find_my_output(self) -> KlereoOutput | None:
        """Find this output's data in the coordinator data."""
        system = self._system()
        if system is None:
            return None
        return system.details.output_index.get(self._output_index)

    async def async_set_native_value(self, value: float) -> None:
        """Set the pump speed. Always sends Manual mode — the only mode a speed applies to."""
        speed = int(value)
        self._attr_native_value = speed
        self.async_write_ha_state()
        await self.coordinator.async_set_output(
            self.system_id, self._output_index, OUT_MODE_MAN, speed
        )
