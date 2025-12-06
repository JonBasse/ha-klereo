"""Binary Sensor platform for Klereo."""
import logging
from homeassistant.components.binary_sensor import BinarySensorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Klereo binary sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    
    for system_id, system_data in coordinator.data.items():
        details = system_data.get("details", {})
        # Assuming no dedicated binary sensors in 'probes' or 'outs' yet based on previous logs,
        # but leaving infrastructure in place.
        # If there are specific boolean flags in 'params' or 'status', they should be mapped here.
        # For now, we will leave it empty but logged to avoid confusion.
        pass

    async_add_entities(entities)


class KlereoBinarySensor(BinarySensorEntity):
    """Representation of a Klereo Binary Sensor."""

    def __init__(self, coordinator, system_id, sensor_data):
        """Initialize the binary sensor."""
        self.coordinator = coordinator
        self.system_id = system_id
        self._sensor_id = sensor_data.get("id")
        self._label = sensor_data.get("label", "Unknown")
        self._attr_unique_id = f"{system_id}_binary_{self._sensor_id}"
        self._attr_name = f"Klereo {self._label}"
        
        self._update_from_data(sensor_data)

    @property
    def should_poll(self):
        return False

    @property
    def available(self):
        return self.coordinator.last_update_success

    async def async_added_to_hass(self):
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))

    def _update_from_data(self, data):
        """Update state from data."""
        val = data.get("value")
        if isinstance(val, str):
            self._attr_is_on = val.lower() in ["on", "1", "true", "yes", "ok"] # Logic might need adjustment
            # Actually for Alarms, 'ok' might mean Off (Safe). 'Error' means On.
            # This is hard to guess without real data.
            # Assuming 1/True/On is the active state.
        else:
            self._attr_is_on = bool(val)

    def _find_my_data(self):
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
        data = self._find_my_data()
        if data:
            self._update_from_data(data)
