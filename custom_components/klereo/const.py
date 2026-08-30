"""Constants for the Klereo integration."""
import hashlib

DOMAIN = "klereo"


def hash_password(plaintext: str) -> str:
    """Hash a plaintext password with SHA-1 for the Klereo API."""
    return hashlib.sha1(plaintext.encode("utf-8")).hexdigest()

# Update interval, in minutes.
#
# 🔴 Klereo refreshes server-side every 10 minutes and threatens to ban faster pollers —
# their own API documentation, relayed by the reporter of GitHub #58 (2026-08-28). The
# verbatim quote is in `docs/klereo-api.md`.
#
# Two things follow, and the second is the one that gets forgotten:
#
#   * polling faster buys NOTHING — above one call per 10 minutes the server returns the
#     same payload, so there is no freshness/risk trade-off to arbitrate here;
#   * the ban would land on the USER's Klereo account, costing them the integration AND
#     their normal access to the service, for something they never asked for.
#
# The floor therefore binds on READ (`coordinator.py`), not only on the options form:
# `scan_interval` is a persisted option and `__init__.py` serves whatever is stored, so an
# install configured before this existed would keep hammering the API with no signal.
# Forgejo #139.
SCAN_INTERVAL_MINUTES = 10
SCAN_INTERVAL_MIN_MINUTES = 10

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

# The three containers a setpoint or regulation parameter can arrive in.
#
# Two installations are measured, and they DISAGREE — which is the fact this comment
# exists to carry, because an earlier version of it stated a rule that only one of them
# supports (#138):
#
#   * GitHub #57, @sbdomo, 2026-08-26 — all three present in the same payload.
#   * Bioul, 2026-08-27, diagnostics export of 1.9.0 — `RegulModes` 4 keys, `params` 116,
#     `ExtraParams` **0**.
#
# What that settles, and what it does NOT:
#
#   * The PRECEDENCE question of #94 is retired: within one response the three are merged
#     below, least-established first, so a later entry can only ADD a key and never
#     overwrite one an install already shows. An empty container adds nothing and breaks
#     nothing, so no behaviour is wrong on either installation.
#   * The COVERAGE question of #94 is NOT retired. For any key upstream reads only from
#     `ExtraParams` — the hybrid chlorine counter `HybChl_*` (`klereo.class.php` l.356) is
#     one — an installation with an empty `ExtraParams` cannot produce it, and nothing in
#     this repository distinguishes "no hybrid pump" from "container not sent". Those keys
#     remain untested on every installation we can reach.
#
# ⚠️ And we cannot tell WHICH of the two Bioul returns: `models.py` does
# `dict(data.get("ExtraParams", {}))`, so an absent key and a present-but-empty one are
# indistinguishable after parsing. Left that way deliberately — a field nobody reads is
# noise, and the question is not currently blocking anything.
SETTING_CONTAINERS = ("ExtraParams", "params", "RegulModes")

# Which probe drives each regulation loop. Klereo documents these four top-level fields in
# `docs/klereo-api.md`, each carrying an index into `probes[]`; a pool can hold several
# temperature probes and nothing else says which one the box regulates on. Confirmed on a
# live `GetIndex` in GitHub #57 (2026-08-26).
REGULATION_REFERENCE_FIELDS = {
    "EauCapteur": "water_temperature",
    "pHCapteur": "ph",
    "TraitCapteur": "disinfectant",
    "PressionCapteur": "pressure",
}

# 🔴 `-1` means "this regulation has no reference probe" — the measured payload carries
# `PressionCapteur: -1` on a pool with no pressure sensor. It is NOT `PARAM_SENTINELS`:
# those mark a disabled or unknown SETPOINT, and a setpoint of -1 is a real value. Reusing
# them here would be a false friend that happens to work.
NO_REFERENCE_PROBE = -1

# Sentinel setpoint values used by the Klereo API. A setpoint carrying one of these is not
# a value: -2000 means the setpoint is disabled, -1000 that it is unknown. Upstream
# discards both (klereo.class.php l.873-896); exposing them would pin an entity to a
# nonsense reading.
PARAM_SENTINELS = frozenset({-2000, -1000})

