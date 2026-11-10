"""Config flow for Jamf Now."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .api import JamfNowApiError, JamfNowAuthError, JamfNowClient
from .const import CONF_BASE_URL, DEFAULT_BASE_URL, DOMAIN


async def _validate_input(hass: HomeAssistant, data: Mapping[str, Any]) -> None:
    """Log in with the given credentials. Raises JamfNowAuthError / JamfNowApiError."""
    session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True))
    try:
        client = JamfNowClient(
            session=session,
            base_url=data.get(CONF_BASE_URL, DEFAULT_BASE_URL),
            username=data[CONF_USERNAME],
            password=data[CONF_PASSWORD],
        )
        await client.async_login()
    finally:
        await session.close()


class JamfNowConfigFlow(ConfigFlow, domain=DOMAIN):
    """Log in to Jamf Now (Jamf ID) when the integration is added."""

    VERSION = 1

    async def _try_login(self, data: Mapping[str, Any]) -> dict[str, str]:
        try:
            await _validate_input(self.hass, data)
        except JamfNowAuthError as err:
            return {"base": "invalid_auth", "detail": str(err)}
        except (JamfNowApiError, aiohttp.ClientError):
            return {"base": "cannot_connect"}
        except Exception:  # noqa: BLE001 - shown as a generic error in the UI
            return {"base": "unknown"}
        return {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders = {"detail": ""}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_USERNAME].strip().lower())
            self._abort_if_unique_id_configured()
            result = await self._try_login(user_input)
            if not result:
                return self.async_create_entry(title=user_input[CONF_USERNAME], data=user_input)
            errors["base"] = result["base"]
            placeholders["detail"] = result.get("detail", "")

        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME, default=(user_input or {}).get(CONF_USERNAME, "")): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors, description_placeholders=placeholders
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        placeholders = {"username": entry.data[CONF_USERNAME], "detail": ""}

        if user_input is not None:
            data = {**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]}
            result = await self._try_login(data)
            if not result:
                return self.async_update_reload_and_abort(entry, data=data)
            errors["base"] = result["base"]
            placeholders["detail"] = result.get("detail", "")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
            description_placeholders=placeholders,
        )
