"""Config flow for Klereo integration."""
import hashlib
import logging

import aiohttp
import voluptuous as vol

from homeassistant import config_entries, core
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import KlereoApi, KlereoApiError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def validate_input(hass: core.HomeAssistant, data: dict) -> dict:
    """Validate the user input allows us to connect."""
    session = async_get_clientsession(hass)
    password_hash = hashlib.sha1(data[CONF_PASSWORD].encode("utf-8")).hexdigest()
    api = KlereoApi(data[CONF_USERNAME], password_hash, session)

    try:
        await api.login()
    except KlereoApiError as err:
        raise InvalidAuth from err
    except aiohttp.ClientResponseError as err:
        if err.status in (401, 403):
            raise InvalidAuth from err
        raise CannotConnect from err
    except (aiohttp.ClientError, TimeoutError) as err:
        raise CannotConnect from err

    return {"title": data[CONF_USERNAME]}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Klereo."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)

                await self.async_set_unique_id(user_input[CONF_USERNAME].strip().lower())
                self._abort_if_unique_id_configured()

                stored_data = {
                    CONF_USERNAME: user_input[CONF_USERNAME],
                    CONF_PASSWORD: hashlib.sha1(
                        user_input[CONF_PASSWORD].encode("utf-8")
                    ).hexdigest(),
                }
                return self.async_create_entry(title=info["title"], data=stored_data)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception during Klereo setup")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

    async def async_step_reauth(self, entry_data: dict):
        """Handle re-authentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """Handle re-authentication confirmation."""
        errors = {}
        if user_input is not None:
            try:
                await validate_input(self.hass, user_input)

                stored_data = {
                    CONF_USERNAME: user_input[CONF_USERNAME],
                    CONF_PASSWORD: hashlib.sha1(
                        user_input[CONF_PASSWORD].encode("utf-8")
                    ).hexdigest(),
                }

                self.hass.config_entries.async_update_entry(
                    self._get_reauth_entry(), data=stored_data
                )
                await self.hass.config_entries.async_reload(
                    self._get_reauth_entry().entry_id
                )
                return self.async_abort(reason="reauth_successful")
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception during Klereo reauth")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="reauth_confirm", data_schema=DATA_SCHEMA, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
