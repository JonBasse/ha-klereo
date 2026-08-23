"""Constants for the Klereo integration."""
import hashlib

DOMAIN = "klereo"


def hash_password(plaintext: str) -> str:
    """Hash a plaintext password with SHA-1 for the Klereo API."""
    return hashlib.sha1(plaintext.encode("utf-8")).hexdigest()

# Default update interval
SCAN_INTERVAL_MINUTES = 5

# Probe types that return binary 0/1 values and should be BinarySensorEntity
BINARY_SENSOR_TYPES = {
    10: {"name": "Generic", "device_class": None},
}

# Probe type to sensor metadata mapping (from Jeedom _PROBE_TYPE_* constants)
# state_class: "measurement" for continuous readings, None for positional/unknown values
SENSOR_TYPES = {
    0: {
        "name": "Technical Room Temperature", "unit": "°C",
        "device_class": "temperature", "state_class": "measurement",
    },
    1: {"name": "Air Temperature", "unit": "°C", "device_class": "temperature", "state_class": "measurement"},
    2: {"name": "Water Level", "unit": "%", "device_class": None, "state_class": "measurement"},
    3: {"name": "pH", "unit": None, "device_class": None, "state_class": "measurement"},
    4: {"name": "Redox", "unit": "mV", "device_class": "voltage", "state_class": "measurement"},
    5: {"name": "Water Temperature", "unit": "°C", "device_class": "temperature", "state_class": "measurement"},
    6: {"name": "Filter Pressure", "unit": "mbar", "device_class": "pressure", "state_class": "measurement"},
    # type 10 "Generic" lives in BINARY_SENSOR_TYPES
    11: {"name": "Flow", "unit": "m³/h", "device_class": None, "state_class": "measurement"},
    12: {"name": "Container Level", "unit": "%", "device_class": None, "state_class": "measurement"},
    13: {"name": "Cover Position", "unit": "%", "device_class": None, "state_class": None},
    14: {"name": "Chlorine", "unit": "mg/L", "device_class": None, "state_class": "measurement"},
}

OUTPUT_NAMES = {
    0: "Lighting",
    1: "Filtration",
    2: "pH Corrector",
    3: "Disinfectant",
    4: "Heating",
    5: "Aux 1",
    6: "Aux 2",
    7: "Aux 3",
    8: "Flocculant",
    9: "Aux 4",
    10: "Aux 5",
    11: "Aux 6",
    12: "Aux 7",
    13: "Aux 8",
    14: "Aux 9",
    15: "Hybrid Disinfectant",
}

# Sentinel setpoint values used by the Klereo API. A setpoint carrying one of these is not
# a value: -2000 means the setpoint is disabled, -1000 that it is unknown. Upstream
# discards both (klereo.class.php l.873-896); exposing them would pin an entity to a
# nonsense reading.
PARAM_SENTINELS = frozenset({-2000, -1000})

# Account access levels, from the upstream plugin (klereo.class.php l.463-471). The API
# gates what a given account may read or write on this value.
ACCESS_READ_ONLY = 5
ACCESS_END_CUSTOMER = 10
ACCESS_ADVANCED_USER = 16
ACCESS_POOL_PROFESSIONAL = 20

# KlereoTherm modes that carry no water setpoint: 0 = no heat pump at all, 3 = an on/off
# heat pump that takes no setpoint. Upstream gates ConsigneEau on HeaterMode not in {0, 3}.
HEATER_MODES_WITHOUT_SETPOINT = frozenset({0, 3})

# Friendly names for setpoint / regulation keys exposed as read-only param sensors.
# Keys in PARAM_TYPES are excluded (they become number entities instead).
PARAM_NAMES = {
    "ModeFiltration": "Filtration Mode",
    "ModeRegulPH": "pH Regulation Mode",
    "ModeRegulRedox": "Redox Regulation Mode",
    "ModeRegulChlore": "Chlorine Regulation Mode",
    "ModeRegulTemp": "Temperature Regulation Mode",
    "ConsignePH": "pH Setpoint",
    "ConsigneRedox": "Redox Setpoint",
    "ConsigneChlore": "Chlorine Setpoint",
    "DureeTimerFiltration": "Filtration Timer Duration",
}

# Writable setpoints exposed as `number` entities.
#   min/max         — fallback bounds, used only when the API sends none
#   min_key/max_key — the API keys carrying the real bounds, preferred over min/max
#   min_access      — the account access level below which the API refuses the write
#   needs_heater    — skip when HeaterMode says the installation has no water setpoint
PARAM_TYPES = {
    "ConsigneEau": {
        "name": "Water Setpoint", "unit": "°C", "min": 10, "max": 40, "step": 0.5,
        "min_key": "EauMin", "max_key": "EauMax",
        "min_access": ACCESS_END_CUSTOMER, "needs_heater": True,
    },
}
