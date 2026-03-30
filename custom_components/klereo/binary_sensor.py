"""Binary sensor platform for Klereo."""
import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import BINARY_SENSOR_TYPES
from .entity import KlereoEntity, setup_discovery
from .models import KlereoPoolDetails, KlereoProbe

_LOGGER = logging.getLogger(__name__)


def _extract_binary_sensors(coordinator, system_id, details: KlereoPoolDetails):
    """Extract binary sensors from system details."""
    items = []
    for probe in details.probes:
        if probe.type not in BINARY_SENSOR_TYPES:
            continue
        uid = f"{system_id}_binary_sensor_{probe.index}"
        items.append((uid, KlereoBinarySensor(coordinator, system_id, probe)))
    return items


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Klereo binary sensors."""
    setup_discovery(hass, entry, async_add_entities, _extract_binary_sensors)


class KlereoBinarySensor(KlereoEntity, BinarySensorEntity):
    """Representation of a Klereo binary probe sensor."""

    def __init__(self, coordinator, system_id, probe: KlereoProbe):
        """Initialize the binary sensor."""
        super().__init__(coordinator, system_id)
        self._index = probe.index
        self._type = probe.type

        sensor_def = BINARY_SENSOR_TYPES.get(self._type, {})

        self._attr_unique_id = f"{system_id}_binary_sensor_{self._index}"
        self._attr_name = sensor_def.get("name", f"Sensor {self._index}")
        self._attr_device_class = sensor_def.get("device_class")

        self._update_from_probe(probe)

    @callback
    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        probe = self._find_my_probe()
        if probe:
            self._attr_available = True
            self._update_from_probe(probe)
        else:
            self._attr_available = False
        super()._handle_coordinator_update()

    def _update_from_probe(self, probe: KlereoProbe):
        """Update state from probe data."""
        value = probe.filtered_value
        if value is None:
            value = probe.direct_value
        self._attr_is_on = bool(value) if value is not None else None

    def _find_my_probe(self) -> KlereoProbe | None:
        """Find this probe's data in the coordinator data."""
        system = self.coordinator.data.get(self.system_id)
        if system is None:
            return None
        return system.details.probe_index.get(self._index)
