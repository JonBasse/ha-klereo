"""Number platform for Klereo."""
import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import PARAM_TYPES
from .entity import KlereoEntity, setup_discovery
from .models import KlereoPoolDetails

_LOGGER = logging.getLogger(__name__)


def _extract_numbers(coordinator, system_id, details: KlereoPoolDetails):
    """Extract number entities from system details."""
    items = []
    for key, value in details.regul_modes.items():
        if key not in PARAM_TYPES:
            continue
        uid = f"{system_id}_number_{key}"
        items.append((uid, KlereoNumber(coordinator, system_id, key, value)))
    return items


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Klereo number entities."""
    setup_discovery(hass, entry, async_add_entities, _extract_numbers)


class KlereoNumber(KlereoEntity, NumberEntity):
    """Representation of a Klereo adjustable parameter."""

    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, system_id, key, initial_value):
        """Initialize the number entity."""
        super().__init__(coordinator, system_id)
        self._key = key
        param = PARAM_TYPES[key]

        self._attr_unique_id = f"{system_id}_number_{key}"
        self._attr_name = param["name"]
        self._attr_native_unit_of_measurement = param.get("unit")
        self._attr_native_min_value = param.get("min", 0)
        self._attr_native_max_value = param.get("max", 100)
        self._attr_native_step = param.get("step", 1)
        self._attr_native_value = initial_value

    @callback
    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        system = self.coordinator.data.get(self.system_id)
        if system is None:
            self._attr_available = False
            return super()._handle_coordinator_update()
        self._attr_available = True
        regul = system.details.regul_modes
        if self._key in regul:
            self._attr_native_value = regul[self._key]
        super()._handle_coordinator_update()

    async def async_set_native_value(self, value: float) -> None:
        """Set the parameter value."""
        self._attr_native_value = value
        self.async_write_ha_state()
        await self.coordinator.async_set_param(self.system_id, self._key, value)
