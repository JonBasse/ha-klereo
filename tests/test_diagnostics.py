"""Tests for Klereo diagnostics."""
from unittest.mock import MagicMock

import pytest

from custom_components.klereo.diagnostics import (
    TO_REDACT,
    async_get_config_entry_diagnostics,
)
from custom_components.klereo.models import (
    KlereoPoolDetails,
    KlereoProbe,
    KlereoSystemData,
    KlereoSystemInfo,
)


class TestDiagnostics:
    """Tests for diagnostics output."""

    async def test_returns_config_and_coordinator_data(self):
        """Should include both config_entry and coordinator_data sections."""
        hass = MagicMock()
        entry = MagicMock()
        entry.as_dict.return_value = {
            "data": {"username": "test@example.com", "password": "secret_hash"},
            "options": {},
        }
        coordinator = MagicMock()
        coordinator.data = {
            "SYS1": KlereoSystemData(
                info=KlereoSystemInfo(id_system="SYS1", pool_nickname="My Pool"),
                details=KlereoPoolDetails(),
            )
        }
        hass.data = {"klereo": {entry.entry_id: coordinator}}

        result = await async_get_config_entry_diagnostics(hass, entry)
        assert "config_entry" in result
        assert "coordinator_data" in result

    async def test_redacts_sensitive_fields(self):
        """Password and token fields should be redacted."""
        hass = MagicMock()
        entry = MagicMock()
        entry.as_dict.return_value = {
            "data": {"password": "secret", "jwt": "tok123", "login": "user"},
            "options": {},
        }
        coordinator = MagicMock()
        coordinator.data = {}
        hass.data = {"klereo": {entry.entry_id: coordinator}}

        result = await async_get_config_entry_diagnostics(hass, entry)
        config = result["config_entry"]
        assert config["data"]["password"] == "**REDACTED**"
        assert config["data"]["jwt"] == "**REDACTED**"
        assert config["data"]["login"] == "**REDACTED**"

    def test_to_redact_contains_expected_keys(self):
        """TO_REDACT should include all sensitive field names."""
        assert "password" in TO_REDACT
        assert "jwt" in TO_REDACT
        assert "token" in TO_REDACT
        assert "login" in TO_REDACT


# The identifying fields of a REAL export, measured 2026-08-26 on the Bioul installation
# via `/api/diagnostics/config_entry/{id}`. Values are the shape, not the originals.
MEASURED_RAW = {
    "idSystem": 121170,
    "poolNickname": "Bioul",
    "pin": "0301-2982521-1260",
    "compta": "AR15217",
    "idAddress": 39377,
    "access": 10,
    "PumpType": 7,
}


class TestRedactionCoversWhatWePromise:
    """🔴 Tests that `TO_REDACT` covers what reporters are TOLD it covers.

    This file's other tests check that redaction *works*; these check that it *reaches*.
    The distinction is the whole defect: the previous set redacted the password and left
    `username` — the other half of the same credential — in clear, on an export the
    repository actively asks people to paste into public issues.

    Every field below was seen in clear in a real export. An external reporter had already
    hand-redacted three of them rather than trust the promise (GitHub #57); this class is
    his judgement, written down.
    """

    @staticmethod
    async def _export(raw=None, entry_data=None):
        """Run the real diagnostics function over a payload shaped like a live one."""
        hass = MagicMock()
        entry = MagicMock()
        entry.as_dict.return_value = {
            "data": entry_data or {"username": "jonbasse", "password": "secret"},
            "options": {},
        }
        coordinator = MagicMock()
        coordinator.data = {
            "121170": KlereoSystemData(
                info=KlereoSystemInfo(
                    id_system="121170", pool_nickname="Bioul", raw=dict(raw or MEASURED_RAW)
                ),
                details=KlereoPoolDetails(probes=[KlereoProbe(index=16, type=5, filtered_value=28.25)]),
            )
        }
        hass.data = {"klereo": {entry.entry_id: coordinator}}
        return await async_get_config_entry_diagnostics(hass, entry)

    async def test_redacts_the_account_username(self):
        """🔴 Should redact `username` — the half of the credential the password isn't.

        THE test of this issue. A reporter publishing this on a public tracker hands over
        everything a password-reset or credential-stuffing attempt is missing.
        """
        result = await self._export()

        assert result["config_entry"]["data"]["username"] == "**REDACTED**"
        assert result["config_entry"]["data"]["password"] == "**REDACTED**"

    @pytest.mark.parametrize("key", ["pin", "compta", "idAddress"])
    async def test_redacts_each_identifier_seen_in_a_real_export(self, key):
        """Should redact the box identifier, the customer reference and the address key.

        Parametrised one per field rather than asserted in a batch: a batch that loses a
        field to a typo still passes on the others, which is how a redaction set comes to
        cover less than its docstring claims.
        """
        result = await self._export()

        assert result["coordinator_data"]["121170"]["info"]["raw"][key] == "**REDACTED**"

    async def test_does_not_redact_what_makes_the_export_useful(self):
        """🔴 Negative control: over-redacting breaks the tool we are making safe.

        An export redacted into uselessness is one nobody pastes, and the export is what
        unblocks these issues. `idSystem` keys the data and ties to no person;
        `poolNickname` is user-chosen and already visible in every entity name they paste
        elsewhere, so hiding it here would be false reassurance rather than safety.
        """
        result = await self._export()
        raw = result["coordinator_data"]["121170"]["info"]["raw"]

        assert raw["idSystem"] == 121170
        assert raw["poolNickname"] == "Bioul"
        assert raw["access"] == 10
        assert raw["PumpType"] == 7

    async def test_measurement_data_survives_redaction(self):
        """Absurdity control: the probe readings are the point of the export."""
        result = await self._export()
        probes = result["coordinator_data"]["121170"]["details"]["probes"]

        assert probes[0]["filtered_value"] == 28.25
        assert probes[0]["type"] == 5
