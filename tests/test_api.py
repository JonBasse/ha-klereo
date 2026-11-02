"""Tests for the Klereo API client."""
import json
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.klereo.api import (
    API_URL_COMMAND_STATUS,
    HEAT_MODE_AUTO,
    HEAT_MODE_COOLING,
    HEAT_MODE_HEATING,
    HEAT_MODE_STOP,
    OUT_STATE_AUTO,
    OUT_STATE_OFF,
    OUT_STATE_ON,
    KlereoApi,
    KlereoApiError,
    KlereoAuthError,
    state_for_heat_mode,
)


@pytest.fixture
def mock_session():
    """Create a mock aiohttp session.

    We avoid spec=aiohttp.ClientSession because aiohttp's .post() and
    .request() return context managers, not coroutines.  The code under
    test awaits them directly (``await session.post(...)``), so we need
    AsyncMock children that return our fake responses when awaited.
    """
    session = MagicMock()
    session.post = AsyncMock()
    session.request = AsyncMock()
    return session


@pytest.fixture
def api(mock_session):
    """Create a KlereoApi instance with mock session."""
    return KlereoApi("test@example.com", "a94a8fe5ccb19ba61c4c0873d391e987982fbbd3", mock_session)


def _make_response(data, status=200):
    """Create a mock response."""
    response = AsyncMock()
    response.status = status
    response.raise_for_status = MagicMock()
    if status >= 400:
        response.raise_for_status.side_effect = aiohttp.ClientResponseError(
            request_info=MagicMock(), history=(), status=status
        )
    response.json = AsyncMock(return_value=data)
    response.text = AsyncMock(return_value=json.dumps(data))
    return response


class TestLogin:
    """Tests for the login method."""

    async def test_the_measured_refusal_is_an_auth_error(self, api, mock_session):
        """The answer measured on 2026-11-02 for an unknown account (#212)."""
        mock_session.post.return_value = _make_response(
            {"status": "error", "detail": "Identification incorrecte"}
        )
        with pytest.raises(KlereoAuthError):
            await api.login()

    @pytest.mark.parametrize("status", [401, 403])
    async def test_an_http_refusal_is_an_auth_error(self, api, mock_session, status):
        """`KlereoAuthError` alone means "refused": callers must not read status codes too."""
        mock_session.post.return_value = _make_response({}, status=status)
        with pytest.raises(KlereoAuthError):
            await api.login()

    @pytest.mark.parametrize(
        "body",
        [
            pytest.param({"status": "error", "detail": "Service indisponible"}, id="another-detail"),
            pytest.param({"status": "error"}, id="no-detail"),
            pytest.param({"detail": "Identification incorrecte"}, id="detail-without-status"),
            pytest.param({"status": "ok"}, id="no-token"),
            pytest.param({"jwt": None}, id="null-token"),
            pytest.param({"jwt": ""}, id="empty-token"),
            pytest.param([], id="list"),
            pytest.param(None, id="null"),
        ],
    )
    async def test_any_other_answer_without_a_token_is_not_an_auth_error(self, api, mock_session, body):
        """🔴 The discriminant is narrow on purpose: this arm is what an outage looks like."""
        mock_session.post.return_value = _make_response(body)
        with pytest.raises(KlereoApiError) as caught:
            await api.login()
        assert not isinstance(caught.value, KlereoAuthError)
        assert api._token is None

    async def test_a_body_that_is_not_json_is_not_an_auth_error(self, api, mock_session):
        response = _make_response({})
        response.json = AsyncMock(side_effect=json.JSONDecodeError("not JSON", "<html>", 0))
        mock_session.post.return_value = response
        with pytest.raises(KlereoApiError) as caught:
            await api.login()
        assert not isinstance(caught.value, KlereoAuthError)

    async def test_the_reason_klereo_gave_reaches_the_error(self, api, mock_session):
        """An unmeasured refusal must say what it was: that is how the discriminant gets corrected."""
        mock_session.post.return_value = _make_response({"status": "error", "detail": "Compte suspendu"})
        with pytest.raises(KlereoApiError, match="Compte suspendu"):
            await api.login()

    async def test_login_extracts_jwt(self, api, mock_session):
        """Login should extract JWT from 'jwt' key."""
        mock_session.post.return_value = _make_response({"jwt": "my-token"})
        await api.login()
        assert api._token == "my-token"

    async def test_login_extracts_token_key(self, api, mock_session):
        """Login should fall back to 'token' key."""
        mock_session.post.return_value = _make_response({"token": "alt-token"})
        await api.login()
        assert api._token == "alt-token"

    async def test_login_no_token_raises(self, api, mock_session):
        """Login should raise KlereoApiError when no token in response."""
        mock_session.post.return_value = _make_response({"error": "bad"})
        with pytest.raises(KlereoApiError, match="no token"):
            await api.login()

    async def test_a_refused_login_logs_key_names_never_values(self, api, mock_session, caplog):
        """The debug log is a publication channel: names only, the rule of #196."""
        mock_session.post.return_value = _make_response({"error": "SECRET-VALUE"})
        with caplog.at_level("DEBUG", logger="custom_components.klereo.api"):
            with pytest.raises(KlereoApiError):
                await api.login()

        assert "SECRET-VALUE" not in caplog.text
        assert "error" in caplog.text  # positive control: the line is still there

    async def test_a_refused_login_that_is_not_an_object_logs_no_value(self, api, mock_session, caplog):
        """Klereo's `response` is a list elsewhere, and a list's items are values, not keys."""
        mock_session.post.return_value = _make_response(["SECRET-VALUE"])
        with caplog.at_level("DEBUG", logger="custom_components.klereo.api"):
            with pytest.raises(KlereoApiError):
                await api.login()

        assert "SECRET-VALUE" not in caplog.text

    async def test_login_sends_hashed_password(self, api, mock_session):
        """Login should send the pre-hashed password."""
        mock_session.post.return_value = _make_response({"jwt": "tok"})
        await api.login()
        call_kwargs = mock_session.post.call_args
        assert call_kwargs.kwargs["data"]["password"] == "a94a8fe5ccb19ba61c4c0873d391e987982fbbd3"


