"""Diagnostics support for Klereo."""
from dataclasses import asdict

from homeassistant.components.diagnostics import async_redact_data
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


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator_data = {
        sys_id: asdict(system_data)
        for sys_id, system_data in coordinator.data.items()
    }
    return {
        "config_entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "coordinator_data": async_redact_data(coordinator_data, TO_REDACT),
    }