# Account access levels, from the upstream plugin (klereo.class.php l.463-471). The API
# gates what a given account may read or write on this value.
# The probe type carrying the pool water temperature. Named rather than spelled `5` at the
# call site: #121 records what an inverted probe-type mapping costs once it ships.
WATER_TEMPERATURE_PROBE_TYPE = 5

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
#
# A key in PARAM_TYPES is excluded here only when its `number` is ACTUALLY offered — see
# `entity.is_setpoint_offered`, which both platforms share. Excluding on the key alone
# would delete a reading whenever a write guard bites: an account at access 10 would lose
# the pH, Redox and chlorine setpoints it reads today and gain nothing writable. #128.
#
# 🔴 `ConsigneEau` is deliberately NOT here, and its absence is load-bearing. It has never
# been a sensor, so the fallback must not invent one — and on both installations measured
# so far it carries the `-2000` sentinel, which would surface as a `Water Setpoint` reading
# -2000: precisely the pinned-nonsense control 1.9.0 refused to create. The three setpoints
# below WERE sensors before they became writable, so keeping theirs deletes nothing, even
# at a sentinel. The rule is "never delete", not "always fall back".
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


# ── Consumption counters (#54) ──────────────────────────────────────────────────────
#
# Klereo counts what each piece of equipment has DONE, in seconds, in `params` — and for
# the hybrid chlorine pump in `ExtraParams`, which is where upstream reads it
# (`klereo.class.php` l.356). Measured three times: named by an external reporter reading
# his own diagnostics export (GitHub #54, 2026-06-17), then on live payloads from the
# Bioul installation and from GitHub #55, both 2026-08-26.
#
# 🔴 The keys are admitted BY NAME, never by a `*_TodayTime` suffix rule. A suffix rule
# would look identical on all three payloads and then admit whatever Klereo adds next,
# sight unseen — the mistake #94 exists to record. Every name below is one upstream reads.
COUNTER_EQUIPMENT = {
    "Filtration": "Filtration",
    "PHMinus": "pH-",
    "ElectroChlore": "Liquid Chlorine",
    "HybChl": "Hybrid Chlorine",
    "Chauff": "Heating",
}
_COUNTER_PERIODS = {"TodayTime": "Today", "TotalTime": "Total"}

# Run time, exposed RAW in seconds rather than divided by 3600 the way upstream does:
# the seconds are what the wire carries, Home Assistant renders a duration by itself, and
# a sensor whose value equals the payload is one a bug report can quote.
PARAM_COUNTER_TYPES = {
    f"{prefix}_{suffix}": {
        "name": f"{label} Time {period}",
        "unit": "s", "device_class": "duration", "state_class": "total_increasing",
    }
    for prefix, label in COUNTER_EQUIPMENT.items()
    for suffix, period in _COUNTER_PERIODS.items()
}

# Chlorine produced by electrolysis. Upstream divides by 1000 and labels the result `g`,
# so the wire carries milligrams — exposed raw, for the same reason as the seconds above.
PARAM_COUNTER_TYPES["Elec_GramDone"] = {
    "name": "Electrolysis Chlorine Produced Today",
    "unit": "mg", "device_class": "weight", "state_class": "total_increasing",
}

# The counters reach the `sensor` platform through the same curated `PARAM_NAMES` gate as
# every other `params` key — the gate is what keeps 113 keys from becoming 113 entities.
# Their names come from `PARAM_COUNTER_TYPES` so there is one source, not two.
PARAM_NAMES.update({key: spec["name"] for key, spec in PARAM_COUNTER_TYPES.items()})

