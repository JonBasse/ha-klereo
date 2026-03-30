"""Switch platform for Klereo."""
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import OUT_MODE_MAN, OUT_STATE_OFF, OUT_STATE_ON
from .const import OUTPUT_NAMES
from .entity import KlereoEntity, setup_discovery
from .models import KlereoOutput, KlereoPoolDetails

_LOGGER = logging.getLogger(__name__)


def _extract_switches(coordinator, system_id, details: KlereoPoolDetails):
    """Extract output switches from system details."""
    items = []
    for output in details.outs:
        uid = f"{system_id}_output_{output.index}"
        items.append((uid, KlereoSwitch(coordinator, system_id, output)))
    return items


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Klereo switches."""
    setup_discovery(hass, entry, async_add_entities, _extract_switches)


class KlereoSwitch(KlereoEntity, SwitchEntity):
    """Representation of a Klereo output switch."""

    def __init__(self, coordinator, system_id, output: KlereoOutput):
        """Initialize the switch."""
        super().__init__(coordinator, system_id)
        self._output_index = output.index

        self._attr_unique_id = f"{system_id}_output_{self._output_index}"
        self._attr_name = OUTPUT_NAMES.get(
            self._output_index, f"Output {self._output_index}"
        )

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
        status = output.status
        if status is not None:
            try:
                self._attr_is_on = int(status) == OUT_STATE_ON
            except (ValueError, TypeError):
                _LOGGER.warning("Unexpected status value %r for output %s", status, self._output_index)
                self._attr_is_on = False
        else:
            self._attr_is_on = False
        self._attr_extra_state_attributes = {
            "mode": output.mode,
            "type": output.type,
        }

    def _find_my_output(self) -> KlereoOutput | None:
        """Find this output's data in the coordinator data."""
        system = self.coordinator.data.get(self.system_id)
        if system is None:
            return None
        return system.details.output_index.get(self._output_index)

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
