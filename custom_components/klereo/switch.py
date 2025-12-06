"""Switch platform for Klereo."""
import logging
from homeassistant.components.switch import SwitchEntity

from .const import DOMAIN, OUTPUT_NAMES
from .debug_logger import log_to_file

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Klereo switches."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    
    log_to_file(f"SWITCH SETUP: Starting. Coordinator data systems: {len(coordinator.data)}")
    
    for system_id, system_data in coordinator.data.items():
        details = system_data.get("details", {})
        
        if "outs" in details:
            for output in details["outs"]:
                # Check if it's a binary controllable output
                # Using all outputs for now as switches
                log_to_file(f"SWITCH SETUP: Adding switch {output.get('index')}")
                entities.append(KlereoSwitch(coordinator, system_id, output))
        else:
            log_to_file(f"SWITCH SETUP: No 'outs' key for {system_id}")

    log_to_file(f"SWITCH SETUP: Final entity count: {len(entities)}")
    async_add_entities(entities)


class KlereoSwitch(SwitchEntity):
    """Representation of a Klereo Switch."""

    def __init__(self, coordinator, system_id, output_data):
        """Initialize the switch."""
        self.coordinator = coordinator
        self.system_id = system_id
        self._output_id = output_data.get("index") # In global 'outs' list, id is index
        
        self._label = OUTPUT_NAMES.get(self._output_id, f"Output {self._output_id}")
        
        self._attr_unique_id = f"{system_id}_output_{self._output_id}"
        self._attr_name = f"Klereo {self._label}"
        self._attr_has_entity_name = True # Use device name + this name
        
        self._update_from_data(output_data)

    @property
    def should_poll(self):
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
        return self.coordinator.last_update_success

    async def async_added_to_hass(self):
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))

    def _update_from_data(self, data):
        """Update state from data."""
        # Status 1 = On, 0 = Off
        val = data.get("status")
        # Could also check 'realStatus' ?
        
        self._attr_is_on = bool(val)
            
        self._attr_extra_state_attributes = {
            "mode": data.get("mode"), # Auto, Manu, etc.
            "type": data.get("type")
        }

    def _find_my_data(self):
        if self.system_id not in self.coordinator.data:
            return None
        details = self.coordinator.data[self.system_id].get("details", {})
        if "outs" not in details:
            return None
        for o in details["outs"]:
            if o.get("index") == self._output_id:
                return o
        return None
        
    def update(self):
         data = self._find_my_data()
         if data:
             self._update_from_data(data)

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        # Force to Manual On
        # Mode 1 = Manual? Need to check numeric constant. Jeedom: Out Mode Man = 1
        # State 1 = On
        await self.coordinator.api.set_output(self.system_id, self._output_id, 1, 1, 0)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        # Force to Manual Off
        # Mode 1 = Manual, State 0 = Off
        await self.coordinator.api.set_output(self.system_id, self._output_id, 1, 0, 0)
        await self.coordinator.async_request_refresh()
