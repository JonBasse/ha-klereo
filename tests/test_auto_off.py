"""Tests for the automatic-off timer — Klereo's « Temps minuterie » (#162).

`SetAutoOff.php` was attested only by the upstream Jeedom plugin until 2026-09-08, when a
two-stage probe on Bioul measured it: a call naming no output answered
`{"status":"error","detail":"Mauvais délais"}` — a route that does not exist does not
*validate* an `offDelay`, it 404s — and an idempotent rewrite of `240 → 240` on output 0
answered `cmdID 4399790` then `status: 9, detail: "Ok"` on `CommandStatus`, from an account
at `access: 10`. The relevé is in `docs/klereo-api.md` § *Poser un délai d'extinction
automatique*.

⚠️ Two things stay UNMEASURED and no test here asserts either of them: what `offDelay: 0`
does, and what the timer means on an output that is not in Manual mode.
"""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.klereo.api import API_URL_SET_AUTO_OFF, KlereoApi
from custom_components.klereo.const import AUTO_OFF_MAX_MINUTES, AUTO_OFF_MIN_MINUTES
from custom_components.klereo.coordinator import KlereoCoordinator
from custom_components.klereo.models import (
    KlereoOutput,
    KlereoPoolDetails,
    KlereoSystemData,
    KlereoSystemInfo,
)
from custom_components.klereo.number import KlereoAutoOffNumber, _extract_numbers

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestTheModelCarriesTheDelay:
    """`offDelay` reaches the platforms through the typed model, never a raw dict.

    ⚠️ #145 REFUSED to widen `KlereoOutput` — but it refused widening it *to make fields
    visible*, which the raw diagnostics export already does. A field is added here because
    a feature READS it, which is the other justification, and the coordinator returns typed
    models rather than raw API dicts (`CLAUDE.md`).
    """

    def test_off_delay_is_parsed(self):
        output = KlereoOutput.from_dict({"index": 1, "offDelay": 5})
        assert output.off_delay == 5

    def test_an_absent_off_delay_stays_none_rather_than_zero(self):
        """🔴 `0` is not a reading. Defaulting to it would invent a timer on every output
        whose payload carries none, and `0` is precisely the value nobody has measured."""
        output = KlereoOutput.from_dict({"index": 1})
        assert output.off_delay is None


class TestTheWire:
    async def test_set_auto_off_posts_the_measured_payload(self):
        api = KlereoApi("u", "h", MagicMock())
        api._request_with_retry = AsyncMock(return_value={"status": "ok"})

        await api.set_auto_off("121170", 0, 240)

        args, kwargs = api._request_with_retry.call_args
        assert args == ("POST", API_URL_SET_AUTO_OFF)
        assert kwargs["data"] == {
            "poolID": "121170",
            "outIdx": 0,
            "offDelay": 240,
            "comMode": 1,
        }

    def test_the_url_is_the_measured_one(self):
        assert API_URL_SET_AUTO_OFF == "https://connect.klereo.fr/php/SetAutoOff.php"


@pytest.fixture
def mock_api():
    api = AsyncMock(spec=KlereoApi)
    api.set_auto_off.return_value = {"status": "ok", "response": [{"cmdID": 4399790}]}
    return api


@pytest.fixture
def coordinator(mock_api, monkeypatch):
    monkeypatch.setattr("custom_components.klereo.coordinator.asyncio.sleep", AsyncMock())
    coord = KlereoCoordinator.__new__(KlereoCoordinator)
    coord.api = mock_api
    coord.hass = MagicMock()
    coord.logger = MagicMock()
    coord.name = "klereo"
    coord.update_interval = None
    coord._listeners = {}
    coord.data = {}
    coord.last_update_success = True
    coord.async_request_refresh = AsyncMock()
    return coord


class TestTheWriteIsConfirmed:
    """🔴 A queued command is not a result. `status 13` reads exactly like success on the
    wire, so the verdict comes from `CommandStatus` — never from the HTTP 200 (#95)."""

    async def test_a_successful_write_is_confirmed_then_refreshed(self, coordinator, mock_api):
        mock_api.command_status.return_value = {"status": "ok", "response": 9}

        await coordinator.async_set_auto_off("SYS1", 0, 240)

        mock_api.set_auto_off.assert_awaited_once_with("SYS1", 0, 240)
        mock_api.command_status.assert_awaited_once_with(4399790)
        coordinator.async_request_refresh.assert_awaited_once()

    async def test_a_rejection_is_raised_rather_than_reported_as_a_success(
        self, coordinator, mock_api
    ):
        mock_api.command_status.return_value = {"status": "ok", "response": 13}

        with pytest.raises(HomeAssistantError, match="insufficient rights"):
            await coordinator.async_set_auto_off("SYS1", 0, 240)


def _details(*outs):
    outputs = list(outs)
    return KlereoPoolDetails(
        outs=outputs,
        output_index={o.index: o for o in outputs},
    )


@pytest.fixture
def entity_coordinator():
    coord = MagicMock()
    coord.last_update_success = True
    coord.async_set_auto_off = AsyncMock()
    coord.data = {
        "SYS1": KlereoSystemData(
            info=KlereoSystemInfo(id_system="SYS1", pool_nickname="My Pool"),
            details=_details(
                KlereoOutput(index=1, off_delay=5),
                KlereoOutput(index=9, off_delay=240),
            ),
        )
    }
    return coord


