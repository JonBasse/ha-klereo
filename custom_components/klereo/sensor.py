"""Sensor platform for Klereo."""
import logging

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SENSOR_TYPES

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Klereo sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    for system_id, system_data in coordinator.data.items():
        details = system_data.get("details", {})

        for probe in details.get("probes", []):
            entities.append(KlereoSensor(coordinator, system_id, probe))

        for key, value in details.get("RegulModes", {}).items():
            entities.append(KlereoParamSensor(coordinator, system_id, key, value))

    async_add_entities(entities)


class KlereoSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Klereo probe sensor."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, system_id, sensor_data):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.system_id = system_id
        self._index = sensor_data.get("index")
        self._type = sensor_data.get("type")

        sensor_def = SENSOR_TYPES.get(self._type, {})

        self._attr_unique_id = f"{system_id}_sensor_{self._index}"
        self._attr_name = sensor_def.get("name", f"Sensor {self._index}")
        self._attr_native_unit_of_measurement = sensor_def.get("unit")
        self._attr_device_class = sensor_def.get("device_class")

        self._update_from_data(sensor_data)

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self.system_id)},
            "name": self.coordinator.data[self.system_id]["info"].get(
                "poolNickname", "Klereo Pool"
            ),
            "manufacturer": "Klereo",
            "model": "Pool System",
        }

    @callback
    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        data = self._find_my_data()
        if data:
            self._update_from_data(data)
        super()._handle_coordinator_update()

    def _update_from_data(self, data):
        """Update state from probe data."""
        self._attr_native_value = data.get("filteredValue", data.get("directValue"))
        self._attr_extra_state_attributes = {
            "type": data.get("type"),
            "status": data.get("status"),
        }

    def _find_my_data(self):
        """Find this probe's data in the coordinator data."""
        if self.system_id not in self.coordinator.data:
            return None
        details = self.coordinator.data[self.system_id].get("details", {})
        for p in details.get("probes", []):
            if p.get("index") == self._index:
                return p
        return None


class KlereoParamSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Klereo regulation parameter as a sensor."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, system_id, key, initial_value):
        """Initialize the parameter sensor."""
        super().__init__(coordinator)
        self.system_id = system_id
        self._key = key

        self._attr_unique_id = f"{system_id}_param_{key}"
        self._attr_name = key
        self._attr_native_value = initial_value

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self.system_id)},
            "name": self.coordinator.data[self.system_id]["info"].get(
                "poolNickname", "Klereo Pool"
            ),
            "manufacturer": "Klereo",
            "model": "Pool System",
        }

    @callback
    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        if self.system_id not in self.coordinator.data:
            return
        details = self.coordinator.data[self.system_id].get("details", {})
        regul = details.get("RegulModes", {})
        if self._key in regul:
            self._attr_native_value = regul[self._key]
        super()._handle_coordinator_update()
