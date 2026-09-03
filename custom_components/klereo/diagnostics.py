"""Diagnostics support for Klereo."""
from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.components.diagnostics.const import REDACTED
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import DOMAIN

# 🔴 This set is a SECURITY claim, not a convenience. The repository asks reporters to
# paste diagnostics into PUBLIC issues on the strength of "credentials are redacted
# automatically" — so anything this set misses is published by someone doing as they were
# told. Measured 2026-08-26 on a real export: the previous set covered the password and
# left `username` — the other half of that credential — in clear, beside the Klereo box
# `pin` and the customer reference `compta`.
#
# An external reporter had already judged this correctly on his own: pasting a payload in
# GitHub #57, he hand-redacted `pin`, `compta` and the pool nickname to `XXX` rather than
# trust the promise. His judgement is what this set now encodes.
TO_REDACT = {
    CONF_PASSWORD,
    CONF_USERNAME,
    "jwt",
    "token",
    "login",
    "pin",       # the Klereo box identifier
    "compta",    # Klereo's customer account reference
    "idAddress",  # key of the installation address
    "podSerial",
    "Address",
    "emailNotify",
}

# ⚠️ Deliberately NOT redacted, because an export redacted into uselessness is one nobody
# pastes — and the export is what unblocks these issues:
#   * `idSystem`     — the key of the data dict, and tied to no person;
#   * `poolNickname` — user-chosen, and already visible in every entity name they paste
#                      elsewhere, so hiding it here would be false reassurance;
#   * probes, outs, `params`, `RegulModes` — precisely what we ask to see.
#
# The verdicts below are the same judgement extended to the five keys of the raw
# `GetPoolDetails` payload that #145 added to the export and that nobody had ever ruled
# on. A key nobody has judged is not a safe key — that is the fault of #122, where
# `username` walked past the filter because nobody had enumerated what the object
# actually held.
#
#   * `device`   — NOT redacted. `docs/klereo-api.md` documents it as "index du bassin
#                  dans le POD (num)" and GitHub #57 measured it at `0`. An ordinal that
#                  says nothing without `podSerial`, which is redacted; hiding it would
#                  hide which pool of a multi-pool POD an export describes.
#   * `idLinked` — NOT redacted, on exactly the ground `idSystem` is not: an internal
#                  Klereo key naming another system, tied to no person. Measured `None`
#                  in GitHub #57. ⚠️ It is NOT `idAddress`, the key of the postal
#                  address, which IS redacted — the names are close and the verdicts are
#                  opposite.
#   * `plans`    — NOT redacted. The one of the five whose contents are MEASURED: upstream
#                  reads it as a list of `{index, plan64}`, the base64 time-slot programme
#                  of an output (`klereo.class.php:1095`). It says when equipment runs,
#                  not who owns it, and the same schedule is already visible through the
#                  `select` entities. It is also what a time-slot feature would read.
#   * `register` — SUMMARISED, and now for a MEASURED reason. See the block below: the
#                  guess ("a registration record, which is where an order reference would
#                  live") was right, and the measurement found something worse than the
#                  guess.
#   * `podinfo`  — NOT redacted since #147. Measured on two installations; the verdict and
#                  the arithmetic that settles it are in the block below.
#
# 🔴 The two containers were summarised together for one shared reason — "nobody has
# measured them" — and the measurement SPLIT them. Bioul, 2026-09-03, both containers read
# straight off `GetPoolDetails`; @nopbop's export of 2026-09-02 is the second installation
# and carries the same four `podinfo` keys.
#
#   `podinfo` — four keys, and all four are INTEGERS: `app`, `pingFail`, `pingSent`,
#               `pongRx`. The doubt was entirely about `app`, whose name — unlike the three
#               ping counters — does not imply its type; a string there could have held a
#               build id, a serial or a MAC. It is an int in the low hundreds, sitting
#               beside two ping counters in the ten thousands. No integer of that shape
#               identifies a person or a box, and the same reasoning that keeps `device` in
#               clear applies: an ordinal is useless without `podSerial`, which is redacted.
#
#   `register` — four keys, two of them already in TO_REDACT (`compta`, `pin`) and two not
#               (`lastUpdate`, a registration epoch; `proID`, the installer's id).
#
#               🔴 AND THIS IS WHY IT STAYS SUMMARISED. `proID` is the LAST SEGMENT OF
#               `pin`. The box pin is dash-delimited and its final field is the proID
#               verbatim, so redacting `pin` by name while publishing `proID` beside it
#               hands out a fragment of the value just blanked.
#
#               That is the defect of #154 in a third shape. There, a value escaped under
#               a different NAME (`title`, `unique_id`). Here it escapes as a SUBSTRING —
#               and a filter that matches on key names is structurally unable to see it,
#               however complete its list of names becomes. Per-key redaction looks like
#               the more rigorous treatment and is the one that leaks; the container-level
#               summary is what actually holds.
#
#               ⚠️ So do not "improve" this by dropping `register` from the set on the
#               grounds that `compta` and `pin` are individually covered. They are. That
#               is not sufficient, and the reason is arithmetic, not policy.
UNJUDGED_CONTAINERS = {"register"}

