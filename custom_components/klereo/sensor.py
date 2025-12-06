"""Sensor platform for Klereo."""
import logging
from homeassistant.components.sensor import SensorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Klereo sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    
    # Iterate over all systems found
    for system_id, system_data in coordinator.data.items():
        details = system_data.get("details", {})
        
        # Add Sensors
        if "list_sensors" in details:
            for sensor in details["list_sensors"]:
                entities.append(KlereoSensor(coordinator, system_id, sensor))
                
        # Add Parameters as read-only sensors for now (unless number platform added)
        if "list_params" in details:
            for param in details["list_params"]:
                 entities.append(KlereoParamSensor(coordinator, system_id, param))

    async_add_entities(entities)


class KlereoSensor(SensorEntity):
    """Representation of a Klereo Sensor."""

    def __init__(self, coordinator, system_id, sensor_data):
        """Initialize the sensor."""
        self.coordinator = coordinator
        self.system_id = system_id
        # We store the ID of the sensor to find it in updates
        self._sensor_id = sensor_data.get("id")
        self._label = sensor_data.get("label", "Unknown")
        self._attr_unique_id = f"{system_id}_sensor_{self._sensor_id}"
        self._attr_name = f"Klereo {self._label}"
        
        # Determine unit and device class based on type or label if possible
        # This is a heuristic.
        self._attr_native_unit_of_measurement = sensor_data.get("unit")
        
        # Store initial data to determine characteristics
        self._update_from_data(sensor_data)

    @property
    def should_poll(self):
        """No polling needed, coordinator handles it."""
        return False

    @property
    def available(self):
        """Return if entity is available."""
        return self.coordinator.last_update_success

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))

    def _update_from_data(self, data):
        """Update state from data."""
        self._attr_native_value = data.get("value")
        self._attr_extra_state_attributes = {
            "type": data.get("type")
        }

    def _find_my_data(self):
        """Find my data in the coordinator data."""
        if self.system_id not in self.coordinator.data:
            return None
        details = self.coordinator.data[self.system_id].get("details", {})
        if "list_sensors" not in details:
            return None
        for s in details["list_sensors"]:
            if s.get("id") == self._sensor_id:
                return s
        return None

    def update(self):
        """Update the entity."""
        data = self._find_my_data()
        if data:
            self._update_from_data(data)

class KlereoParamSensor(SensorEntity):
    """Representation of a Klereo Parameter as a Sensor."""
    
    def __init__(self, coordinator, system_id, param_data):
        self.coordinator = coordinator
        self.system_id = system_id
        self._param_id = param_data.get("id")
        self._label = param_data.get("label", "Unknown")
        self._attr_unique_id = f"{system_id}_param_{self._param_id}"
        self._attr_name = f"Klereo {self._label}"
        self._attr_native_unit_of_measurement = param_data.get("unit")
        self._update_from_data(param_data)

    @property
    def should_poll(self):
        return False
        
    @property
    def available(self):
        return self.coordinator.last_update_success

    async def async_added_to_hass(self):
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))

    def _update_from_data(self, data):
        self._attr_native_value = data.get("value")

    def _find_my_data(self):
        if self.system_id not in self.coordinator.data:
            return None
        details = self.coordinator.data[self.system_id].get("details", {})
        if "list_params" not in details:
            return None
        for p in details["list_params"]:
            if p.get("id") == self._param_id:
                return p
        return None

    def update(self):
        data = self._find_my_data()
        if data:
            self._update_from_data(data)
