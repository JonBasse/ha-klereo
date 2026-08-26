"""Sensor platform for Klereo."""
import logging
import re

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ALERT_LABELS,
    ALERT_PARAM_CALIBRATION,
    ALERT_PARAM_IS_ERROR_CODE,
    ALERT_PARAM_IS_FLOW,
    ALERT_PARAM_IS_OUTPUT,
    ALERT_PARAM_IS_PROBE,
    ALERT_PARAM_IS_PUMP,
    ALERT_PARAM_PREFIXES,
    BINARY_SENSOR_TYPES,
    OUTPUT_NAMES,
    PARAM_NAMES,
    PARAM_TYPES,
    SENSOR_TYPES,
)
from .entity import KlereoEntity, setup_discovery
from .models import KlereoAlert, KlereoPoolDetails, KlereoProbe

_LOGGER = logging.getLogger(__name__)


def _humanize_key(key: str) -> str:
    """Convert a camelCase API key to a human-readable name."""
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", key)


def _extract_sensors(coordinator, system_id, details: KlereoPoolDetails):
    """Extract probe sensors and param sensors from system details."""
    items = []
    for probe in details.probes:
        if probe.type in BINARY_SENSOR_TYPES:
            continue
        uid = f"{system_id}_sensor_{probe.index}"
        items.append((uid, KlereoSensor(coordinator, system_id, probe)))

    for key, value in details.regul_modes.items():
        if key in PARAM_TYPES:
            continue
        uid = f"{system_id}_param_{key}"
        items.append((uid, KlereoParamSensor(coordinator, system_id, key, value)))

    # `params` is only read through the curated PARAM_NAMES list. Upstream reads that
    # container at 40+ sites — consumption counters, setpoint bounds, internal flags — so
    # taking every key would create dozens of entities in every install. `RegulModes`
    # above stays unfiltered: it is what current installs already show, and narrowing it
    # would delete entities users have.
    seen = set(details.regul_modes)
    for container in (details.params, details.extra_params):
        for key, value in container.items():
            if key in PARAM_TYPES or key in seen or key not in PARAM_NAMES:
                continue
            seen.add(key)
            uid = f"{system_id}_param_{key}"
            items.append((uid, KlereoParamSensor(coordinator, system_id, key, value)))

    # Unconditionally, NOT on the presence of `alerts`: the key is absent when there is
    # nothing to report (GitHub #57), so keying the entity on it would make an alert
    # sensor that exists only while something is wrong — and vanishes, with its history,
    # the moment the pool is healthy. Same rule as the setpoint gates: a thing we cannot
    # read never removes an entity.
    items.append((f"{system_id}_alerts", KlereoAlertSensor(coordinator, system_id)))
    return items


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Klereo sensors."""
    setup_discovery(hass, entry, async_add_entities, _extract_sensors)


class KlereoSensor(KlereoEntity, SensorEntity):
    """Representation of a Klereo probe sensor."""

    def __init__(self, coordinator, system_id, probe: KlereoProbe):
        """Initialize the sensor."""
        super().__init__(coordinator, system_id)
        self._index = probe.index
        self._type = probe.type

        sensor_def = SENSOR_TYPES.get(self._type, {})

        self._attr_unique_id = f"{system_id}_sensor_{self._index}"
        self._attr_name = sensor_def.get("name", f"Sensor {self._index}")
        self._attr_native_unit_of_measurement = sensor_def.get("unit")
        self._attr_device_class = sensor_def.get("device_class")

        state_class = sensor_def.get("state_class")
        if state_class:
            self._attr_state_class = SensorStateClass(state_class)

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
        self._attr_native_value = value
        self._attr_extra_state_attributes = {
            "type": probe.type,
            "status": probe.status,
        }

    def _find_my_probe(self) -> KlereoProbe | None:
        """Find this probe's data in the coordinator data."""
        system = self.coordinator.data.get(self.system_id)
        if system is None:
            return None
        return system.details.probe_index.get(self._index)


class KlereoParamSensor(KlereoEntity, SensorEntity):
    """Representation of a Klereo regulation parameter as a sensor."""

    def __init__(self, coordinator, system_id, key, initial_value):
        """Initialize the parameter sensor."""
        super().__init__(coordinator, system_id)
        self._key = key

        self._attr_unique_id = f"{system_id}_param_{key}"
        self._attr_name = PARAM_NAMES.get(key, _humanize_key(key))
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


