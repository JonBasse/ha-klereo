"""Number platform for Klereo."""
import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

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
