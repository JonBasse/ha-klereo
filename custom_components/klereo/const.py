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