def _describe_alert_param(alert: KlereoAlert, details: KlereoPoolDetails) -> str | None:
    """Return what this alert's `param` means, or None when nothing sources it.

    🔴 `param` carries a different kind of identifier per code — a probe index, a flow id,
    an output index, a pump id, an error code — so rendering it raw is wrong more often
    than right. Codes with no documented meaning get no description rather than a
    plausible one (`klereo.class.php` l.575-596).

    Probe and output params resolve against what THIS installation actually reports, not
    against a ported lookup table: upstream carries a fixed CapteurID→label map, and a
    second source of truth for something we already parse is a drift waiting to happen.
    An index that resolves to nothing falls back to the number.
    """
    code, param = alert.code, alert.param

    if code == 5:
        # Upstream ignores `param` entirely here — the alert is always about the RFID
        # module, whatever it carries.
        return "RFID"
    if code == 6:
        return ALERT_PARAM_CALIBRATION.get(param)
    if param is None:
        return None
    if code in ALERT_PARAM_IS_PROBE:
        probe = details.probe_index.get(param)
        if probe is not None and probe.type in SENSOR_TYPES:
            return SENSOR_TYPES[probe.type]["name"]
        if probe is not None and probe.type in BINARY_SENSOR_TYPES:
            return BINARY_SENSOR_TYPES[probe.type]["name"]
        return f"sensor {param}"
    if code in ALERT_PARAM_IS_OUTPUT:
        return OUTPUT_NAMES.get(param, f"output {param}")
    if code in ALERT_PARAM_IS_FLOW:
        return f"flow {param}"
    if code in ALERT_PARAM_IS_PUMP:
        return f"pump {param}"
    if code in ALERT_PARAM_IS_ERROR_CODE:
        return f"error code {param}"
    prefix = ALERT_PARAM_PREFIXES.get(code)
    return f"{prefix} {param}" if prefix else None


def _render_alert(alert: KlereoAlert, details: KlereoPoolDetails) -> dict:
    """Render one alert as the attribute dict an automation reads."""
    label = ALERT_LABELS.get(alert.code)
    detail = _describe_alert_param(alert, details)
    if label is None:
        # Upstream says "Code alerte inconnu par le plugin" rather than mapping to a
        # neighbour. An alert we cannot name is still an alert worth counting and showing.
        label = f"Unknown alert code {alert.code}"
        detail = None
    return {
        "code": alert.code,
        "label": f"{label} - {detail}" if detail else label,
        "param": alert.param,
        "level": alert.level,
        "updated": alert.updated,
    }


class KlereoAlertSensor(KlereoEntity, SensorEntity):
    """The pool's active Klereo alerts: how many, and which ones.

    Requested in GitHub #57 and shaped by the reporter, who chose this over one
    binary_sensor per code (~25 entities per pool) and over an event (no dashboard state):
    *"It will allow me to trigger a notification on my phone when there is an alert and
    see exactly what the alert is."* The upstream plugin, written independently, exposes
    the same pair — an `alertCount` and an `alerts` text (`klereo.class.php` l.509-517).

    🔴 The state is `len(alerts)`, NOT the API's `alertCount`. The only measured payload
    carries `alertCount: 0` beside one active alert, so trusting that field would render a
    healthy-looking `0` over a real alert — a false green, on the entity whose entire job
    is to not be one. The reported figure is exposed as an attribute so the divergence
    stays visible.
    """

    _attr_icon = "mdi:pool"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, system_id):
        """Initialize the alert sensor."""
        super().__init__(coordinator, system_id)
        self._attr_unique_id = f"{system_id}_alerts"
        self._attr_name = "Alerts"
        self._apply()

    def _apply(self) -> None:
        """Read the current alerts off the coordinator into state and attributes."""
        system = self.coordinator.data.get(self.system_id)
        if system is None:
            self._attr_available = False
            return
        self._attr_available = True
        details = system.details
        rendered = [_render_alert(a, details) for a in details.alerts]
        self._attr_native_value = len(rendered)
        self._attr_extra_state_attributes = {
            "alerts": rendered,
            "codes": [a.code for a in details.alerts],
            # Klereo's own figure, kept for comparison and never used as the state.
            "reported_alert_count": details.reported_alert_count,
        }

    @callback
    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        self._apply()
        super()._handle_coordinator_update()