class TestRequestWithRetry:
    """Tests for _request_with_retry."""

    async def test_successful_request(self, api, mock_session):
        """Successful request returns parsed JSON."""
        api._token = "valid-token"
        mock_session.request.return_value = _make_response({"data": "value"})
        result = await api._request_with_retry("GET", "https://example.com/api")
        assert result == {"data": "value"}

    async def test_401_triggers_reauth(self, api, mock_session):
        """401 response should trigger re-authentication and retry."""
        api._token = "expired-token"

        # First call fails with 401 (raise_for_status raises ClientResponseError)
        fail_response = _make_response({}, status=401)
        success_response = _make_response({"data": "value"})

        # Login response for re-auth
        login_response = _make_response({"jwt": "new-token"})

        mock_session.request.side_effect = [fail_response, success_response]
        mock_session.post.return_value = login_response

        result = await api._request_with_retry("GET", "https://example.com/api")
        assert result == {"data": "value"}
        assert api._token == "new-token"

    async def test_transient_error_retries(self, api, mock_session):
        """ConnectionError should retry once after 2s backoff."""
        api._token = "valid-token"
        success_response = _make_response({"data": "ok"})
        mock_session.request.side_effect = [
            aiohttp.ClientConnectionError("connection lost"),
            success_response,
        ]
        result = await api._request_with_retry("GET", "https://example.com/api")
        assert result == {"data": "ok"}
        assert mock_session.request.call_count == 2

    async def test_transient_error_retry_fails(self, api, mock_session):
        """If retry also fails with transient error, exception propagates."""
        api._token = "valid-token"
        mock_session.request.side_effect = aiohttp.ClientConnectionError("still broken")
        with pytest.raises(aiohttp.ClientConnectionError):
            await api._request_with_retry("GET", "https://example.com/api")

    async def test_non_401_http_error_propagates(self, api, mock_session):
        """Non-401 HTTP errors should propagate without retry."""
        api._token = "valid-token"
        mock_session.request.return_value = _make_response({}, status=500)
        with pytest.raises(aiohttp.ClientResponseError):
            await api._request_with_retry("GET", "https://example.com/api")


