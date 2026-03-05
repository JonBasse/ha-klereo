"""Number platform for Klereo."""
import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, PARAM_TYPES
from .entity import KlereoEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Klereo number entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    known_ids: set[str] = set()

    @callback
    def _discover_entities() -> None:
        new_entities: list[NumberEntity] = []

        for system_id, system_data in coordinator.data.items():
            details = system_data.get("details", {})
            for key, value in details.get("RegulModes", {}).items():
                if key not in PARAM_TYPES:
                    continue
                uid = f"{system_id}_number_{key}"
                if uid not in known_ids:
                    known_ids.add(uid)
                    new_entities.append(
                        KlereoNumber(coordinator, system_id, key, value)
                    )

        if new_entities:
            async_add_entities(new_entities)

    _discover_entities()
    entry.async_on_unload(coordinator.async_add_listener(_discover_entities))


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
        if self.system_id not in self.coordinator.data:
            self._attr_available = False
            return super()._handle_coordinator_update()
        self._attr_available = True
        details = self.coordinator.data[self.system_id].get("details", {})
        regul = details.get("RegulModes", {})
        if self._key in regul:
            self._attr_native_value = regul[self._key]
        super()._handle_coordinator_update()

    async def async_set_native_value(self, value: float) -> None:
        """Set the parameter value."""
        try:
            await self.coordinator.api.set_param(self.system_id, self._key, value)
        except Exception as err:
            raise HomeAssistantError(
                f"Failed to set {self._attr_name}: {err}"
            ) from err
        self._attr_native_value = value
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
