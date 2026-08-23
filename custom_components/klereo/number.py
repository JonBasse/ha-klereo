"""Number platform for Klereo."""
import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    HEATER_MODES_WITHOUT_SETPOINT,
    PARAM_SENTINELS,
    PARAM_TYPES,
)
from .entity import KlereoEntity, setup_discovery
from .models import KlereoPoolDetails

_LOGGER = logging.getLogger(__name__)


def _is_offered(key: str, value, details: KlereoPoolDetails) -> bool:
    """Return whether this installation actually has this setpoint.

    An unknown answer never gates: a payload carrying neither `access` nor `HeaterMode`
    must keep the entity it has today. Only a value we can read, and that says "no",
    removes one.
    """
    param = PARAM_TYPES[key]

    if value in PARAM_SENTINELS:
        _LOGGER.debug("Skipping %s: sentinel value %s", key, value)
        return False

    min_access = param.get("min_access")
    if min_access is not None and details.access is not None and details.access < min_access:
        _LOGGER.debug(
            "Skipping %s: account access %s is below the required %s",
            key, details.access, min_access,
        )
        return False

    if param.get("needs_heater"):
        heater_mode = details.settings.get("HeaterMode")
        if heater_mode in HEATER_MODES_WITHOUT_SETPOINT:
            _LOGGER.debug("Skipping %s: HeaterMode %s carries no setpoint", key, heater_mode)
            return False

    return True


def _extract_numbers(coordinator, system_id, details: KlereoPoolDetails):
    """Extract number entities from system details."""
    items = []
    settings = details.settings
    for key, value in settings.items():
        if key not in PARAM_TYPES:
            continue
        if not _is_offered(key, value, details):
            continue
        uid = f"{system_id}_number_{key}"
        items.append((uid, KlereoNumber(coordinator, system_id, key, value, settings)))
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

    def __init__(self, coordinator, system_id, key, initial_value, settings=None):
        """Initialize the number entity."""
        super().__init__(coordinator, system_id)
        self._key = key
        param = PARAM_TYPES[key]
        settings = settings or {}

        # The API sends the real bounds for this installation; the hard-coded pair is only
        # a fallback for a payload that carries none.
        self._attr_unique_id = f"{system_id}_number_{key}"
        self._attr_name = param["name"]
        self._attr_native_unit_of_measurement = param.get("unit")
        self._attr_native_min_value = settings.get(param.get("min_key"), param.get("min", 0))
        self._attr_native_max_value = settings.get(param.get("max_key"), param.get("max", 100))
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
        settings = system.details.settings
        if self._key in settings:
            self._attr_native_value = settings[self._key]
        super()._handle_coordinator_update()

    async def async_set_native_value(self, value: float) -> None:
        """Set the parameter value."""
        self._attr_native_value = value
        self.async_write_ha_state()
        await self.coordinator.async_set_param(self.system_id, self._key, value)