class TestParseResponse:
    """Tests for _parse_response."""

    async def test_valid_json(self, api):
        """Valid JSON response should be parsed."""
        response = _make_response({"key": "value"})
        result = await api._parse_response(response, "https://example.com")
        assert result == {"key": "value"}

    async def test_invalid_json_raises(self, api):
        """Invalid JSON should raise KlereoApiError."""
        response = AsyncMock()
        response.raise_for_status = MagicMock()
        response.text = AsyncMock(return_value="not json at all")
        with pytest.raises(KlereoApiError, match="Invalid JSON"):
            await api._parse_response(response, "https://example.com")

    async def test_http_error_raises(self, api):
        """Non-200 status should raise ClientResponseError via raise_for_status."""
        response = _make_response({}, status=503)
        with pytest.raises(aiohttp.ClientResponseError):
            await api._parse_response(response, "https://example.com")

    async def test_an_error_inside_a_200_raises_with_klereos_detail(self, api):
        """`status: error` is a refusal whatever the HTTP status says (#211)."""
        response = _make_response({"status": "error", "detail": "Mauvais délais"})
        with pytest.raises(KlereoApiError, match="Mauvais délais"):
            await api._parse_response(response, "https://example.com")

    async def test_an_error_without_a_detail_still_raises(self, api):
        """`detail` is optional on the wire; the refusal is not."""
        response = _make_response({"status": "error"})
        with pytest.raises(KlereoApiError):
            await api._parse_response(response, "https://example.com")

    @pytest.mark.parametrize(
        "body",
        [
            {"status": "ok", "response": []},
            {"response": "ok"},
            # A `status` inside `response` is a COMMAND status, read by the coordinator.
            {"status": "ok", "response": {"status": "error"}},
            [{"status": "error"}],
        ],
        ids=["ok", "no-status", "nested-status", "bare-list"],
    )
    async def test_anything_else_passes_through_unchanged(self, api, body):
        """Negative arm: only a top-level `status: error` is a refusal."""
        assert await api._parse_response(_make_response(body), "https://example.com") == body


class TestCommandStatus:
    """Tests for the second half of a Klereo write.

    `SetOut` and `SetParam` do not execute — they queue, and return immediately with a
    cmdID. Whether the command actually ran is a separate call (#95).
    """

    async def test_posts_the_command_id(self, api, mock_session):
        """Should ask WaitCommand.php about a specific cmdID."""
        mock_session.request.return_value = _make_response({"status": "ok", "response": 9})
        api._token = "token"

        await api.command_status(4242)

        args, kwargs = mock_session.request.call_args
        # Asserted against the literal endpoint, not against the constant: comparing the
        # constant to itself passes whatever the constant is set to.
        assert args[1].endswith("/CommandStatus.php")
        assert args[1] == API_URL_COMMAND_STATUS
        assert kwargs["data"]["cmdID"] == 4242


class TestHeatModeStates:
    """`newState` on output 4 is decided by the TARGET heat mode. Measured, not inferred.

    🔴 Three network captures of the official web client, two installations, 2026-09-06
    (GitHub #55 — @nopbop, @StephanH27; Forgejo #166):

    | transition | newMode | newState |
    |---|---|---|
    | Auto → Heating (pump already running) | 3 | **1** |
    | Stopped → Heating | 3 | **1** |
    | Heating → Auto | 1 | **2** |
    | Heating → Stopped | 0 | **0** |

    The two Heating rows leave from *different* starting states and send the same value,
    which is what rules out the hypothesis this repository held until then — that `newState`
    depended on where the pump was coming from. It depends on where it is going.
    """

    def test_heating_pairs_with_on(self):
        """🔴 The one value this changes. Upstream's rule said AUTO here; the wire says ON."""
        assert state_for_heat_mode(HEAT_MODE_HEATING) == OUT_STATE_ON

    def test_auto_pairs_with_auto(self):
        """Measured, and identical to what this integration already sent."""
        assert state_for_heat_mode(HEAT_MODE_AUTO) == OUT_STATE_AUTO

    def test_stop_pairs_with_off(self):
        """Measured on both installations, and identical to what was already sent."""
        assert state_for_heat_mode(HEAT_MODE_STOP) == OUT_STATE_OFF

    def test_cooling_is_left_at_auto_because_nobody_has_measured_it(self):
        """⚠️ NOT a measurement — a deliberate refusal to invent one.

        No reporter in either thread owns a reversible heat pump, so the Cooling cell is
        empty. `1, 2, ?, 0` has no pattern to extrapolate from, and guessing it by symmetry
        would turn three measured values back into a table of four guesses. Cooling
        therefore keeps the value this integration has always sent: unchanged behaviour is
        the honest answer to an unmeasured question.
        """
        assert state_for_heat_mode(HEAT_MODE_COOLING) == OUT_STATE_AUTO

    def test_an_unknown_mode_falls_back_to_auto_rather_than_off(self):
        """Control: a mode outside the table must never resolve to OFF.

        OFF is a command that *stops the heat pump*. Resolving an unknown mode to it would
        turn "we do not recognise this" into a destructive action, which is the shape of
        the #58 defect (`newMode` 0 sent as an on command). AUTO is the upstream rule and
        the only non-destructive default.
        """
        assert state_for_heat_mode(42) == OUT_STATE_AUTO
