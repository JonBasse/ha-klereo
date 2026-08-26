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

# Outputs whose `newMode` does not carry the output mode. Klereo's documentation says
# newMode is "NON VALABLE POUR LES SORTIES 2,3,4,8,15"; output 4 is handled separately
# because its meaning there IS known (the KlereoTherm mode, #58). For these four it is
# not, so upstream does not reinterpret it either — it refuses to command them below
# professional access (klereo.class.php:1188). See #104.
PRO_ONLY_OUTPUTS = frozenset({2, 3, 8, 15})

# The three containers a setpoint or regulation parameter can arrive in. Measured
# 2026-08-26 (GitHub #57): an installation returns ALL THREE in the same payload, which
# retires the "which one does this install send?" framing of #94 — the precedence there
# arbitrates between three containers of one response, not between installations.
# `models.KlereoPoolDetails.settings` merges them in this order, least-established first,
# so a later entry can only add a key and never overwrite one an install already shows.
SETTING_CONTAINERS = ("ExtraParams", "params", "RegulModes")

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

# KlereoTherm types that can only heat or stop: 0 = no heat pump at all, 1 = heat pump or
# on/off heater, 3 = on/off heating without setpoint. Upstream builds the mode list from
# the same field (klereo.class.php l.929) and offers Auto + Cooling only to 2 (KlereoTherm
# heat pump) and 4 (other heat pump).
#
# 🔴 Written as a positive list of the types KNOWN to be heat-only, which is the INVERSE
# of upstream's `not in [2, 4]`. The two differ exactly on a value we cannot read — absent,
# unparseable, or an integer Klereo has not documented — and there "unknown never bars"
# wins: narrowing on a missing reading would delete a control that works today, while the
# defect it fixes is benign (an option the box accepts and never executes). #124.
HEATER_MODES_WITHOUT_COOLING = frozenset({0, 1, 3})

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


# ── Alerts ──────────────────────────────────────────────────────────────────────────
#
# Klereo returns active alerts in the `alerts` array of `GetIndex` / `GetPoolsDetails`.
# `docs/klereo-api.md` does NOT document them — its field lists are elided — so the whole
# of what follows is ported from the upstream Jeedom plugin (`klereo.class.php` l.517-597),
# cross-checked against the one payload anyone has measured (GitHub #57, @sbdomo,
# 2026-08-26).
#
# Two things that measurement settled, and neither was guessable:
#
#   * the key is ABSENT when there are no alerts, not present and empty. So "no alerts"
#     and "we could not read them" look identical in the payload, and only one of them is
#     a reason to show nothing. The entity is therefore created unconditionally: an alert
#     sensor that disappears when the pool is healthy is worse than one reading 0.
#   * `alertCount` and `len(alerts)` DISAGREE — the reporter's payload carries
#     `alertCount: 0` beside one active alert, and says so ("I don't know why alertcount
#     is 0 and not 1"). Upstream never reads that field either: it computes
#     `count($pool['alerts'])` (l.511). The state is derived from the array; the reported
#     figure is exposed as an attribute so a divergence is visible rather than silent.

# Alert code → label (`klereo.class.php` l.517-568). Codes absent from this table are
# reported by their number rather than mapped to a neighbouring label — upstream does the
# same ("Code alerte inconnu par le plugin"). Gaps (4, 9, 15-20, 24, 27, 32, 33) are the
# upstream table's own; do not fill them.
ALERT_LABELS = {
    0: "No alert",
    1: "Sensor failure",
    2: "Relay configuration problem",
    3: "pH/Redox probes swapped",
    5: "Low batteries",
    6: "Calibration",
    7: "Minimum",
    8: "Maximum",
    10: "Not received",
    11: "Frost protection",
    12: "Unknown alert #12",
    13: "Excess water consumption",
    14: "Water leak",
    21: "Internal memory fault",
    22: "Circulation problem",
    23: "Insufficient filtration schedule",
    25: "High pH, disinfectant ineffective",
    26: "Filtration undersized",
    28: "Regulation stopped",
    29: "Filtration in MANUAL-OFF mode",
    30: "INSTALLATION mode",
    31: "Shock treatment",
    34: "Regulation suspended or disabled",
    35: "Maintenance",
    36: "Daily injection limit reached",
    37: "Multi-sensor failure",
    38: "Electrolyser link failure",
    39: "Daily brominator limit reached",
    40: "Electrolyser",
    41: "Heat pump link failure",
    42: "Inconsistent sensor configuration",
    43: "Electrolyser in safe mode",
    44: "Dosing pump maintenance",
    45: "Learning not performed",
    46: "No analysis water flow",
    47: "Inconsistent cover configuration",
    48: "Filtration not controlled",
    49: "Check the clock",
    50: "Heat pump",
    51: "Heat pump",
    52: "Heat pump",
    53: "Filtration link failure",
    54: "Filtration pump",
    55: "Gen3 or Gen5 multi-sensor missing",
    56: "Filtration state unknown — risk of treatment without filtration",
    57: "Gen3 or Gen4 multi-sensor missing",
    58: "Incorrect pump configuration",
    59: "Communication problem with the consumption metering module",
    60: "Variable-speed pump display locked",
    61: "Heat pump fault",
}

# 🔴 `param` means a DIFFERENT thing per code, and a raw number is wrong most of the time.
# Codes not listed here carry no documented meaning for `param`, so it is not described at
# all rather than described wrongly (`klereo.class.php` l.575-596).
ALERT_PARAM_IS_PROBE = frozenset({1, 7, 8, 10, 36})   # param = CapteurID
ALERT_PARAM_IS_FLOW = frozenset({13, 14})             # param = DebitID
ALERT_PARAM_IS_OUTPUT = frozenset({35})               # param = OutID
ALERT_PARAM_IS_PUMP = frozenset({53})                 # param = PumpID
ALERT_PARAM_IS_ERROR_CODE = frozenset({50, 51, 52, 54, 61})  # ErrCode{E,P,F}X, PumpErrCode
ALERT_PARAM_PREFIXES = {40: "BSVError", 41: "Communication"}
# Code 6 names what is being calibrated; code 5 always means the RFID module, whatever
# `param` carries — upstream ignores it there.
ALERT_PARAM_CALIBRATION = {0: "pH", 1: "Disinfectant"}
