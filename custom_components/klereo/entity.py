"""Base entity for Klereo."""
import logging
from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ACCESS_POOL_PROFESSIONAL, DOMAIN, PRO_ONLY_OUTPUTS
from .coordinator import KlereoCoordinator
from .models import KlereoPoolDetails

_LOGGER = logging.getLogger(__name__)


def is_output_offered(index: int, details: KlereoPoolDetails) -> bool:
    """Return whether this account may be offered an entity for this output.

    Outputs 2, 3, 8 and 15 take a `newMode` whose meaning is undocumented, and upstream
    refuses to command them below professional access rather than guessing it. Offering a
    switch or a select there hands the user a control whose every write comes back as
    status 13 — visible as an error since #95, and silently wrong before it.

    ⚠️ An unknown `access` NEVER gates. The field is optional, and "we do not know" must
    not remove an entity a working installation already has. Same rule, and the same
    reason, as `_is_offered` in `number.py`.
    """
    if index not in PRO_ONLY_OUTPUTS:
        return True
    if details.access is None or details.access >= ACCESS_POOL_PROFESSIONAL:
        return True
    _LOGGER.debug(
        "Skipping output %s: account access %s is below the required %s",
        index, details.access, ACCESS_POOL_PROFESSIONAL,
    )
    return False


class KlereoEntity(CoordinatorEntity[KlereoCoordinator]):
    """Base class for Klereo entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: KlereoCoordinator, system_id: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.system_id = system_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        system = self.coordinator.data.get(self.system_id)
        name = system.info.pool_nickname if system else "Klereo Pool"
        return DeviceInfo(
            identifiers={(DOMAIN, self.system_id)},
            name=name,
            manufacturer="Klereo",
            model="Pool System",
        )


def setup_discovery(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    extract_fn: Callable[[KlereoCoordinator, str, KlereoPoolDetails], list[KlereoEntity]],
) -> None:
    """Set up dynamic entity discovery for a platform.

    Args:
        extract_fn: Called with (coordinator, system_id, details) and returns
            a list of (uid, entity) tuples for new entities to register.
    """
    coordinator: KlereoCoordinator = hass.data[DOMAIN][entry.entry_id]
    known_ids: set[str] = set()

    @callback
    def _discover() -> None:
        new_entities: list[KlereoEntity] = []
        for system_id, system_data in coordinator.data.items():
            for uid, entity in extract_fn(coordinator, system_id, system_data.details):
                if uid not in known_ids:
                    known_ids.add(uid)
                    new_entities.append(entity)
        if new_entities:
            async_add_entities(new_entities)

    _discover()
    entry.async_on_unload(coordinator.async_add_listener(_discover))