class TestWhichOutputsGetATimer:
    def test_one_entity_per_output_that_carries_the_field(self, entity_coordinator):
        details = entity_coordinator.data["SYS1"].details
        uids = [uid for uid, _ in _extract_numbers(entity_coordinator, "SYS1", details)]
        assert "SYS1_auto_off_1" in uids
        assert "SYS1_auto_off_9" in uids

    def test_an_output_without_off_delay_gets_NOTHING(self, entity_coordinator):
        """🔴 Not an entity at `0`, not a fallback. The five outputs of Bioul all carry the
        field, but nothing says that is universal — `plans` already does not (#128/#135/#138)."""
        details = _details(KlereoOutput(index=1), KlereoOutput(index=9, off_delay=240))
        uids = [uid for uid, _ in _extract_numbers(entity_coordinator, "SYS1", details)]
        assert "SYS1_auto_off_1" not in uids
        assert "SYS1_auto_off_9" in uids


class TestTheTimerEntity:
    def test_it_is_named_for_what_it_is_and_bounded_where_it_was_declared(
        self, entity_coordinator
    ):
        number = KlereoAutoOffNumber(
            entity_coordinator, "SYS1", KlereoOutput(index=1, off_delay=5)
        )
        assert number._attr_name == "Filtration Auto-Off Timer"
        assert number._attr_unique_id == "SYS1_auto_off_1"
        assert number._attr_native_unit_of_measurement == "min"
        assert number._attr_native_min_value == 1
        assert number._attr_native_max_value == 600
        assert number._attr_native_step == 1
        assert number._attr_native_value == 5

    def test_an_unnamed_output_still_gets_a_legible_name(self, entity_coordinator):
        number = KlereoAutoOffNumber(
            entity_coordinator, "SYS1", KlereoOutput(index=99, off_delay=5)
        )
        assert number._attr_name == "Output 99 Auto-Off Timer"

    async def test_setting_it_routes_through_the_coordinator(self, entity_coordinator):
        number = KlereoAutoOffNumber(
            entity_coordinator, "SYS1", KlereoOutput(index=1, off_delay=5)
        )
        number.async_write_ha_state = MagicMock()

        await number.async_set_native_value(30.0)

        assert number._attr_native_value == 30
        entity_coordinator.async_set_auto_off.assert_awaited_once_with("SYS1", 1, 30)

    async def test_the_written_delay_is_an_INTEGER_on_the_wire(self, entity_coordinator):
        """Home Assistant hands `async_set_native_value` a float; `offDelay` is an int
        field, and `30.0` is not the value the probe measured going over the wire."""
        number = KlereoAutoOffNumber(
            entity_coordinator, "SYS1", KlereoOutput(index=1, off_delay=5)
        )
        number.async_write_ha_state = MagicMock()

        await number.async_set_native_value(30.0)

        (_, _, sent), _ = entity_coordinator.async_set_auto_off.call_args
        assert isinstance(sent, int)

    def test_a_refresh_reads_the_new_delay_back(self, entity_coordinator):
        number = KlereoAutoOffNumber(
            entity_coordinator, "SYS1", KlereoOutput(index=1, off_delay=5)
        )
        number.async_write_ha_state = MagicMock()
        entity_coordinator.data["SYS1"].details.output_index[1].off_delay = 42

        number._handle_coordinator_update()

        assert number._attr_native_value == 42
        assert number.available is True

    def test_an_output_that_leaves_the_payload_makes_the_entity_unavailable(
        self, entity_coordinator
    ):
        """Narrowed like the switch's: an output that vanishes must not leave the timer
        pinned to its last reading forever (#130)."""
        number = KlereoAutoOffNumber(
            entity_coordinator, "SYS1", KlereoOutput(index=1, off_delay=5)
        )
        number.async_write_ha_state = MagicMock()
        entity_coordinator.data["SYS1"].details = _details(
            KlereoOutput(index=9, off_delay=240)
        )

        number._handle_coordinator_update()

        assert number.available is False
        assert number._attr_native_value == 5


class TestTheDocumentationAgreesWithTheConstants:
    """The bounds are in three places — upstream's declaration, `const.py`, and `README.md`
    — and a README drifting behind the constant is what invites someone to "fix" it back.
    Same instrument as `test_scan_interval.py` and `test_button.py`.
    """

    def test_the_readme_states_the_declared_bounds(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

        assert f"{AUTO_OFF_MIN_MINUTES} to {AUTO_OFF_MAX_MINUTES}" in readme

    def test_the_readme_says_the_unit_is_minutes(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

        assert "Auto-Off Timer" in readme
        assert "**minutes**" in readme

    def test_the_readme_states_that_a_timerless_output_gets_NOTHING(self):
        """The user-facing half of the rule of #128/#135/#138: an absent entity has to be
        legible as a decision, or it reads as a bug and gets "fixed" into existence."""
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

        assert "no** timer gets **no entity" in readme

    def test_the_readme_declares_the_two_UNMEASURED_questions(self):
        """🔴 The load-bearing one. Both open questions are unknowns, not features, and an
        entity that shows a timer without saying so invites the user to assume it fires on
        a regulated output. Silence would be the claim."""
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

        assert "not in Manual mode" in readme
        assert "What `0` means" in readme
