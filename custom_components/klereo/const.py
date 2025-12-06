"""Constants for the Klereo integration."""

DOMAIN = "klereo"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

API_URL_BASE = "https://connect.klereo.fr/php"
API_URL_LOGIN = f"{API_URL_BASE}/GetJWT.php"
API_URL_GET_INDEX = f"{API_URL_BASE}/GetIndex.php"
API_URL_GET_POOL_DETAILS = f"{API_URL_BASE}/GetPoolDetails.php"
API_URL_SET_OUT = f"{API_URL_BASE}/SetOut.php"
API_URL_SET_PARAM = f"{API_URL_BASE}/SetParam.php"

# Default update interval
SCAN_INTERVAL_MINUTES = 5

SENSOR_TYPES = {
    1: {"name": "Water Temperature", "unit": "°C", "device_class": "temperature"},
    2: {"name": "External Temperature", "unit": "°C", "device_class": "temperature"},
    3: {"name": "pH", "unit": None, "device_class": None},
    4: {"name": "Redox", "unit": "mV", "device_class": "voltage"},
    5: {"name": "Air Temperature", "unit": "°C", "device_class": "temperature"},
    16: {"name": "Air Temperature", "unit": "°C", "device_class": "temperature"},
}
