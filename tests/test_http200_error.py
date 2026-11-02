"""An error answered inside an HTTP 200, through the WHOLE path (#211).

Klereo can refuse a request with `HTTP 200 {"status":"error","detail":...}`: measured on
`SetAutoOff` and on `GetJWT` (`docs/klereo-api.md`, #212). Only the transport is simulated
here. `KlereoApi`, the coordinator, the entities and the service calls are the real ones,
because the defect sat in the seam between them: every layer worked, and the refusal still
read as a successful refresh with no entities, or as a successful write.
"""
import logging

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, STATE_UNAVAILABLE
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.klereo.api import (
    API_URL_COMMAND_STATUS,
    API_URL_GET_INDEX,
    API_URL_GET_POOL_DETAILS,
    API_URL_LOGIN,
    API_URL_SET_AUTO_OFF,
    API_URL_SET_OUT,
    API_URL_SET_PARAM,
)
from custom_components.klereo.const import DOMAIN

SYS = "SYS1"
DETAIL = "Mauvais délais"
REFUSED = {"status": "error", "detail": DETAIL}

QUEUED = {"status": "ok", "response": [{"cmdID": 77, "poolID": SYS}]}
HEALTHY = {
    API_URL_LOGIN: {"status": "ok", "jwt": "session token"},
    API_URL_GET_INDEX: {"status": "ok", "response": [{"idSystem": SYS, "poolNickname": "Pool"}]},
    API_URL_GET_POOL_DETAILS: {
        "status": "ok",
        "response": [
            {
                "access": 10,
                "probes": [{"index": 0, "type": 5, "filteredValue": 28.5, "directValue": 28.4, "status": 0}],
                "outs": [{"index": 0, "type": 0, "mode": 0, "status": 1, "offDelay": 240}],
                "RegulModes": {"ConsigneEau": 28, "HeaterMode": 2},
            }
        ],
    },
    API_URL_SET_OUT: QUEUED,
    API_URL_SET_PARAM: QUEUED,
    API_URL_SET_AUTO_OFF: QUEUED,
    API_URL_COMMAND_STATUS: {"status": "ok", "response": {"cmdID": 77, "status": 9, "detail": "Ok"}},
}


def _serve(aioclient_mock, **refused):
    """Answer every route, the ones named in `refused` (url=body) instead of the healthy body."""
    aioclient_mock.clear_requests()
    answers = {**HEALTHY, **{url: body for url, body in refused.values()}}
    for url, body in answers.items():
        register = aioclient_mock.get if url == API_URL_GET_INDEX else aioclient_mock.post
        register(url, json=body)


def _hits(aioclient_mock, url):
    return sum(1 for _, called, *_ in aioclient_mock.mock_calls if str(called) == url)


async def _load(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        data={CONF_USERNAME: "u", CONF_PASSWORD: "p", "password_hashed": True},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _entity(hass, domain, unique_id):
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, unique_id)
    assert entity_id is not None, f"{domain} {unique_id} was not created"
    return entity_id


def _states(hass):
    return [state.state for state in hass.states.async_all() if state.domain in ("sensor", "switch")]


@pytest.mark.parametrize(
    "route",
    [
        pytest.param((API_URL_GET_INDEX, "GetIndex.php"), id="GetIndex"),
        pytest.param((API_URL_GET_POOL_DETAILS, "GetPoolDetails.php"), id="GetPoolDetails"),
    ],
)
async def test_a_refused_read_fails_the_update_and_says_so(
    hass, enable_custom_integrations, aioclient_mock, caplog, route
):
    """Unavailable through a FAILED refresh, not through an empty one that counts as a success."""
    url, route_name = route
    _serve(aioclient_mock)
    entry = await _load(hass)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    # Positive control: "unavailable afterwards" proves nothing about entities never available.
    assert _states(hass) and STATE_UNAVAILABLE not in _states(hass)

    _serve(aioclient_mock, refused=(url, REFUSED))
    caplog.clear()
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.last_update_success is False
    assert set(_states(hass)) == {STATE_UNAVAILABLE}
    errors = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert any(DETAIL in message and route_name in message for message in errors), errors

    # The refusal is a state, not a verdict: the next good answer restores everything.
    _serve(aioclient_mock)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.last_update_success is True
    assert _states(hass) and STATE_UNAVAILABLE not in _states(hass)