# 🔴 The ENVELOPE, one level ABOVE everything judged so far. #122 and #147 both asked
# "what is inside `data`?"; nobody had asked the same question of the object that WRAPS
# it, and `entry.as_dict()` puts fifteen siblings beside `data` — two of which carry the
# account identifier under a different NAME, which is all `async_redact_data` matches on:
#
#     config_flow.py:42   title      = data[CONF_USERNAME]                   verbatim
#     config_flow.py:63   unique_id  = data[CONF_USERNAME].strip().lower()
#
# So `CONF_USERNAME` in TO_REDACT blanks `data.username` and publishes the same string
# twice over. That is what shipped in 1.13.0 — the release that invited every reporter to
# attach an export — and an external reporter found it in the first one he sent
# (GitHub #58, 2026-09-02). Third time in this file that a value walked past the filter
# under a name nobody had enumerated.
#
# ⚠️ These two are NOT added to TO_REDACT. That set recurses on key names at every depth,
# and `title` is a word Klereo could plausibly use inside a payload we DO want to read;
# blanking it everywhere would trade this leak for a blind spot. The defect is in the
# envelope, so the remedy is applied to the envelope and nowhere else.
ENVELOPE_IDENTITY = {"title", "unique_id"}

# The other fourteen keys, judged one by one against `ConfigEntry.as_dict()` as measured on
# homeassistant 2026.7.3. A key absent from BOTH sets is summarised to its shape rather
# than published — because the lesson of #122, #147 and #58 is that the next leak arrives
# as a field nobody has ruled on, and a Home Assistant release can add one without us
# noticing. Silence must fail closed.
#
#   * `entry_id`, `domain`, `version`, `minor_version`, `source`, `disabled_by`,
#     `created_at`, `modified_at`, `pref_disable_new_entities`, `pref_disable_polling`
#              — NOT redacted. Integration-level facts and a random UUID, tied to no
#                person. Same ground as `idSystem` above.
#   * `data`, `options`
#              — NOT redacted HERE. They are what TO_REDACT and UNJUDGED_CONTAINERS
#                already walk, and that walk still runs over them unchanged.
#   * `discovery_keys`, `subentries`
#              — SUMMARISED. Both are empty on every Klereo entry (the integration is
#                `config_flow`-only, declares no discovery in `manifest.json`, and creates
#                no subentry), so nobody has ever seen one carry anything. Unmeasured is
#                unjudged: they get shapes, not values, exactly like `register`.
ENVELOPE_JUDGED_SAFE = {
    "created_at",
    "data",
    "disabled_by",
    "domain",
    "entry_id",
    "minor_version",
    "modified_at",
    "options",
    "pref_disable_new_entities",
    "pref_disable_polling",
    "source",
    "version",
}


def _redact_envelope(entry_dict: Mapping[str, Any]) -> dict:
    """Blank the identifier-bearing envelope keys, summarise every unjudged one.

    Applied at the TOP LEVEL ONLY, and before anything else touches the object: the
    security claim must not depend on a later pass, for the same reason the comment in
    `async_get_config_entry_diagnostics` gives.
    """
    redacted = {}
    for key, value in entry_dict.items():
        if key in ENVELOPE_IDENTITY:
            redacted[key] = REDACTED
        elif key in ENVELOPE_JUDGED_SAFE:
            redacted[key] = value
        else:
            redacted[key] = f"{REDACTED} — never judged; {_shape_of(value)}"
    return redacted


def _shape_of(value: Any) -> str:
    """Describe a value by its KEYS and size, never by its contents."""
    if isinstance(value, Mapping):
        return f"dict, keys: [{', '.join(sorted(str(key) for key in value))}]"
    if isinstance(value, list):
        keys = sorted({str(k) for item in value if isinstance(item, Mapping) for k in item})
        shape = f"list of {len(value)} items"
        return f"{shape}, keys: [{', '.join(keys)}]" if keys else shape
    return type(value).__name__


def _summarise_unjudged(data: Any) -> Any:
    """Replace every unjudged container with its shape, at any depth.

    🔴 Why a shape and not a plain `**REDACTED**`. Blanking the two containers outright
    would be safe and would also recreate, one level down, the exact blind spot #145 is
    about: nobody could ever judge them from an export, so the only way out would be
    another direct API call with the owner's credentials — the thing this issue exists to
    make unnecessary. Naming the keys without publishing a single value costs nothing and
    lets the NEXT export anyone pastes settle the question.

    This runs over the WHOLE export rather than over the raw payload alone. A rule applied
    at one address is a rule that misses the next address, which is the shape of the
    defect being fixed here.
    """
    if isinstance(data, list):
        return [_summarise_unjudged(item) for item in data]
    if not isinstance(data, Mapping):
        return data
    summarised = {}
    for key, value in data.items():
        if key in UNJUDGED_CONTAINERS:
            summarised[key] = f"{REDACTED} — never judged; {_shape_of(value)}"
        elif isinstance(value, Mapping | list):
            summarised[key] = _summarise_unjudged(value)
        else:
            summarised[key] = value
    return summarised


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator_data = {
        sys_id: asdict(system_data)
        for sys_id, system_data in coordinator.data.items()
    }
    # `_redact_envelope` and `async_redact_data` both run FIRST and unconditionally, so
    # the security claim never depends on the pass below: key names are what all three
    # walks match on, and summarising a value cannot change the name above it.
    return {
        "config_entry": _summarise_unjudged(
            async_redact_data(_redact_envelope(entry.as_dict()), TO_REDACT)
        ),
        "coordinator_data": _summarise_unjudged(
            async_redact_data(coordinator_data, TO_REDACT)
        ),
    }
