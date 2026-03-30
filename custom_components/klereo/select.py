"""Select platform for Klereo."""
import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import OUTPUT_MODES
from .const import OUTPUT_NAMES
from .entity import KlereoEntity, setup_discovery
from .models import KlereoOutput, KlereoPoolDetails

_LOGGER = logging.getLogger(__name__)

# Reverse lookup: label → mode int
_MODE_BY_LABEL = {v: k for k, v in OUTPUT_MODES.items()}


def _extract_selects(coordinator, system_id, details: KlereoPoolDetails):
    """Extract output mode selects from system details."""
    items = []
    for output in details.outs:
        uid = f"{system_id}_output_mode_{output.index}"
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

    def __init__(self, coordinator, system_id, output: KlereoOutput):
        """Initialize the select entity."""
        super().__init__(coordinator, system_id)
        self._output_index = output.index

        self._attr_unique_id = f"{system_id}_output_mode_{self._output_index}"
        self._attr_name = f"{OUTPUT_NAMES.get(self._output_index, f'Output {self._output_index}')} Mode"

        self._update_from_output(output)

    @callback
    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        output = self._find_my_output()
        if output:
            self._attr_available = True
            self._update_from_output(output)
        else:
            self._attr_available = False
        super()._handle_coordinator_update()

    def _update_from_output(self, output: KlereoOutput):
        """Update state from output data."""
        mode = output.mode
        if mode is not None:
            try:
                self._attr_current_option = OUTPUT_MODES.get(int(mode), OUTPUT_MODES[0])
            except (ValueError, TypeError):
                _LOGGER.warning("Unexpected mode value %r for output %s", mode, self._output_index)
                self._attr_current_option = OUTPUT_MODES[0]
        else:
            self._attr_current_option = OUTPUT_MODES[0]

    def _find_my_output(self) -> KlereoOutput | None:
        """Find this output's data in the coordinator data."""
        system = self.coordinator.data.get(self.system_id)
        if system is None:
            return None
        return system.details.output_index.get(self._output_index)

    async def async_select_option(self, option: str) -> None:
        """Set the output mode."""
        mode = _MODE_BY_LABEL[option]
        # Read current state so we preserve ON/OFF
        output = self._find_my_output()
        current_state = 0
        if output:
            try:
                current_state = int(output.status)
            except (ValueError, TypeError):
                current_state = 0

        self._attr_current_option = option
        self.async_write_ha_state()
        await self.coordinator.async_set_output(
            self.system_id, self._output_index, mode, current_state
        )
