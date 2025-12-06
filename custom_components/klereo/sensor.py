"""Sensor platform for Klereo."""
import logging
from homeassistant.components.sensor import SensorEntity

from .const import DOMAIN, SENSOR_TYPES
from .debug_logger import log_to_file

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Klereo sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    
    log_to_file(f"SENSOR SETUP: Starting. Coordinator data systems: {len(coordinator.data)}")
    
    # Iterate over all systems found
    for system_id, system_data in coordinator.data.items():
        details = system_data.get("details", {})
        log_to_file(f"SENSOR SETUP: System {system_id} has keys: {list(details.keys())}")
        
        # Add Sensors from 'probes'
        if "probes" in details:
            for probe in details["probes"]:
                log_to_file(f"SENSOR SETUP: Adding probe {probe.get('index')} type {probe.get('type')}")
                entities.append(KlereoSensor(coordinator, system_id, probe))
        else:
             log_to_file(f"SENSOR SETUP: No 'probes' key for {system_id}")
                
        # Add Parameters as read-only sensors
        if "RegulModes" in details:
            for key, value in details["RegulModes"].items():
                 entities.append(KlereoParamSensor(coordinator, system_id, key, value))

    log_to_file(f"SENSOR SETUP: Final entity count: {len(entities)}")
    async_add_entities(entities)


class KlereoSensor(SensorEntity):
    """Representation of a Klereo Sensor (Probe)."""

    def __init__(self, coordinator, system_id, sensor_data):
        """Initialize the sensor."""
        self.coordinator = coordinator
        self.system_id = system_id
        # We store the index/type of the sensor to find it in updates
        self._index = sensor_data.get("index")
        self._type = sensor_data.get("type")
        
        sensor_def = SENSOR_TYPES.get(self._type, {})
        
        self._label = sensor_def.get("name", f"Unknown Sensor {self._type} (Index {self._index})")
        self._attr_unique_id = f"{system_id}_sensor_{self._index}"
        self._attr_name = f"Klereo {self._label}"
        
        self._attr_native_unit_of_measurement = sensor_def.get("unit")
        self._attr_device_class = sensor_def.get("device_class")
        
        # Store initial data to determine characteristics
        self._update_from_data(sensor_data)

    @property
    def should_poll(self):
        """No polling needed, coordinator handles it."""
        return False

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self.system_id)},
            "name": self.coordinator.data[self.system_id]["info"].get("poolNickname", "Klereo Pool"),
            "manufacturer": "Klereo",
            "model": "Pool System",
        }

    @property
    def available(self):
        """Return if entity is available."""
        return self.coordinator.last_update_success

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))

    def _update_from_data(self, data):
        """Update state from data."""
        # Use filteredValue if available, else directValue
        self._attr_native_value = data.get("filteredValue", data.get("directValue"))
        self._attr_extra_state_attributes = {
            "type": data.get("type"),
            "status": data.get("status")
        }

    def _find_my_data(self):
        """Find my data in the coordinator data."""
        if self.system_id not in self.coordinator.data:
            return None
        details = self.coordinator.data[self.system_id].get("details", {})
        if "probes" not in details:
            return None
        for p in details["probes"]:
            if p.get("index") == self._index:
                return p
        return None

    def update(self):
        """Update the entity."""
        data = self._find_my_data()
        if data:
            self._update_from_data(data)

class KlereoParamSensor(SensorEntity):
    """Representation of a Klereo Parameter as a Sensor."""
    
    def __init__(self, coordinator, system_id, key, initial_value):
        self.coordinator = coordinator
        self.system_id = system_id
        self._key = key
        
        self._attr_unique_id = f"{system_id}_param_{key}"
        self._attr_name = f"Klereo {key}"
        self._attr_native_value = initial_value

    @property
    def should_poll(self):
        return False
        
    @property
    def available(self):
        return self.coordinator.last_update_success

    async def async_added_to_hass(self):
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))

    def _find_my_data(self):
        if self.system_id not in self.coordinator.data:
            return None
        details = self.coordinator.data[self.system_id].get("details", {})
        if "RegulModes" in details and self._key in details["RegulModes"]:
             return details["RegulModes"][self._key]
        return None

    def update(self):
        val = self._find_my_data()
        if val is not None:
             self._attr_native_value = val
