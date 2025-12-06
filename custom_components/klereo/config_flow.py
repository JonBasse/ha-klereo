"""Config flow for Klereo integration."""
import logging
import voluptuous as vol

from homeassistant import config_entries, core, exceptions
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN
from .api import KlereoApi

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

async def validate_input(hass: core.HomeAssistant, data):
    """Validate the user input allows us to connect.

    Data has the keys from DATA_SCHEMA with values provided by the user.
    """
    session = async_get_clientsession(hass)
    api = KlereoApi(data[CONF_USERNAME], data[CONF_PASSWORD], session)

    try:
        await api.login()
    except Exception as err:
        # If login fails
        raise InvalidAuth from err

    # Login successful, we might want to get systems now or just assume it's good.
    # We can use the username as the title.
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

                return self.async_create_entry(title=info["title"], data=user_input)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )


class InvalidAuth(exceptions.HomeAssistantError):
    """Error to indicate there is invalid auth."""
