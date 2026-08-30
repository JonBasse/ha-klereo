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
    DERIVED_COUNTER_TYPES,
    NO_REFERENCE_PROBE,
    OUTPUT_NAMES,
    PARAM_COUNTER_TYPES,
    PARAM_NAMES,
    PARAM_SENTINELS,
    PARAM_TYPES,
    SENSOR_TYPES,
)
from .entity import KlereoEntity, is_setpoint_offered, setup_discovery
from .models import KlereoAlert, KlereoPoolDetails, KlereoProbe

_LOGGER = logging.getLogger(__name__)


def _humanize_key(key: str) -> str:
    """Convert a camelCase API key to a human-readable name."""
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", key)


def _reading(value):
    """Return a setpoint's value, or `None` when Klereo sent a sentinel instead.

    `-2000` means the setpoint is DISABLED and `-1000` that it is UNKNOWN. Neither is a
    measurement, and an entity named *pH Setpoint* holding one feeds Home Assistant's
    statistics, graphs and averages a plausible, wrong number. Upstream discards both
    (`klereo.class.php` l.873-896); `number` already refuses them through
    `is_setpoint_offered`, and `climate` refuses them too. `sensor` was the one path that
    did not. See #137.

    🔴 The VALUE is mapped, never the existence. Not creating the entity would delete a
    sensor installs already have and break any automation referencing it — the harm #128
    and #135 exist to prevent. `None` renders as `unknown`, which is exactly what the
    sentinel says.

    ⚠️ The `isinstance` guard is not decoration. `regul_modes` is read UNFILTERED on
    purpose (#94), so a value here is whatever Klereo sent; a bare `value in
    PARAM_SENTINELS` raises `TypeError` on anything unhashable and would take the whole
    platform down rather than one reading. And `-1` must NOT be caught: `const.py` calls
    reusing it "a false friend that happens to work" — a setpoint of -1 is a real number.
    """
    if isinstance(value, int | float) and value in PARAM_SENTINELS:
        return None
    return value


