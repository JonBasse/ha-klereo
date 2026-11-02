"""A refused login and the re-authentication that follows, through the WHOLE path (#212, #215).

Only the transport is simulated. `KlereoApi`, the coordinator, the config flow and Home
Assistant's own entry lifecycle are real, because both issues live in the seams: a refusal
that one layer reads correctly and the next one swallows, and a reload that each layer
performs because it believes it is the only one.

Every test of a refusal has a twin for an outage. A discriminant that sends the user to
re-enter a password that was never wrong is worse than the defect it closes: a Klereo outage
would then ask every install for credentials at once.
"""
from unittest.mock import patch

import aiohttp
import pytest
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.klereo as klereo
from custom_components.klereo.api import API_URL_GET_INDEX, API_URL_GET_POOL_DETAILS, API_URL_LOGIN
from custom_components.klereo.const import DOMAIN, hash_password

USERNAME = "BernardPetit"
OLD_HASH = hash_password("old password")
NEW_PASSWORD = "new password"

# The answer measured on 2026-11-02, on an unknown account (`docs/klereo-api.md`, #212).
REFUSED = {"json": {"status": "error", "detail": "Identification incorrecte"}}
EXPIRED = {"status": 401}

ACCEPTED = {"json": {"status": "ok", "jwt": "session token"}}
POOLS = {"json": {"status": "ok", "response": [{"idSystem": "SYS1", "poolNickname": "Pool"}]}}
TWO_POOLS = {
    "json": {
        "status": "ok",
        "response": [
            {"idSystem": "SYS1", "poolNickname": "Pool"},
            {"idSystem": "SYS2", "poolNickname": "Other pool"},
        ],
    }
}
DETAILS = {
    "json": {
        "status": "ok",
        "response": [
            {
                "access": 10,
                "probes": [{"index": 0, "type": 5, "filteredValue": 28.5, "directValue": 28.4, "status": 0}],
                "outs": [],
            }
        ],
    }
}

# 🔴 What must NOT read as a wrong password. One parameter per shape: a batch that loses a
# shape to a typo still passes on the others.
OUTAGES = [
    pytest.param({"json": {"status": "error", "detail": "Service indisponible"}}, id="another-detail"),
    pytest.param({"json": {"status": "error"}}, id="status-error-no-detail"),
    pytest.param({"json": {"status": "ok"}}, id="status-ok-no-token"),
    pytest.param({"json": {"detail": "Identification incorrecte"}}, id="detail-without-status"),
    pytest.param({"json": []}, id="json-list"),
    pytest.param({"text": "<html>502 Bad Gateway</html>"}, id="html-body"),
    pytest.param({"text": ""}, id="empty-body"),
    pytest.param({"status": 500}, id="http-500"),
    pytest.param({"status": 503}, id="http-503"),
    pytest.param({"exc": aiohttp.ClientConnectionError()}, id="connection-refused"),
    pytest.param({"exc": TimeoutError()}, id="timeout"),
]


def _serve(aioclient_mock, *, login=ACCEPTED, index=POOLS, details=DETAILS):
    """Answer the three routes a refresh walks, each with its own answer."""
    aioclient_mock.clear_requests()
    aioclient_mock.post(API_URL_LOGIN, **login)
    aioclient_mock.get(API_URL_GET_INDEX, **index)
    aioclient_mock.post(API_URL_GET_POOL_DETAILS, **details)


def _hits(aioclient_mock, url):
    return sum(1 for _, called, *_ in aioclient_mock.mock_calls if str(called) == url)


def _reauth_flows(hass, entry):
    return [
        flow
        for flow in hass.config_entries.flow.async_progress_by_handler(DOMAIN)
        if flow["context"]["source"] == SOURCE_REAUTH and flow["context"]["entry_id"] == entry.entry_id
    ]


