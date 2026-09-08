"""Button platform for Klereo."""
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import KlereoEntity, setup_discovery
from .models import KlereoPoolDetails

_LOGGER = logging.getLogger(__name__)


def _extract_buttons(coordinator, system_id, details: KlereoPoolDetails):
    """Extract the refresh button of a system.

    One per pool, unconditionally: unlike every other platform here there is nothing in the
    payload to gate on. A pool that is reported at all can be re-read.
    """
    uid = f"{system_id}_refresh"
    return [(uid, KlereoRefreshButton(coordinator, system_id))]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Klereo buttons."""
    setup_discovery(hass, entry, async_add_entities, _extract_buttons)


class KlereoRefreshButton(KlereoEntity, ButtonEntity):
    """Re-read this pool from the Klereo cloud, on demand.

    Asked for by @StephanH27 (GitHub #61, Forgejo #164) because the v1 and v3 web
    interfaces carry such a button. The capture that unblocked the ticket shows that
    button emitting one `POST GetPoolDetails.php` and nothing else, so this one does the
    same thing rather than a local approximation of something larger.

    ⚠️ The name says Klereo on purpose. Nothing here talks to the box at the poolside: the
    integration reads a cloud that the box updates on its own schedule, and a name like
    "Sync" or "Update pool" would promise a conversation that does not happen.
    """

    _attr_name = "Refresh from Klereo"
    _attr_icon = "mdi:cloud-refresh"

    def __init__(self, coordinator, system_id: str) -> None:
        """Initialize the button."""
        super().__init__(coordinator, system_id)
        self._attr_unique_id = f"{system_id}_refresh"

    async def async_press(self) -> None:
        """Ask the coordinator to re-read Klereo.

        Straight through to a coordinator method, like every other command in this
        integration — and here that also puts the rate limit somewhere a second caller
        cannot walk around. The refusal it raises reaches the user as an error rather than
        being swallowed: a button that silently does nothing is indistinguishable from a
        broken one.
        """
        await self.coordinator.async_manual_refresh()