def _extract_sensors(coordinator, system_id, details: KlereoPoolDetails):
    """Extract probe sensors and param sensors from system details."""
    items = []
    for probe in details.probes:
        if probe.type in BINARY_SENSOR_TYPES:
            continue
        uid = f"{system_id}_sensor_{probe.index}"
        items.append((uid, KlereoSensor(coordinator, system_id, probe)))

    # A writable setpoint becomes a `number` instead — but ONLY when the write is actually
    # offered. When a guard refuses it (access too low, pHMode off, HeaterMode without a
    # setpoint), the read-only sensor stays: the account cannot write the value, and that
    # is no reason to stop showing it. Excluding on `key in PARAM_TYPES` alone is what
    # #128 fixes; it would have deleted three sensors from every account below access 16.
    # `key not in PARAM_NAMES` is what keeps `ConsigneEau` out. This loop is otherwise
    # unfiltered, so without it a refused water setpoint would fall back here even though
    # it has never been a sensor — and on a sentinel payload that means a brand-new entity
    # reading -2000. The `params` loop below already carries the same condition.
    for key, value in details.regul_modes.items():
        if key in PARAM_TYPES and (is_setpoint_offered(key, details) or key not in PARAM_NAMES):
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
            if key in seen or key not in PARAM_NAMES:
                continue
            if key in PARAM_TYPES and is_setpoint_offered(key, details):
                continue
            seen.add(key)
            uid = f"{system_id}_param_{key}"
            items.append((uid, KlereoParamSensor(coordinator, system_id, key, value)))

    # Product consumption is the one figure Klereo does not send: it exists only as a run
    # time multiplied by a pump flow rate. Each entity is gated on BOTH keys being read,
    # never assumed — an installation without a pH- pump carries neither, and that same
    # gate is what keeps the two chlorine pumps exclusive without reading `HybrideMode`.
    settings = details.settings
    for key, spec in DERIVED_COUNTER_TYPES.items():
        if spec["source"] not in settings or spec["rate"] not in settings:
            continue
        uid = f"{system_id}_consumption_{key}"
        items.append((uid, KlereoDerivedSensor(coordinator, system_id, key, spec)))

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

    @property
    def available(self) -> bool:
        """Return False once the payload stops carrying this probe.

        Narrows the base property, which only checks the system. A probe that vanishes
        used to leave the entity pinned to its last reading forever (#130).
        """
        return super().available and self._find_my_probe() is not None

    @callback
    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        probe = self._find_my_probe()
        if probe:
            self._update_from_probe(probe)
        super()._handle_coordinator_update()

    def _update_from_probe(self, probe: KlereoProbe):
        """Update state from probe data."""
        value = probe.filtered_value
        if value is None:
            value = probe.direct_value
        self._attr_native_value = value
        attributes = {
            "type": probe.type,
            "status": probe.status,
        }
        references = self._regulations_i_drive()
        if references:
            # Absent rather than empty: an empty list reads as a claim that we looked and
            # found none, which is not what an installation sending no reference fields
            # is telling us.
            attributes["regulation_reference"] = references
        self._attr_extra_state_attributes = attributes

    def _regulations_i_drive(self) -> list[str]:
        """Return the regulation loops this probe is the reference sensor for.

        Always a list. A probe named by two loops has never been measured, and a list
        needs no special path for it — where a string would need a rule invented on the
        spot, the first time it happens, in production.
        """
        system = self.coordinator.data.get(self.system_id)
        if system is None:
            return []
        details = system.details
        driven = []
        for name, index in sorted(details.regulation_probes.items()):
            if index == NO_REFERENCE_PROBE:
                # A normal installation, not an anomaly: the measured payload carries
                # `PressionCapteur: -1` on a pool with no pressure sensor. Warning here
                # would cry wolf on every one of them.
                _LOGGER.debug("Regulation %s has no reference probe", name)
                continue
            if index not in details.probe_index:
                _LOGGER.warning(
                    "Regulation %s names probe %s, which this installation does not report",
                    name, index,
                )
                continue
            if index == self._index:
                driven.append(name)
        return driven

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
        self._attr_native_value = _reading(initial_value)

        # Counters carry a unit and a class; an ordinary regulation parameter carries
        # neither, and giving it a plausible one would be a guess.
        counter = PARAM_COUNTER_TYPES.get(key, {})
        self._attr_native_unit_of_measurement = counter.get("unit")
        self._attr_device_class = counter.get("device_class")
        state_class = counter.get("state_class")
        if state_class:
            self._attr_state_class = SensorStateClass(state_class)

    @callback
    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        system = self._system()
        if system is None:
            return super()._handle_coordinator_update()
        settings = system.details.settings
        if self._key in settings:
            self._attr_native_value = _reading(settings[self._key])
        super()._handle_coordinator_update()


class KlereoDerivedSensor(KlereoEntity, SensorEntity):
    """A product volume computed from a run time and a pump flow rate.

    The only entity on this platform whose value is not on the wire. Klereo sends how long
    the dosing pump ran and how fast it pumps; the litres are upstream's arithmetic
    (`klereo.class.php` l.335-380), and reproducing it here is what answers #54's actual
    request — litres of pH-, not hours of pump.
    """

    def __init__(self, coordinator, system_id, key, spec):
        """Initialize the derived sensor."""
        super().__init__(coordinator, system_id)
        self._key = key
        self._spec = spec

        self._attr_unique_id = f"{system_id}_consumption_{key}"
        self._attr_name = spec["name"]
        self._attr_native_unit_of_measurement = spec["unit"]
        self._attr_device_class = spec["device_class"]
        self._attr_state_class = SensorStateClass(spec["state_class"])
        self._attr_native_value = self._compute()

    @callback
    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        system = self._system()
        if system is None:
            return super()._handle_coordinator_update()
        self._attr_native_value = self._compute()
        super()._handle_coordinator_update()

    def _compute(self):
        """Return the volume, or None when either reading is missing or unreadable.

        None is the honest report. Turning "we cannot read this" into a number would be
        the #105 failure applied to a consumption total, where a plausible-looking litre
        count is exactly what nobody would question.
        """
        system = self.coordinator.data.get(self.system_id)
        if system is None:
            return None
        settings = system.details.settings
        try:
            seconds = float(settings[self._spec["source"]])
            rate = float(settings[self._spec["rate"]])
        except (KeyError, TypeError, ValueError):
            _LOGGER.debug(
                "Cannot compute %s: %s or %s is missing or unreadable",
                self._key, self._spec["source"], self._spec["rate"],
            )
            return None
        return round(seconds * rate / self._spec["divisor"], 2)


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
        system = self._system()
        if system is None:
            return
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
