"""Tests for Klereo config flow."""
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from custom_components.klereo.api import KlereoApiError
from custom_components.klereo.config_flow import (
    CannotConnect,
    InvalidAuth,
    NoPoolsFound,
    validate_input,
)
from custom_components.klereo.const import hash_password

# 🔴 A Klereo USERNAME, not an e-mail address. This fixture used to read
# "test@example.com", which is the input GitHub #56 reports as broken: it authenticates
# and then matches no pool. The suite was green on the failing scenario.
USER_INPUT = {
    CONF_USERNAME: "BernardPetit",
    CONF_PASSWORD: "mypassword",
}

ONE_POOL = {"response": [{"idSystem": "121170", "poolNickname": "Bioul"}]}


def _api(mock_api_cls, *, login=None, systems=ONE_POOL):
    """Stub the two calls `validate_input` makes — login AND the pool listing.

    Both are stubbed together on purpose: the tests that broke when the listing arm was
    added had only ever stubbed `login`, which is the same reason the flow itself only
    ever checked `login`.
    """
    api = mock_api_cls.return_value
    api.login = AsyncMock(side_effect=login)
    api.get_systems = AsyncMock(return_value=systems)
    return api


class TestValidateInput:
    """Tests for validate_input."""

    async def test_successful_login(self):
        """Should return title on successful login."""
        hass = MagicMock()
        with patch(
            "custom_components.klereo.config_flow.async_get_clientsession"
        ), patch(
            "custom_components.klereo.config_flow.KlereoApi"
        ) as mock_api_cls:
            _api(mock_api_cls)
            result = await validate_input(hass, USER_INPUT)
        assert result == {"title": "BernardPetit"}

    async def test_invalid_auth_on_api_error(self):
        """Should raise InvalidAuth on KlereoApiError."""
        hass = MagicMock()
        with patch(
            "custom_components.klereo.config_flow.async_get_clientsession"
        ), patch(
            "custom_components.klereo.config_flow.KlereoApi"
        ) as mock_api_cls:
            mock_api_cls.return_value.login = AsyncMock(
                side_effect=KlereoApiError("bad creds")
            )
            with pytest.raises(InvalidAuth):
                await validate_input(hass, USER_INPUT)

    async def test_invalid_auth_on_401(self):
        """Should raise InvalidAuth on 401 response."""
        hass = MagicMock()
        with patch(
            "custom_components.klereo.config_flow.async_get_clientsession"
        ), patch(
            "custom_components.klereo.config_flow.KlereoApi"
        ) as mock_api_cls:
            mock_api_cls.return_value.login = AsyncMock(
                side_effect=aiohttp.ClientResponseError(
                    request_info=MagicMock(), history=(), status=401
                )
            )
            with pytest.raises(InvalidAuth):
                await validate_input(hass, USER_INPUT)

    async def test_cannot_connect_on_client_error(self):
        """Should raise CannotConnect on connection error."""
        hass = MagicMock()
        with patch(
            "custom_components.klereo.config_flow.async_get_clientsession"
        ), patch(
            "custom_components.klereo.config_flow.KlereoApi"
        ) as mock_api_cls:
            mock_api_cls.return_value.login = AsyncMock(
                side_effect=aiohttp.ClientError("offline")
            )
            with pytest.raises(CannotConnect):
                await validate_input(hass, USER_INPUT)

    async def test_cannot_connect_on_timeout(self):
        """Should raise CannotConnect on timeout."""
        hass = MagicMock()
        with patch(
            "custom_components.klereo.config_flow.async_get_clientsession"
        ), patch(
            "custom_components.klereo.config_flow.KlereoApi"
        ) as mock_api_cls:
            mock_api_cls.return_value.login = AsyncMock(
                side_effect=TimeoutError()
            )
            with pytest.raises(CannotConnect):
                await validate_input(hass, USER_INPUT)

    async def test_cannot_connect_on_500(self):
        """Should raise CannotConnect on non-auth HTTP error."""
        hass = MagicMock()
        with patch(
            "custom_components.klereo.config_flow.async_get_clientsession"
        ), patch(
            "custom_components.klereo.config_flow.KlereoApi"
        ) as mock_api_cls:
            mock_api_cls.return_value.login = AsyncMock(
                side_effect=aiohttp.ClientResponseError(
                    request_info=MagicMock(), history=(), status=500
                )
            )
            with pytest.raises(CannotConnect):
                await validate_input(hass, USER_INPUT)

    async def test_hashes_password_before_login(self):
        """Should hash the password before passing to API."""
        hass = MagicMock()
        with patch(
            "custom_components.klereo.config_flow.async_get_clientsession"
        ), patch(
            "custom_components.klereo.config_flow.KlereoApi"
        ) as mock_api_cls:
            _api(mock_api_cls)
            await validate_input(hass, USER_INPUT)
            _, call_kwargs = mock_api_cls.call_args
            assert call_kwargs.get("password_hash") or mock_api_cls.call_args[0][1] == hash_password("mypassword")