async def test_a_read_refused_at_startup_leaves_the_entry_retrying(
    hass, enable_custom_integrations, aioclient_mock
):
    """Before #211 this loaded an entry with no entities and nothing to explain it."""
    _serve(aioclient_mock, refused=(API_URL_GET_INDEX, REFUSED))

    entry = await _load(hass)

    assert entry.state is ConfigEntryState.SETUP_RETRY


def _write_calls(hass):
    """(route, service domain, service, entity, data) for each of the three write routes."""
    return {
        "SetOut": (API_URL_SET_OUT, "switch", "turn_off", _entity(hass, "switch", f"{SYS}_output_0"), {}),
        "SetParam": (
            API_URL_SET_PARAM, "number", "set_value",
            _entity(hass, "number", f"{SYS}_number_ConsigneEau"), {"value": 29},
        ),
        "SetAutoOff": (
            API_URL_SET_AUTO_OFF, "number", "set_value",
            _entity(hass, "number", f"{SYS}_auto_off_0"), {"value": 60},
        ),
    }


@pytest.mark.parametrize("write", ["SetOut", "SetParam", "SetAutoOff"])
async def test_a_refused_write_is_a_visible_failure(hass, enable_custom_integrations, aioclient_mock, write):
    """The service call raises with Klereo's own words, and no verdict is asked of nothing."""
    _serve(aioclient_mock)
    await _load(hass)
    url, domain, service, entity_id, data = _write_calls(hass)[write]

    _serve(aioclient_mock, refused=(url, REFUSED))
    with pytest.raises(HomeAssistantError, match=DETAIL):
        await hass.services.async_call(domain, service, {"entity_id": entity_id, **data}, blocking=True)
    await hass.async_block_till_done()

    assert _hits(aioclient_mock, url) == 1
    assert _hits(aioclient_mock, API_URL_COMMAND_STATUS) == 0


@pytest.mark.parametrize("write", ["SetOut", "SetParam", "SetAutoOff"])
async def test_an_accepted_write_stays_a_success(hass, enable_custom_integrations, aioclient_mock, write):
    """Negative arm: `status: ok` still queues, still gets confirmed, still raises nothing."""
    _serve(aioclient_mock)
    await _load(hass)
    url, domain, service, entity_id, data = _write_calls(hass)[write]

    await hass.services.async_call(domain, service, {"entity_id": entity_id, **data}, blocking=True)
    await hass.async_block_till_done()

    assert _hits(aioclient_mock, url) == 1
    assert _hits(aioclient_mock, API_URL_COMMAND_STATUS) == 1


async def test_a_refused_status_read_is_unconfirmed_not_rejected(
    hass, enable_custom_integrations, aioclient_mock, caplog
):
    """The command is QUEUED and may well run: an unreadable verdict must not claim otherwise.

    `_async_confirm_command` keeps "unconfirmed" apart from "rejected" (#140). A refusal of
    `CommandStatus` says nothing about the command, so it is logged with Klereo's detail and
    does not raise "rejected".
    """
    _serve(aioclient_mock)
    await _load(hass)
    url, domain, service, entity_id, data = _write_calls(hass)["SetOut"]

    _serve(aioclient_mock, refused=(API_URL_COMMAND_STATUS, REFUSED))
    caplog.clear()
    await hass.services.async_call(domain, service, {"entity_id": entity_id, **data}, blocking=True)
    await hass.async_block_till_done()

    assert _hits(aioclient_mock, url) == 1
    assert any(
        record.levelno == logging.WARNING and DETAIL in record.getMessage()
        for record in caplog.records
    )


async def test_a_listing_refused_during_setup_is_not_reported_as_no_pools(
    hass, enable_custom_integrations, aioclient_mock
):
    """`no_pools` tells the reporter of GitHub #56 their account is empty; here it is not."""
    _serve(aioclient_mock, refused=(API_URL_GET_INDEX, REFUSED))

    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {CONF_USERNAME: "u", CONF_PASSWORD: "p"}
    )

    assert result["errors"] == {"base": "cannot_connect"}
