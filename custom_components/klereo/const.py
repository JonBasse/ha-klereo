"""Constants for the Klereo integration."""

DOMAIN = "klereo"

API_URL_BASE = "https://connect.klereo.fr/php"
API_URL_LOGIN = f"{API_URL_BASE}/GetJWT.php"
API_URL_GET_INDEX = f"{API_URL_BASE}/GetIndex.php"
API_URL_GET_POOL_DETAILS = f"{API_URL_BASE}/GetPoolDetails.php"
API_URL_SET_OUT = f"{API_URL_BASE}/SetOut.php"
API_URL_SET_PARAM = f"{API_URL_BASE}/SetParam.php"

# Default update interval
SCAN_INTERVAL_MINUTES = 5

# Output modes (from Jeedom plugin _OUT_MODE_* constants)
OUT_MODE_MAN = 0
OUT_MODE_TIME_SLOTS = 1
OUT_MODE_TIMER = 2
OUT_MODE_REGUL = 3

# Output states (from Jeedom plugin _OUT_STATE_* constants)
OUT_STATE_OFF = 0
OUT_STATE_ON = 1

# Probe type to sensor metadata mapping (from Jeedom _PROBE_TYPE_* constants)
SENSOR_TYPES = {
    0: {"name": "Technical Room Temperature", "unit": "°C", "device_class": "temperature"},
    1: {"name": "Air Temperature", "unit": "°C", "device_class": "temperature"},
    2: {"name": "Water Level", "unit": "%", "device_class": None},
    3: {"name": "pH", "unit": None, "device_class": None},
    4: {"name": "Redox", "unit": "mV", "device_class": "voltage"},
    5: {"name": "Water Temperature", "unit": "°C", "device_class": "temperature"},
    6: {"name": "Filter Pressure", "unit": "mbar", "device_class": "pressure"},
    10: {"name": "Generic", "unit": "%", "device_class": None},
    11: {"name": "Flow", "unit": "m³/h", "device_class": None},
    12: {"name": "Container Level", "unit": "%", "device_class": None},
    13: {"name": "Cover Position", "unit": "%", "device_class": None},
    14: {"name": "Chlorine", "unit": "mg/L", "device_class": None},
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
