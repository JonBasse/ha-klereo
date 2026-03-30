"""Sensor platform for Klereo."""
import logging
import re

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import PARAM_NAMES, PARAM_TYPES, SENSOR_TYPES
from .entity import KlereoEntity, setup_discovery
from .models import KlereoPoolDetails, KlereoProbe

_LOGGER = logging.getLogger(__name__)


def _humanize_key(key: str) -> str:
    """Convert a camelCase API key to a human-readable name."""
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", key)


def _extract_sensors(coordinator, system_id, details: KlereoPoolDetails):
    """Extract probe sensors and param sensors from system details."""
    items = []
    for probe in details.probes:
        uid = f"{system_id}_sensor_{probe.index}"
        items.append((uid, KlereoSensor(coordinator, system_id, probe)))

    for key, value in details.regul_modes.items():
        if key in PARAM_TYPES:
            continue
        uid = f"{system_id}_param_{key}"
        items.append((uid, KlereoParamSensor(coordinator, system_id, key, value)))
    return items


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Klereo sensors."""
    setup_discovery(hass, entry, async_add_entities, _extract_sensors)


class KlereoSensor(KlereoEntity, SensorEntity):
    """Representation of a Klereo probe sensor."""

    def __init__(self, coordinator, system_id, probe: KlereoProbe):
        """Initialize the sensor."""
        super().__init__(coordinator, system_id)
        self._index = probe.index
        self._type = probe.type

        sensor_def = SENSOR_TYPES.get(self._type, {})

        self._attr_unique_id = f"{system_id}_sensor_{self._index}"
        self._attr_name = sensor_def.get("name", f"Sensor {self._index}")
        self._attr_native_unit_of_measurement = sensor_def.get("unit")
        self._attr_device_class = sensor_def.get("device_class")

        state_class = sensor_def.get("state_class")
        if state_class:
            self._attr_state_class = SensorStateClass(state_class)

        self._update_from_probe(probe)

    @callback
    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        probe = self._find_my_probe()
        if probe:
            self._attr_available = True
            self._update_from_probe(probe)
        else:
            self._attr_available = False
        super()._handle_coordinator_update()

    def _update_from_probe(self, probe: KlereoProbe):
        """Update state from probe data."""
        value = probe.filtered_value
        if value is None:
            value = probe.direct_value
        self._attr_native_value = value
        self._attr_extra_state_attributes = {
            "type": probe.type,
            "status": probe.status,
        }

    def _find_my_probe(self) -> KlereoProbe | None:
        """Find this probe's data in the coordinator data."""
        system = self.coordinator.data.get(self.system_id)
        if system is None:
            return None
        return system.details.probe_index.get(self._index)


class KlereoParamSensor(KlereoEntity, SensorEntity):
    """Representation of a Klereo regulation parameter as a sensor."""

    def __init__(self, coordinator, system_id, key, initial_value):
        """Initialize the parameter sensor."""
        super().__init__(coordinator, system_id)
        self._key = key

        self._attr_unique_id = f"{system_id}_param_{key}"
        self._attr_name = PARAM_NAMES.get(key, _humanize_key(key))
        self._attr_native_value = initial_value

    @callback
    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        system = self.coordinator.data.get(self.system_id)
        if system is None:
            self._attr_available = False
            return super()._handle_coordinator_update()
        self._attr_available = True
        regul = system.details.regul_modes
        if self._key in regul:
            self._attr_native_value = regul[self._key]
        super()._handle_coordinator_update()
