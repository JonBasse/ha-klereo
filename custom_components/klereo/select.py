"""Select platform for Klereo."""
import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import (
    HEAT_MODES,
    OUT_IDX_HEATING,
    OUT_MODE_MAN,
    OUT_STATE_AUTO,
    OUT_STATE_OFF,
    OUT_STATE_ON,
    OUTPUT_MODES,
)
from .const import OUTPUT_NAMES
from .entity import KlereoEntity, setup_discovery
from .models import KlereoOutput, KlereoPoolDetails

_LOGGER = logging.getLogger(__name__)

# Reverse lookups: label → mode int, per mode family
_MODE_BY_LABEL = {v: k for k, v in OUTPUT_MODES.items()}
_HEAT_MODE_BY_LABEL = {v: k for k, v in HEAT_MODES.items()}


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

    def __init__(self, coordinator, system_id, output: KlereoOutput):
        """Initialize the select entity."""
        super().__init__(coordinator, system_id)
        self._output_index = output.index

        # Output 4 carries the KlereoTherm mode, not the output mode.
        self._is_heating = self._output_index == OUT_IDX_HEATING
        self._modes = HEAT_MODES if self._is_heating else OUTPUT_MODES
        self._mode_by_label = _HEAT_MODE_BY_LABEL if self._is_heating else _MODE_BY_LABEL
        self._attr_options = list(self._modes.values())

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
        self._attr_current_option = self._label_for_mode(output.mode)

    def _label_for_mode(self, mode) -> str | None:
        """Return the label for a reported mode, or None when there is no honest one.

        ⚠️ This used to fall back to `self._modes[0]` — "Manual" on an ordinary output,
        "Off" on the heating one. That turned "we do not know" into a specific, plausible,
        wrong answer, indistinguishable from an output genuinely in that mode. Klereo
        documents ten modes and two of them are internal-use, so an unlabelled mode is a
        normal occurrence, not a corrupt payload (#105).

        None is the honest report: Home Assistant renders it as unknown.
        """
        if mode is None:
            return None
        try:
            code = int(mode)
        except (ValueError, TypeError):
            _LOGGER.warning("Unexpected mode value %r for output %s", mode, self._output_index)
            return None

        label = self._modes.get(code)
        if label is None:
            _LOGGER.debug(
                "Output %s reports mode %s, which Klereo does not document as selectable",
                self._output_index, code,
            )
        return label

    def _find_my_output(self) -> KlereoOutput | None:
        """Find this output's data in the coordinator data."""
        system = self.coordinator.data.get(self.system_id)
        if system is None:
            return None
        return system.details.output_index.get(self._output_index)

    async def async_select_option(self, option: str) -> None:
        """Set the output mode."""
        mode = self._mode_by_label[option]
        state = self._state_for_mode(mode)

        self._attr_current_option = option
        self.async_write_ha_state()
        await self.coordinator.async_set_output(
            self.system_id, self._output_index, mode, state
        )

    def _state_for_mode(self, mode: int) -> int:
        """Pick the newState that goes with a newMode.

        Only Manual carries the ON/OFF state; every other mode hands control to
        the box and sends AUTO. On the heating output, any mode above Off is
        automatic. Source: klereo.class.php l.1525+ and l.1641-1655.
        """
        if self._is_heating:
            return OUT_STATE_AUTO if mode > 0 else OUT_STATE_OFF
        if mode != OUT_MODE_MAN:
            return OUT_STATE_AUTO

        # Manual: preserve the output's current ON/OFF state. A status of AUTO
        # has no ON/OFF meaning, so anything that is not ON becomes OFF.
        output = self._find_my_output()
        if output is None:
            return OUT_STATE_OFF
        try:
            return OUT_STATE_ON if int(output.status) == OUT_STATE_ON else OUT_STATE_OFF
        except (ValueError, TypeError):
            return OUT_STATE_OFF
