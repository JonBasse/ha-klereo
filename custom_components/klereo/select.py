"""Select platform for Klereo."""
import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import OUTPUT_MODES
from .const import OUTPUT_NAMES
from .entity import KlereoEntity, setup_discovery

_LOGGER = logging.getLogger(__name__)

# Reverse lookup: label → mode int
_MODE_BY_LABEL = {v: k for k, v in OUTPUT_MODES.items()}


def _extract_selects(coordinator, system_id, details):
    """Extract output mode selects from system details."""
    items = []
    for output in details.get("outs", []):
        if output.get("index") is None:
            continue
        uid = f"{system_id}_output_mode_{output['index']}"
        items.append((uid, KlereoOutputModeSelect(coordinator, system_id, output)))
    return items


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Klereo output mode selects."""
    setup_discovery(hass, entry, async_add_entities, _extract_selects)


class KlereoOutputModeSelect(KlereoEntity, SelectEntity):
    """Representation of a Klereo output mode selector."""

    _attr_options = list(OUTPUT_MODES.values())

    def __init__(self, coordinator, system_id, output_data):
        """Initialize the select entity."""
        super().__init__(coordinator, system_id)
        self._output_index = output_data.get("index")

        self._attr_unique_id = f"{system_id}_output_mode_{self._output_index}"
        self._attr_name = f"{OUTPUT_NAMES.get(self._output_index, f'Output {self._output_index}')} Mode"

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
        mode = data.get("mode")
        if mode is not None:
            try:
                self._attr_current_option = OUTPUT_MODES.get(int(mode), OUTPUT_MODES[0])
            except (ValueError, TypeError):
                _LOGGER.warning("Unexpected mode value %r for output %s", mode, self._output_index)
                self._attr_current_option = OUTPUT_MODES[0]
        else:
            self._attr_current_option = OUTPUT_MODES[0]

    def _find_my_data(self):
        """Find this output's data in the coordinator data."""
        if self.system_id not in self.coordinator.data:
            return None
        details = self.coordinator.data[self.system_id].get("details", {})
        return details.get("_output_index", {}).get(self._output_index)

    async def async_select_option(self, option: str) -> None:
        """Set the output mode."""
        mode = _MODE_BY_LABEL[option]
        # Read current state so we preserve ON/OFF
        data = self._find_my_data()
        current_state = 0
        if data:
            try:
                current_state = int(data.get("status", 0))
            except (ValueError, TypeError):
                current_state = 0

        self._attr_current_option = option
        self.async_write_ha_state()
        await self.coordinator.async_set_output(
            self.system_id, self._output_index, mode, current_state
        )