def _entry(hass, *, unique_id=USERNAME.lower(), username=USERNAME):
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        unique_id=unique_id,
        data={CONF_USERNAME: username, CONF_PASSWORD: OLD_HASH, "password_hashed": True},
    )
    entry.add_to_hass(hass)
    return entry


async def _load(hass, entry):
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _expire_the_token(hass, entry, aioclient_mock, **routes):
    """The session of a loaded entry dies, and the login that follows answers as `routes` says."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    _serve(aioclient_mock, **{"index": EXPIRED, **routes})
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    return coordinator


@pytest.fixture(autouse=True)
def no_retry_pause():
    """`_request_with_retry` waits 2 s before retrying a transient error."""
    with patch("custom_components.klereo.api.asyncio.sleep"):
        yield


@pytest.fixture
def setups():
    """Count the real `async_setup_entry` runs, which is what a reload costs."""
    calls = []
    real = klereo.async_setup_entry

    async def counting(hass, entry):
        calls.append(entry.entry_id)
        return await real(hass, entry)

    with patch.object(klereo, "async_setup_entry", counting):
        yield calls


class TestRefusedAtFirstLoad:
    """`async_config_entry_first_refresh`: reauthentication, never `ConfigEntryNotReady`."""

    @pytest.mark.parametrize(
        "login",
        [pytest.param(REFUSED, id="refused-in-a-200"), pytest.param({"status": 401}, id="http-401")],
    )
    async def test_a_refusal_asks_for_the_credentials(self, hass, enable_custom_integrations, aioclient_mock, login):
        _serve(aioclient_mock, login=login)
        entry = _entry(hass)

        await _load(hass, entry)

        assert entry.state is ConfigEntryState.SETUP_ERROR
        assert len(_reauth_flows(hass, entry)) == 1

    @pytest.mark.parametrize("login", OUTAGES)
    async def test_an_outage_retries_and_asks_nothing(self, hass, enable_custom_integrations, aioclient_mock, login):
        _serve(aioclient_mock, login=login)
        entry = _entry(hass)

        await _load(hass, entry)

        assert entry.state is ConfigEntryState.SETUP_RETRY
        assert _reauth_flows(hass, entry) == []


class TestRefusedInFlight:
    """The token expires on a loaded entry, and the login that replaces it answers."""

    @pytest.mark.parametrize(
        "login",
        [pytest.param(REFUSED, id="refused-in-a-200"), pytest.param({"status": 401}, id="http-401")],
    )
    async def test_a_refusal_asks_for_the_credentials(self, hass, enable_custom_integrations, aioclient_mock, login):
        _serve(aioclient_mock)
        entry = _entry(hass)
        await _load(hass, entry)
        assert entry.state is ConfigEntryState.LOADED

        coordinator = await _expire_the_token(hass, entry, aioclient_mock, login=login)

        assert coordinator.last_update_success is False
        assert len(_reauth_flows(hass, entry)) == 1

    @pytest.mark.parametrize(
        "index",
        [pytest.param(POOLS, id="one-pool"), pytest.param(TWO_POOLS, id="two-pools")],
    )
    async def test_a_refusal_behind_the_pool_details_is_not_lost(
        self, hass, enable_custom_integrations, aioclient_mock, index
    ):
        """🔴 `gather(return_exceptions=True)` turns the refusal into a value.

        The listing can succeed and the token expire on the next call, so the refusal arrives
        through the results of `gather`, where a pool-level failure is only worth a warning.
        With some pools still served, the next poll fails on `GetIndex` and asks all the same.
        """
        _serve(aioclient_mock)
        entry = _entry(hass)
        await _load(hass, entry)

        coordinator = await _expire_the_token(
            hass, entry, aioclient_mock, login=REFUSED, index=index, details=EXPIRED
        )

        assert coordinator.last_update_success is False
        assert len(_reauth_flows(hass, entry)) == 1

    @pytest.mark.parametrize("login", OUTAGES)
    async def test_an_outage_fails_the_update_and_asks_nothing(
        self, hass, enable_custom_integrations, aioclient_mock, login
    ):
        _serve(aioclient_mock)
        entry = _entry(hass)
        await _load(hass, entry)

        coordinator = await _expire_the_token(hass, entry, aioclient_mock, login=login)

        assert coordinator.last_update_success is False
        assert _reauth_flows(hass, entry) == []

        # An outage is a state, not a verdict: the next good answer restores everything.
        _serve(aioclient_mock)
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        assert coordinator.last_update_success is True

    @pytest.mark.parametrize(
        "login",
        [
            pytest.param({"json": {"status": "error", "detail": "Service indisponible"}}, id="another-detail"),
            pytest.param({"text": "<html>502 Bad Gateway</html>"}, id="html-body"),
            pytest.param({"status": 503}, id="http-503"),
        ],
    )
    async def test_a_klereo_answer_that_is_not_a_refusal_is_update_failed(
        self, hass, enable_custom_integrations, aioclient_mock, login
    ):
        """The named exception of the criterion, on the arms where Klereo did answer."""
        _serve(aioclient_mock)
        entry = _entry(hass)
        await _load(hass, entry)

        coordinator = await _expire_the_token(hass, entry, aioclient_mock, login=login)

        assert isinstance(coordinator.last_exception, UpdateFailed)


async def _start_reauth(hass, entry, aioclient_mock):
    """Load the entry and open a reauthentication, whatever brought the user there."""
    _serve(aioclient_mock)
    await _load(hass, entry)
    return await entry.start_reauth_flow(hass)


async def _submit(hass, flow, username=USERNAME, password=NEW_PASSWORD):
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {CONF_USERNAME: username, CONF_PASSWORD: password}
    )
    await hass.async_block_till_done()
    return result


class TestReauthenticationSucceeds:
    async def test_the_form_is_filled_with_the_username_and_not_the_password(
        self, hass, enable_custom_integrations, aioclient_mock
    ):
        flow = await _start_reauth(hass, _entry(hass), aioclient_mock)

        assert flow["step_id"] == "reauth_confirm"
        suggested = {
            str(key): (key.description or {}).get("suggested_value") for key in flow["data_schema"].schema
        }
        assert suggested == {CONF_USERNAME: USERNAME, CONF_PASSWORD: None}

    async def test_it_stores_the_new_hash_and_reloads_once(
        self, hass, enable_custom_integrations, aioclient_mock, setups
    ):
        """🔴 The update listener and the flow must not each reload the entry."""
        entry = _entry(hass)
        flow = await _start_reauth(hass, entry, aioclient_mock)
        assert len(setups) == 1
        logins_before = _hits(aioclient_mock, API_URL_LOGIN)

        result = await _submit(hass, flow)

        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "reauth_successful"
        assert entry.data[CONF_PASSWORD] == hash_password(NEW_PASSWORD)
        assert entry.state is ConfigEntryState.LOADED
        assert len(setups) == 2
        # One to validate the form, one for the single reload: the wire agrees with the count.
        assert _hits(aioclient_mock, API_URL_LOGIN) - logins_before == 2

    async def test_the_same_password_still_reloads_once(self, hass, enable_custom_integrations, aioclient_mock, setups):
        """🔴 A refusal stops the polling, so an unchanged entry has to come back as well.

        Klereo can refuse a password that was right, and nothing else restarts the coordinator:
        an entry whose data did not change fires no update listener at all.
        """
        entry = _entry(hass)
        flow = await _start_reauth(hass, entry, aioclient_mock)

        result = await _submit(hass, flow, password="old password")

        assert result["reason"] == "reauth_successful"
        assert len(setups) == 2

    async def test_an_entry_refused_at_first_load_comes_back(
        self, hass, enable_custom_integrations, aioclient_mock, setups
    ):
        """The listener is registered after the first refresh, so on this path there is none."""
        _serve(aioclient_mock, login=REFUSED)
        entry = _entry(hass)
        await _load(hass, entry)
        flow, = _reauth_flows(hass, entry)
        assert entry.state is ConfigEntryState.SETUP_ERROR

        _serve(aioclient_mock)
        await _submit(hass, flow)

        assert entry.state is ConfigEntryState.LOADED
        assert len(setups) == 2

    async def test_an_entry_refused_in_flight_polls_again(self, hass, enable_custom_integrations, aioclient_mock):
        """The whole loop: refused, re-entered, and the data flows again."""
        _serve(aioclient_mock)
        entry = _entry(hass)
        await _load(hass, entry)
        await _expire_the_token(hass, entry, aioclient_mock, login=REFUSED)
        flow, = _reauth_flows(hass, entry)

        _serve(aioclient_mock)
        await _submit(hass, flow)

        assert entry.state is ConfigEntryState.LOADED
        assert hass.data[DOMAIN][entry.entry_id].last_update_success is True
        assert _reauth_flows(hass, entry) == []

    @pytest.mark.parametrize(
        "typed",
        [
            pytest.param(USERNAME.upper(), id="upper-case"),
            pytest.param(USERNAME.lower(), id="lower-case"),
            pytest.param(f"  {USERNAME} ", id="surrounding-spaces"),
            pytest.param(f" {USERNAME.upper()}\t", id="both"),
        ],
    )
    async def test_case_and_spaces_are_the_same_account(self, hass, enable_custom_integrations, aioclient_mock, typed):
        entry = _entry(hass)
        flow = await _start_reauth(hass, entry, aioclient_mock)

        result = await _submit(hass, flow, username=typed)

        assert result["reason"] == "reauth_successful"
        assert entry.data[CONF_USERNAME] == typed.strip()

    @pytest.mark.parametrize(
        "unique_id",
        [
            pytest.param(None, id="before-76348ca-no-unique-id"),
            pytest.param(USERNAME, id="before-5680931-not-lowercased"),
            pytest.param("previous account", id="moved-by-an-earlier-reauth"),
        ],
    )
    async def test_an_old_entry_is_never_locked_out(self, hass, enable_custom_integrations, aioclient_mock, unique_id):
        """🔴 The account in use is the one the entry logs in with, whatever its `unique_id` says.

        No migration ever rewrote `unique_id`, so these three survive on real installs. HA's
        `_abort_if_unique_id_mismatch` compares against it verbatim and would refuse all three,
        with no way out but deleting the entry and its history.
        """
        entry = _entry(hass, unique_id=unique_id)
        flow = await _start_reauth(hass, entry, aioclient_mock)

        result = await _submit(hass, flow)

        assert result["reason"] == "reauth_successful"
        assert entry.data[CONF_PASSWORD] == hash_password(NEW_PASSWORD)


class TestReauthenticationRefused:
    async def test_another_account_is_refused_and_nothing_changes(
        self, hass, enable_custom_integrations, aioclient_mock, setups
    ):
        entry = _entry(hass)
        flow = await _start_reauth(hass, entry, aioclient_mock)
        logins_before = _hits(aioclient_mock, API_URL_LOGIN)

        result = await _submit(hass, flow, username="SomeoneElse")

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "wrong_account"}
        assert entry.data[CONF_USERNAME] == USERNAME
        assert entry.data[CONF_PASSWORD] == OLD_HASH
        assert len(setups) == 1
        # Klereo is not asked: the verdict needs no network, and that login is not ours to try.
        assert _hits(aioclient_mock, API_URL_LOGIN) == logins_before

    async def test_the_flow_survives_so_a_typo_can_be_corrected(self, hass, enable_custom_integrations, aioclient_mock):
        """🔴 Why this is a form error and not an abort.

        A refusal stops the polling (`auth_failed` skips `_schedule_refresh`), so nothing would
        open a new flow: aborting here leaves a loaded entry frozen until HA restarts, and the
        notification that explained why is gone with the flow.
        """
        entry = _entry(hass)
        flow = await _start_reauth(hass, entry, aioclient_mock)
        await _submit(hass, flow, username="SomeoneElse")

        result = await _submit(hass, flow)

        assert result["reason"] == "reauth_successful"

    async def test_a_wrong_password_stays_on_the_form(self, hass, enable_custom_integrations, aioclient_mock, setups):
        entry = _entry(hass)
        flow = await _start_reauth(hass, entry, aioclient_mock)

        _serve(aioclient_mock, login=REFUSED)
        result = await _submit(hass, flow)

        assert result["errors"] == {"base": "invalid_auth"}
        assert entry.data[CONF_PASSWORD] == OLD_HASH
        assert len(setups) == 1

    @pytest.mark.parametrize("login", OUTAGES)
    async def test_an_outage_is_not_reported_as_a_wrong_password(
        self, hass, enable_custom_integrations, aioclient_mock, login
    ):
        flow = await _start_reauth(hass, _entry(hass), aioclient_mock)

        _serve(aioclient_mock, login=login)
        result = await _submit(hass, flow)

        assert result["errors"] == {"base": "cannot_connect"}


class TestTheAccountFormReadsTheSameDiscriminant:
    """`validate_input` and the coordinator used to disagree about the same answer (#212)."""

    async def _submit_user_form(self, hass):
        flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        return await hass.config_entries.flow.async_configure(
            flow["flow_id"], {CONF_USERNAME: USERNAME, CONF_PASSWORD: NEW_PASSWORD}
        )

    @pytest.mark.parametrize(
        "login",
        [pytest.param(REFUSED, id="refused-in-a-200"), pytest.param({"status": 401}, id="http-401")],
    )
    async def test_a_refusal_is_invalid_auth(self, hass, enable_custom_integrations, aioclient_mock, login):
        _serve(aioclient_mock, login=login)

        assert (await self._submit_user_form(hass))["errors"] == {"base": "invalid_auth"}

    @pytest.mark.parametrize("login", OUTAGES)
    async def test_an_outage_is_cannot_connect(self, hass, enable_custom_integrations, aioclient_mock, login):
        _serve(aioclient_mock, login=login)

        assert (await self._submit_user_form(hass))["errors"] == {"base": "cannot_connect"}


class TestOptionsStillReload:
    """The update listener carried this; it could not stay beside the reauthentication."""

    async def _submit_options(self, hass, entry, scan_interval):
        flow = await hass.config_entries.options.async_init(entry.entry_id)
        await hass.config_entries.options.async_configure(flow["flow_id"], {"scan_interval": scan_interval})
        await hass.async_block_till_done()

    async def test_a_changed_option_reloads_once_with_the_new_value(
        self, hass, enable_custom_integrations, aioclient_mock, setups
    ):
        _serve(aioclient_mock)
        entry = _entry(hass)
        await _load(hass, entry)

        await self._submit_options(hass, entry, 45)

        assert len(setups) == 2
        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert coordinator.update_interval.total_seconds() == 45 * 60

    async def test_an_unchanged_option_does_not_reload(self, hass, enable_custom_integrations, aioclient_mock, setups):
        _serve(aioclient_mock)
        entry = _entry(hass)
        await _load(hass, entry)
        await self._submit_options(hass, entry, 45)
        assert len(setups) == 2

        await self._submit_options(hass, entry, 45)

        assert len(setups) == 2


class TestNoUsageReport:
    async def test_the_reauthentication_trips_no_deprecation(
        self, hass, enable_custom_integrations, aioclient_mock, caplog
    ):
        """`async_update_reload_and_abort` beside a listener breaks in HA 2026.12."""
        flow = await _start_reauth(hass, _entry(hass), aioclient_mock)

        await _submit(hass, flow)

        assert "has an update listener" not in caplog.text
