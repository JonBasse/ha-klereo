"""Base entity for Klereo."""
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import KlereoCoordinator


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
        system = self.coordinator.data.get(self.system_id, {})
        name = system.get("info", {}).get("poolNickname", "Klereo Pool")
        return DeviceInfo(
            identifiers={(DOMAIN, self.system_id)},
            name=name,
            manufacturer="Klereo",
            model="Pool System",
        )