# Product consumption — what the reporter of #54 actually asked for, and the one thing
# here the API does not send. Klereo carries a run time and a pump flow rate; upstream
# multiplies them (`klereo.class.php` l.335-380):
#
#     today = <Equipment>_TodayTime × <rate> / 36      → mL
#     total = <Equipment>_TotalTime × <rate> / 36000   → L
#
# That asymmetry is the rule for the whole platform: we compute only what is not on the
# wire. Both chlorine pumps are metered by the single `Chlore_Debit`.
#
# 🔴 Each entity is gated on BOTH its keys being present, which is a reading and not a
# guess: an installation without a pH- pump carries neither the counter nor the rate. It
# is also what keeps the two chlorine pumps exclusive without reading `HybrideMode` —
# upstream branches on that flag, but the payload already says which pump exists, and a
# second source for a fact we can read directly is a drift waiting to happen.
DERIVED_COUNTER_TYPES = {
    f"{prefix}_{period}": {
        "name": f"{label} Consumption {period}",
        "source": f"{prefix}_{suffix}",
        "rate": rate,
        "divisor": divisor,
        "unit": unit,
        "device_class": "volume",
        "state_class": "total_increasing",
    }
    for prefix, label, rate in (
        ("PHMinus", "pH-", "PHMinus_Debit"),
        ("ElectroChlore", "Liquid Chlorine", "Chlore_Debit"),
        ("HybChl", "Hybrid Chlorine", "Chlore_Debit"),
    )
    for suffix, period, divisor, unit in (
        ("TodayTime", "Today", 36, "mL"),
        ("TotalTime", "Total", 36000, "L"),
    )
}

# Writable setpoints exposed as `number` entities.
#   min/max         — fallback bounds, used only when the API sends none
#   min_key/max_key — the API keys carrying the real bounds, preferred over min/max
#   min_access      — the account access level below which the API refuses the write
#   needs_heater    — skip when HeaterMode says the installation has no water setpoint
#   needs_ph_mode   — skip when pHMode says this installation regulates no pH
#
# 🔴 Upstream writes EXACTLY these four and no others (`klereo.class.php` l.869-897, the
# only four `createCmdAction` calls that carry a setpoint). `setParam()` (l.1237) takes an
# arbitrary `$_param`, so the API may well accept more — but every extra name would be a
# guess, which is the fault #94 exists to record. The "pH drift adjustment" asked for in
# GitHub #54 appears NOWHERE upstream; it is absent on purpose, not by oversight. #128.
PARAM_TYPES = {
    "ConsigneEau": {
        "name": "Water Setpoint", "unit": "°C", "min": 10, "max": 40, "step": 0.5,
        "min_key": "EauMin", "max_key": "EauMax",
        "min_access": ACCESS_END_CUSTOMER, "needs_heater": True,
    },
    # No unit: the pH probe carries none either (SENSOR_TYPES[3]), and pH is a bare number.
    # The 0-14 fallback is the total physical range rather than a plausible pool window —
    # it is only ever used by a payload carrying no pHMin/pHMax, and a narrow guess there
    # would clamp a real setpoint. Upstream has no fallback at all: it reads the two keys
    # unconditionally and lets PHP yield null when they are absent.
    "ConsignePH": {
        "name": "pH Setpoint", "unit": None, "min": 0, "max": 14, "step": 0.1,
        "min_key": "pHMin", "max_key": "pHMax",
        "min_access": ACCESS_ADVANCED_USER, "needs_ph_mode": True,
    },
    # ⚠️ The 0-1000 mV fallback is a CONVENTION for ORP probes, not a measurement and not
    # an upstream value. Same role as pH's: permissive, and only reachable without bounds.
    "ConsigneRedox": {
        "name": "Redox Setpoint", "unit": "mV", "min": 0, "max": 1000, "step": 1,
        "min_key": "OrpMin", "max_key": "OrpMax",
        "min_access": ACCESS_ADVANCED_USER,
    },
    # 🔴 No min_key/max_key ON PURPOSE. Upstream hard-codes 0-5 mg/L here (l.894-896) and
    # reads no bounds keys for chlorine — unlike the other three. Inventing a
    # `ChloreMin`/`ChloreMax` pair to make the table uniform would be a guessed wire name.
    "ConsigneChlore": {
        "name": "Chlorine Setpoint", "unit": "mg/L", "min": 0, "max": 5, "step": 0.1,
        "min_access": ACCESS_ADVANCED_USER,
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
