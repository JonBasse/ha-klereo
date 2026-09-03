"""Tests for Klereo diagnostics."""
from unittest.mock import MagicMock

import pytest

from custom_components.klereo.diagnostics import (
    ENVELOPE_IDENTITY,
    ENVELOPE_JUDGED_SAFE,
    TO_REDACT,
    UNJUDGED_CONTAINERS,
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
    "pin": "0000-0000000-0000",
    "compta": "XX00000",
    "idAddress": 99999999,
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
            "data": entry_data or {"username": "ExampleUser", "password": "secret"},
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


# ---------------------------------------------------------------------------
# #145 — the raw `GetPoolDetails` payload
# ---------------------------------------------------------------------------

# One `outs[]` element, measured 2026-08-30 on the Bioul installation with the OWNER's
# own credentials — the direct API call #145 exists to make unnecessary. Eleven keys, of
# which `KlereoOutput` parses four; `realStatus` is the one that blocks #141.
MEASURED_OUT = {
    "cloneSrc": -1,
    "flags": 0,
    "index": 0,
    "map": 1,
    "mode": 0,
    "offDelay": 0,
    "realStatus": 1,
    "status": 1,
    "totalTime": 1234567,
    "type": 0,
    "updateTime": 74,
}

# The seven fields the parser drops on the floor. Listed here rather than derived from
# `MEASURED_OUT` so that a field silently disappearing from the fixture cannot make the
# test that watches for them pass by watching nothing.
UNPARSED_OUT_FIELDS = (
    "cloneSrc", "flags", "map", "offDelay", "realStatus", "totalTime", "updateTime",
)

# One `GetPoolDetails` element, shaped after the 70 top-level keys @sbdomo pasted in
# GitHub #57 (2026-08-26). The KEY NAMES are measured; the values are shapes, not
# originals.
#
# ⚠️ The contents of `podinfo` and `register` are INVENTED — nobody has ever measured
# them, which is precisely why they are treated as unjudged below. Nothing here asserts
# what they contain; the tests assert only that no value of theirs reaches the export,
# which holds whatever they turn out to carry.
MEASURED_POOL_PAYLOAD = {
    "idSystem": 121170,
    "poolNickname": "Bioul",
    "access": 10,
    "pin": "0000-0000000-0000",
    "compta": "XX00000",
    "idAddress": 99999999,
    "podSerial": "POD00012345",
    "Address": "1 Example Street, Anytown",
    "emailNotify": "owner@example.invalid",
    "device": 0,
    "idLinked": None,
    "plans": [{"index": 0, "plan64": "AAAAAAAAAAAAAAAA"}],
    "podinfo": {"serialNumber": "POD00012345", "owner": "A Name"},
    "register": {"customerEmail": "owner@example.invalid", "orderRef": "CMD-9912"},
    "PumpType": 7,
    "probes": [{"index": 16, "type": 5, "filteredValue": 28.25, "seuilMin": 10}],
    "outs": [MEASURED_OUT],
    "params": {"ConsigneEau": 28},
}


async def _export_payload(payload=None, entry_data=None):
    """Run the real diagnostics function over a whole `GetPoolDetails` element."""
    from custom_components.klereo.models import KlereoPoolDetails

    payload = dict(MEASURED_POOL_PAYLOAD if payload is None else payload)
    hass = MagicMock()
    entry = MagicMock()
    entry.as_dict.return_value = {
        "data": entry_data or {"username": "ExampleUser", "password": "secret"},
        "options": {},
    }
    coordinator = MagicMock()
    coordinator.data = {
        "121170": KlereoSystemData(
            info=KlereoSystemInfo.from_dict({"idSystem": 121170, "poolNickname": "Bioul"}),
            details=KlereoPoolDetails.from_dict(payload, raw=payload),
        )
    }
    hass.data = {"klereo": {entry.entry_id: coordinator}}
    result = await async_get_config_entry_diagnostics(hass, entry)
    return result


def _raw(result):
    """Return the raw pool payload out of an export."""
    return result["coordinator_data"]["121170"]["details"]["raw"]


class TestTheRawPayloadReachesTheExport:
    """🔴 Criterion 1 — the export must carry what the parser drops.

    The export is the only remote instrument this project has, and it was structurally
    blind to every field the integration does not already parse — that is, to exactly the
    fields the NEXT question will be about. #141 could not be answered from an export and
    needed a direct API call with the owner's credentials, which no reporter can make for
    us.
    """

    async def test_realstatus_reaches_the_export_for_every_output(self):
        """🔴 THE test of this issue: the field that blocks #141 is in the export."""
        result = await _export_payload()

        outs = _raw(result)["outs"]
        assert [o["realStatus"] for o in outs] == [1]

    @pytest.mark.parametrize("field", UNPARSED_OUT_FIELDS)
    async def test_each_field_the_parser_drops_reaches_the_export(self, field):
        """Positive control, one per field: "the payload is there" must not be
        satisfiable by an EMPTY payload being there.

        Parametrised rather than batched: a batch that loses a field to a typo still
        passes on the others, which is how an instrument comes to measure less than its
        name claims.
        """
        result = await _export_payload()

        assert _raw(result)["outs"][0][field] == MEASURED_OUT[field]

    async def test_the_typed_output_model_did_not_grow(self):
        """🔴 Negative control on the SCOPE: the raw payload answers the question
        *instead of* widening the model, not as well as.

        A field nothing reads is noise — #138 refused exactly that. If `KlereoOutput`
        ever grows a `realStatus`, this test says so.
        """
        result = await _export_payload()

        parsed = result["coordinator_data"]["121170"]["details"]["outs"][0]
        assert set(parsed) == {"index", "status", "mode", "type"}


class TestRedactionReachesTheRawPayload:
    """🔴 Criteria 2 and 3 — the SECURITY claim, checked where the new data actually is.

    `TO_REDACT` is a security claim: the repository asks reporters to paste this export
    into PUBLIC issues on the strength of "credentials are redacted automatically". Adding
    a raw payload publishes an object whose key list comes from the server and can change
    without notice, so "it is redacted" has to be shown FROM THE RAW PAYLOAD and not only
    from the typed object we were already looking at.
    """

    async def test_the_box_pin_is_redacted_in_the_raw_payload(self):
        """🔴 Criterion 2. The weapon that tells "redacted" from "redacted in the one
        place we already had our eyes on"."""
        result = await _export_payload()

        assert _raw(result)["pin"] == "**REDACTED**"

    @pytest.mark.parametrize(
        "key", ["pin", "compta", "idAddress", "podSerial", "Address", "emailNotify"]
    )
    async def test_each_sensitive_key_of_the_raw_payload_is_redacted(self, key):
        """Every key GitHub #57 showed to be sensitive, checked one at a time."""
        result = await _export_payload()

        assert _raw(result)[key] == "**REDACTED**"

    async def test_a_sensitive_key_nested_two_levels_deep_is_redacted(self):
        """🔴 Criterion 3, absurdity control: depth must not be a way out.

        `async_redact_data` recurses through mappings AND lists, so this should hold at
        any depth. Asserting it rather than assuming it is the half that makes the
        security claim true or false.
        """
        payload = dict(MEASURED_POOL_PAYLOAD)
        payload["nested"] = {"level1": {"level2": {"pin": "0000-0000000-0000"}}}

        result = await _export_payload(payload)

        assert _raw(result)["nested"]["level1"]["level2"]["pin"] == "**REDACTED**"

    async def test_a_sensitive_key_inside_a_list_of_dicts_is_redacted(self):
        """Same control through a LIST — `outs`, `probes` and `plans` are all lists."""
        payload = dict(MEASURED_POOL_PAYLOAD)
        payload["linked"] = [{"pin": "0000-0000000-0000"}, {"compta": "XX00000"}]

        result = await _export_payload(payload)

        assert _raw(result)["linked"][0]["pin"] == "**REDACTED**"
        assert _raw(result)["linked"][1]["compta"] == "**REDACTED**"

    async def test_the_measurements_survive_redaction(self):
        """Negative control: an export redacted into uselessness is one nobody pastes."""
        raw = _raw(await _export_payload())

        assert raw["idSystem"] == 121170
        assert raw["poolNickname"] == "Bioul"
        assert raw["access"] == 10
        assert raw["probes"][0]["filteredValue"] == 28.25


class TestTheFiveNeverJudgedKeys:
    """🔴 Criterion 4 — `register`, `plans`, `podinfo`, `idLinked`, `device`.

    Each of the five carries a written verdict in `diagnostics.py`. A key nobody has
    judged is not a safe key: that is the fault of #122, where `username` walked past the
    filter because nobody had enumerated what the object actually contained.
    """

    @pytest.mark.parametrize("key", ["register", "podinfo"])
    async def test_an_unjudged_container_publishes_no_value(self, key):
        """🔴 Contents never measured, in no source, and named after things that would
        hold a serial or a customer record. They do not go out in clear."""
        result = await _export_payload()

        published = repr(_raw(result)[key])
        for value in MEASURED_POOL_PAYLOAD[key].values():
            assert str(value) not in published

    @pytest.mark.parametrize("key", ["register", "podinfo"])
    async def test_an_unjudged_container_still_names_its_keys(self, key):
        """The exit from the redaction: a summary that names the keys without publishing
        their values is what lets the NEXT export judge them.

        Without this, redacting the two containers would just move the blind spot #145 is
        about, with no way out that does not need the owner's credentials again.
        """
        result = await _export_payload()

        published = _raw(result)[key]
        assert "**REDACTED**" in published
        for name in MEASURED_POOL_PAYLOAD[key]:
            assert name in published

    async def test_an_unjudged_container_is_summarised_wherever_it_appears(self):
        """Uniformity: the pass runs over the WHOLE export, not over the raw payload only.

        A rule applied at one address is a rule that misses the next address — the exact
        shape of the defect this issue is about.
        """
        result = await _export_payload()
        info_raw = result["coordinator_data"]["121170"]["info"]["raw"]

        assert "REDACTED" in str(result["coordinator_data"])
        assert "podinfo" not in info_raw or "**REDACTED**" in info_raw["podinfo"]

    async def test_plans_stays_in_clear(self):
        """Verdict: NOT redacted. Upstream reads it (`klereo.class.php:1095`) as a list of
        `{index, plan64}` — the base64 time-slot programme of each output. It describes
        when equipment runs, not who owns it, and it is what a time-slot feature reads."""
        result = await _export_payload()

        assert _raw(result)["plans"] == [{"index": 0, "plan64": "AAAAAAAAAAAAAAAA"}]

    async def test_device_stays_in_clear(self):
        """Verdict: NOT redacted. Documented as "index du bassin dans le POD"
        (`docs/klereo-api.md`), measured `0` in GitHub #57 — an ordinal that says nothing
        without `podSerial`, which is redacted."""
        result = await _export_payload()

        assert _raw(result)["device"] == 0

    async def test_id_linked_stays_in_clear(self):
        """Verdict: NOT redacted, on the same ground as `idSystem` — an internal Klereo
        key naming another system, tied to no person. Measured `None` in GitHub #57.

        ⚠️ It is NOT `idAddress`, the key of the postal address, which IS redacted."""
        result = await _export_payload()

        assert _raw(result)["idLinked"] is None


class TestTheReadmeStillDescribesWhatIsRedacted:
    """🔴 The user-facing half of the same security claim.

    `README.md` tells users, key by key, what the export hides — deliberately, "so you can
    decide rather than trust a blanket promise". A list that drifts behind `TO_REDACT` is
    worse than no list: it reads as an enumeration and is a sample.

    It HAD drifted. `podSerial`, `Address` and `emailNotify` were in the set and named
    nowhere, and #145 is what made that matter: those three ride on the `GetPoolDetails`
    payload, which nothing exported before.
    """

    # Four fields are described in prose rather than by their wire name, because that is
    # what the reader actually sees in Home Assistant. Anything NOT in this map has to
    # appear verbatim — so a key added to `TO_REDACT` and to nothing else fails here.
    README_ALIASES = {
        "password": "password",
        "jwt": "session token",
        "token": "session token",
        "login": "account username",
        "username": "account username",
    }

    @staticmethod
    def _readme():
        from pathlib import Path

        return (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")

    @pytest.mark.parametrize("key", sorted(TO_REDACT))
    def test_the_readme_names_every_redacted_key(self, key):
        """One assertion per key: a batch that loses one still passes on the others.

        A wire name is matched INSIDE ITS BACKTICKS, the way the README writes it. A bare
        substring would let `Address` be satisfied by the `idAddress` two words away —
        a green witness over a key named nowhere, which is the failure being guarded.
        """
        readme = self._readme()

        assert (self.README_ALIASES.get(key) or f"`{key}`") in readme

    @pytest.mark.parametrize("key", sorted(UNJUDGED_CONTAINERS))
    def test_the_readme_names_every_summarised_container(self, key):
        """The two blanked for a different reason are explained, not silently missing."""
        assert f"`{key}`" in self._readme()


class TestTheEnvelopeAroundTheCredential:
    """🔴 The leak of GitHub #58, and the reason four green fixtures never saw it.

    Every `entry.as_dict.return_value` in this file used to carry exactly two keys —
    `data` and `options`. The object Home Assistant actually produces carries sixteen, and
    **two of them are the account identifier under another name**: `title` is
    `data[CONF_USERNAME]` verbatim (`config_flow.py:42`) and `unique_id` is the same string
    lowercased (`config_flow.py:63`). `async_redact_data` matches on key names, so
    `CONF_USERNAME` in `TO_REDACT` blanked one copy and published two.

    The defect was never in the redaction logic. It was in the fixture: a fixture smaller
    than the object cannot fail on the part it omits, and it decides what the suite is
    able to refute. So these tests build a **real `MockConfigEntry`** rather than a dict —
    the envelope can never silently shrink again, and a Home Assistant release that adds a
    key adds it here too.
    """

    SENTINEL = "sentinel-klereo-account-name"

    @classmethod
    async def _export(cls, **entry_kwargs):
        """Export a REAL config entry, not a hand-written stand-in of one."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        entry = MockConfigEntry(
            domain="klereo",
            version=2,  # ConfigFlow.VERSION — the fixture tracks the real flow
            title=cls.SENTINEL,
            unique_id=cls.SENTINEL,
            data={"username": cls.SENTINEL, "password": "hash", "password_hashed": True},
            **entry_kwargs,
        )
        hass = MagicMock()
        coordinator = MagicMock()
        coordinator.data = {}
        hass.data = {"klereo": {entry.entry_id: coordinator}}
        return await async_get_config_entry_diagnostics(hass, entry)

    async def test_the_identifier_appears_nowhere_in_the_whole_export(self):
        """🔴 THE test of this issue, and the only arm that could have caught it.

        It asserts over the SERIALISED export rather than over the two keys now known to
        be guilty. Checking `title` and `unique_id` by name would pass on exactly the
        blindness being fixed: the previous set was complete against every key anyone had
        thought of, and the leak was in the key nobody had.
        """
        import json

        result = await self._export()

        assert self.SENTINEL not in json.dumps(result)

    @pytest.mark.parametrize("key", ["title", "unique_id"])
    async def test_each_envelope_copy_of_the_identifier_is_redacted(self, key):
        """One assertion per key: a batch that loses one still passes on the other."""
        result = await self._export()

        assert result["config_entry"][key] == "**REDACTED**"

    async def test_the_credential_inside_data_is_still_redacted(self):
        """Regression guard for #122: fixing the envelope must not unfix the payload."""
        result = await self._export()

        assert result["config_entry"]["data"]["username"] == "**REDACTED**"
        assert result["config_entry"]["data"]["password"] == "**REDACTED**"

    async def test_the_useful_envelope_keys_survive(self):
        """🔴 Negative control: an export redacted into uselessness is one nobody pastes.

        Without this arm, blanking the whole envelope would pass the test above — and the
        diagnostics would stop naming which integration, which version and which flow the
        entry came from, which is what makes a report actionable.
        """
        result = await self._export()
        envelope = result["config_entry"]

        assert envelope["domain"] == "klereo"
        assert envelope["source"] == "user"
        assert envelope["version"] == 2
        assert envelope["disabled_by"] is None

    async def test_the_judged_sets_cover_the_real_envelope_exactly(self):
        """🔴 The arm that fails when Home Assistant ADDS a key.

        `ENVELOPE_JUDGED_SAFE` plus `ENVELOPE_IDENTITY` plus the two deliberately
        summarised containers must account for every key of the real object. When a future
        release adds one, this fails and someone has to rule on it — instead of the key
        riding out in clear because nobody knew it existed. That is the failure this whole
        class exists to make impossible a third time.
        """
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        real = set(MockConfigEntry(domain="klereo").as_dict())
        summarised = {"discovery_keys", "subentries"}

        assert real == ENVELOPE_JUDGED_SAFE | ENVELOPE_IDENTITY | summarised

    async def test_an_unjudged_envelope_key_is_summarised_not_published(self):
        """A key in neither set publishes its SHAPE, never its value — fail closed.

        Positive control for the branch that will run the day the assertion above starts
        failing: whatever that key holds, it does not reach the export.
        """
        from custom_components.klereo.diagnostics import _redact_envelope

        result = _redact_envelope({"a_key_from_a_future_release": {"secret": "value"}})

        assert "value" not in str(result)
        assert result["a_key_from_a_future_release"] == (
            "**REDACTED** — never judged; dict, keys: [secret]"
        )

    @pytest.mark.parametrize("key", sorted(["title", "unique_id"]))
    def test_the_readme_names_every_redacted_envelope_key(self, key):
        """The README enumerates what the export hides; these two belong in that list.

        Same reasoning as the `TO_REDACT` version above — worse here, because `README.md`
        promised the "account username" was hidden while the envelope published it twice.
        """
        from pathlib import Path

        readme = (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")

        assert f"`{key}`" in readme
