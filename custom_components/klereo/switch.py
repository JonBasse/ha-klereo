"""Switch platform for Klereo."""
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, OUTPUT_NAMES, OUT_MODE_MAN, OUT_STATE_ON, OUT_STATE_OFF
from .entity import KlereoEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Klereo switches."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    for system_id, system_data in coordinator.data.items():
        details = system_data.get("details", {})
        for output in details.get("outs", []):
            if output.get("index") is None:
                _LOGGER.warning("Skipping output with no index: %s", output)
                continue
            entities.append(KlereoSwitch(coordinator, system_id, output))

    async_add_entities(entities)


class KlereoSwitch(KlereoEntity, SwitchEntity):
    """Representation of a Klereo output switch."""

    def __init__(self, coordinator, system_id, output_data):
        """Initialize the switch."""
        super().__init__(coordinator, system_id)
        self._output_index = output_data.get("index")

        self._attr_unique_id = f"{system_id}_output_{self._output_index}"
        self._attr_name = OUTPUT_NAMES.get(
            self._output_index, f"Output {self._output_index}"
        )

        self._update_from_data(output_data)

    @callback
    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        data = self._find_my_data()
        if data:
            self._update_from_data(data)
        super()._handle_coordinator_update()

    def _update_from_data(self, data):
        """Update state from output data."""
        self._attr_is_on = data.get("status") == OUT_STATE_ON
        self._attr_extra_state_attributes = {
            "mode": data.get("mode"),
            "type": data.get("type"),
        }

    def _find_my_data(self):
        """Find this output's data in the coordinator data."""
        if self.system_id not in self.coordinator.data:
            return None
        details = self.coordinator.data[self.system_id].get("details", {})
        for o in details.get("outs", []):
            if o.get("index") == self._output_index:
                return o
        return None

    async def async_turn_on(self, **kwargs):
        """Turn the output on (Manual mode, ON state)."""
        await self.coordinator.api.set_output(
            self.system_id, self._output_index, OUT_MODE_MAN, OUT_STATE_ON
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        """Turn the output off (Manual mode, OFF state)."""
        await self.coordinator.api.set_output(
            self.system_id, self._output_index, OUT_MODE_MAN, OUT_STATE_OFF
        )
        await self.coordinator.async_request_refresh()
