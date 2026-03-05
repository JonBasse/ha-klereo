"""Switch platform for Klereo."""
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, OUT_MODE_MAN, OUT_STATE_OFF, OUT_STATE_ON, OUTPUT_NAMES
from .entity import KlereoEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Klereo switches."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    known_ids: set[str] = set()

    @callback
    def _discover_entities() -> None:
        new_entities: list[SwitchEntity] = []

        for system_id, system_data in coordinator.data.items():
            details = system_data.get("details", {})
            for output in details.get("outs", []):
                if output.get("index") is None:
                    continue
                uid = f"{system_id}_output_{output['index']}"
                if uid not in known_ids:
                    known_ids.add(uid)
                    new_entities.append(
                        KlereoSwitch(coordinator, system_id, output)
                    )

        if new_entities:
            async_add_entities(new_entities)

    _discover_entities()
    entry.async_on_unload(coordinator.async_add_listener(_discover_entities))


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
            self._attr_available = True
            self._update_from_data(data)
        else:
            self._attr_available = False
        super()._handle_coordinator_update()

    def _update_from_data(self, data):
        """Update state from output data."""
        status = data.get("status")
        if status is not None:
            try:
                self._attr_is_on = int(status) == OUT_STATE_ON
            except (ValueError, TypeError):
                _LOGGER.warning("Unexpected status value %r for output %s", status, self._output_index)
                self._attr_is_on = False
        else:
            self._attr_is_on = False
        self._attr_extra_state_attributes = {
            "mode": data.get("mode"),
            "type": data.get("type"),
        }

    def _find_my_data(self):
        """Find this output's data in the coordinator data."""
        if self.system_id not in self.coordinator.data:
            return None
        details = self.coordinator.data[self.system_id].get("details", {})
        return details.get("_output_index", {}).get(self._output_index)

    async def async_turn_on(self, **kwargs):
        """Turn the output on (Manual mode, ON state)."""
        self._attr_is_on = True
        self.async_write_ha_state()
        await self.coordinator.async_set_output(
            self.system_id, self._output_index, OUT_MODE_MAN, OUT_STATE_ON
        )

    async def async_turn_off(self, **kwargs):
        """Turn the output off (Manual mode, OFF state)."""
        self._attr_is_on = False
        self.async_write_ha_state()
        await self.coordinator.async_set_output(
            self.system_id, self._output_index, OUT_MODE_MAN, OUT_STATE_OFF
        )