class TestCredentialsThatLogInAndMatchNoPool:
    """🔴 GitHub #56 — the failure that had no arm anywhere.

    bernardPetit entered his e-mail address in a field labelled "Email". The login
    SUCCEEDED, `GetIndex` returned no pool, and `validate_input` returned a title anyway:
    the flow reported success, the entry was created, and he was left with an integration
    carrying zero entities and no error to explain it. He diagnosed it himself, told us
    the cause, and waited 87 days.

    The old `validate_input` only ever called `login()`. Authentication was never the
    question being asked.
    """

    async def test_an_empty_pool_list_is_refused(self):
        """🔴 THE test of this issue: credentials accepted, no pool, must not succeed."""
        hass = MagicMock()
        with patch(
            "custom_components.klereo.config_flow.async_get_clientsession"
        ), patch("custom_components.klereo.config_flow.KlereoApi") as mock_api_cls:
            _api(mock_api_cls, systems={"response": []})
            with pytest.raises(NoPoolsFound):
                await validate_input(hass, USER_INPUT)

    async def test_it_is_not_reported_as_invalid_auth(self):
        """🔴 The distinction that makes the message useful rather than misleading.

        Collapsing this into `InvalidAuth` would tell the reporter his password is wrong.
        It is not — it is the only part of his input that WAS right, and he would go round
        the loop re-typing it. `NoPoolsFound` must not be a subclass of `InvalidAuth`.
        """
        assert not issubclass(NoPoolsFound, InvalidAuth)
        assert not issubclass(NoPoolsFound, CannotConnect)

    @pytest.mark.parametrize(
        "systems",
        [
            pytest.param({"response": []}, id="empty-response-key"),
            pytest.param({"list_systems": []}, id="empty-legacy-key"),
            pytest.param([], id="bare-empty-list"),
            pytest.param({}, id="no-recognised-key"),
            pytest.param(None, id="null-body"),
            pytest.param("unexpected", id="not-a-container"),
        ],
    )
    async def test_every_shape_that_carries_no_pool_is_refused(self, systems):
        """Klereo's empty answer has more than one shape, and none may slip through.

        Parametrised one per shape rather than batched: a batch that loses a shape to a
        typo still passes on the others, which is how a guard comes to cover less than its
        docstring claims.
        """
        hass = MagicMock()
        with patch(
            "custom_components.klereo.config_flow.async_get_clientsession"
        ), patch("custom_components.klereo.config_flow.KlereoApi") as mock_api_cls:
            _api(mock_api_cls, systems=systems)
            with pytest.raises(NoPoolsFound):
                await validate_input(hass, USER_INPUT)

    async def test_a_pool_still_validates(self):
        """🔴 Negative control: the guard must not refuse the working case.

        Without this arm, `raise NoPoolsFound` unconditionally would pass every test
        above — a guard that rejects everyone is indistinguishable from one that works.
        """
        hass = MagicMock()
        with patch(
            "custom_components.klereo.config_flow.async_get_clientsession"
        ), patch("custom_components.klereo.config_flow.KlereoApi") as mock_api_cls:
            _api(mock_api_cls)
            assert await validate_input(hass, USER_INPUT) == {"title": "BernardPetit"}

    async def test_a_listing_failure_is_a_connection_error_not_an_empty_pool_list(self):
        """An unreachable API must not be reported as "no pool attached to your account".

        `get_systems` raising and `get_systems` returning nothing are different facts, and
        only the second one is about the username. Reporting the first as `no_pools` would
        send a user whose network is down to go hunting for their Klereo username.
        """
        hass = MagicMock()
        with patch(
            "custom_components.klereo.config_flow.async_get_clientsession"
        ), patch("custom_components.klereo.config_flow.KlereoApi") as mock_api_cls:
            api = _api(mock_api_cls)
            api.get_systems = AsyncMock(side_effect=aiohttp.ClientError())
            with pytest.raises(CannotConnect):
                await validate_input(hass, USER_INPUT)


class TestTheFieldSaysWhatTheApiActuallyWants:
    """The user-facing half. A field labelled "Email" over an API that matches only the
    username produces a silent, non-attributable failure — the label is the whole cause.
    """

    @staticmethod
    def _strings(name):
        import json
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent / "custom_components" / "klereo"
        return json.loads((root / name).read_text(encoding="utf-8"))

    @pytest.mark.parametrize("name", ["strings.json", "translations/en.json"])
    @pytest.mark.parametrize("step", ["user", "reauth_confirm"])
    def test_the_username_field_is_not_labelled_email(self, name, step):
        """Both files and both steps — the label lived in four places, not one."""
        data = self._strings(name)["config"]["step"][step]["data"]

        assert data["username"] != "Email"
        assert "username" in data["username"].lower()

    @pytest.mark.parametrize("name", ["strings.json", "translations/en.json"])
    @pytest.mark.parametrize("step", ["user", "reauth_confirm"])
    def test_the_field_says_explicitly_that_it_is_not_the_email(self, name, step):
        """🔴 Renaming the label is not enough on its own.

        Klereo's own app accepts the e-mail address at sign-in, so a user has every reason
        to keep typing it. The description has to contradict that habit in words.
        """
        described = self._strings(name)["config"]["step"][step]["data_description"]

        assert "e-mail" in described["username"].lower()

    @pytest.mark.parametrize("name", ["strings.json", "translations/en.json"])
    def test_the_no_pools_error_exists_and_names_the_cause(self, name):
        """The error the flow now raises must have a message in both files.

        A missing key renders as the raw string `no_pools` in the UI — which is how a
        translated integration silently ships an untranslated error.
        """
        message = self._strings(name)["config"]["error"]["no_pools"]

        assert "username" in message.lower()


class TestHashPassword:
    """Tests for hash_password utility."""

    def test_known_hash(self):
        """Should produce known SHA-1 hash for 'test'."""
        assert hash_password("test") == "a94a8fe5ccb19ba61c4c0873d391e987982fbbd3"

    def test_deterministic(self):
        """Should produce same hash for same input."""
        assert hash_password("hello") == hash_password("hello")

    def test_different_inputs(self):
        """Different inputs should produce different hashes."""
        assert hash_password("a") != hash_password("b")
