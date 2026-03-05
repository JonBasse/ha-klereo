"""Sensor platform for Klereo."""
import logging

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, PARAM_TYPES, SENSOR_TYPES
from .entity import KlereoEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Klereo sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    known_sensor_ids: set[str] = set()
    known_param_ids: set[str] = set()

    @callback
    def _discover_entities() -> None:
        new_entities: list[SensorEntity] = []

        for system_id, system_data in coordinator.data.items():
            details = system_data.get("details", {})

            for probe in details.get("probes", []):
                if probe.get("index") is None:
                    continue
                uid = f"{system_id}_sensor_{probe['index']}"
                if uid not in known_sensor_ids:
                    known_sensor_ids.add(uid)
                    new_entities.append(
                        KlereoSensor(coordinator, system_id, probe)
                    )

            for key, value in details.get("RegulModes", {}).items():
                if key in PARAM_TYPES:
                    continue
                uid = f"{system_id}_param_{key}"
                if uid not in known_param_ids:
                    known_param_ids.add(uid)
                    new_entities.append(
                        KlereoParamSensor(coordinator, system_id, key, value)
                    )

        if new_entities:
            async_add_entities(new_entities)

    _discover_entities()
    entry.async_on_unload(coordinator.async_add_listener(_discover_entities))


class KlereoSensor(KlereoEntity, SensorEntity):
    """Representation of a Klereo probe sensor."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, system_id, sensor_data):
        """Initialize the sensor."""
        super().__init__(coordinator, system_id)
        self._index = sensor_data.get("index")
        self._type = sensor_data.get("type")

        sensor_def = SENSOR_TYPES.get(self._type, {})

        self._attr_unique_id = f"{system_id}_sensor_{self._index}"
        self._attr_name = sensor_def.get("name", f"Sensor {self._index}")
        self._attr_native_unit_of_measurement = sensor_def.get("unit")
        self._attr_device_class = sensor_def.get("device_class")

        self._update_from_data(sensor_data)

    @callback
    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        data = self._find_my_data()
        if data:
            self._update_from_data(data)
        super()._handle_coordinator_update()

    def _update_from_data(self, data):
        """Update state from probe data."""
        value = data.get("filteredValue")
        if value is None:
            value = data.get("directValue")
        self._attr_native_value = value
        self._attr_extra_state_attributes = {
            "type": data.get("type"),
            "status": data.get("status"),
        }

    def _find_my_data(self):
        """Find this probe's data in the coordinator data."""
        if self.system_id not in self.coordinator.data:
            return None
        details = self.coordinator.data[self.system_id].get("details", {})
        return details.get("_probe_index", {}).get(self._index)


class KlereoParamSensor(KlereoEntity, SensorEntity):
    """Representation of a Klereo regulation parameter as a sensor."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, system_id, key, initial_value):
        """Initialize the parameter sensor."""
        super().__init__(coordinator, system_id)
        self._key = key

        self._attr_unique_id = f"{system_id}_param_{key}"
        self._attr_name = key
        self._attr_native_value = initial_value

    @callback
    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        if self.system_id not in self.coordinator.data:
            self._attr_available = False
            return super()._handle_coordinator_update()
        self._attr_available = True
        details = self.coordinator.data[self.system_id].get("details", {})
        regul = details.get("RegulModes", {})
        if self._key in regul:
            self._attr_native_value = regul[self._key]
        super()._handle_coordinator_update()
