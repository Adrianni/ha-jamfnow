"""The Jamf Now integration."""

from __future__ import annotations

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .api import JamfNowApiError, JamfNowAuthError, JamfNowClient
from .const import (
    CONF_BASE_URL,
    DEFAULT_BASE_URL,
    DOMAIN,
    PLATFORMS,
    SERVICE_DISABLE_LOST_MODE,
    SERVICE_ENABLE_LOST_MODE,
    SERVICE_PLAY_SOUND,
    SERVICE_RESTART_DEVICE,
    SERVICE_SET_BLUEPRINT,
    SERVICE_SHUTDOWN_DEVICE,
    SERVICE_SYNC_INVENTORY,
)
from .coordinator import JamfNowDataUpdateCoordinator

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

DEVICE_SCHEMA = {vol.Required("device_id"): vol.All(cv.ensure_list, [cv.string])}


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the services once for the whole integration."""
    _register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # The shared HA session drops cookies, but the Jamf login relies on a SESSION cookie,
    # so this entry owns a session with a cookie jar (closed again on unload).
    session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True))
    client = JamfNowClient(
        session=session,
        base_url=entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL),
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
    )

    try:
        await client.async_login()
    except JamfNowAuthError as err:
        await session.close()
        raise ConfigEntryAuthFailed(str(err)) from err
    except JamfNowApiError as err:
        await session.close()
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = JamfNowDataUpdateCoordinator(hass, entry, client)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await session.close()
        raise

    entry.runtime_data = coordinator
    entry.async_on_unload(session.close)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def _resolve_targets(hass: HomeAssistant, call: ServiceCall) -> list[tuple[JamfNowDataUpdateCoordinator, str]]:
    """Map the selected Home Assistant devices to (coordinator, Jamf device id)."""
    if call.data.get("entity_id"):
        raise ServiceValidationError("Select a Jamf Now device, not an entity")
    registry = dr.async_get(hass)
    entries = [e for e in hass.config_entries.async_entries(DOMAIN) if hasattr(e, "runtime_data")]
    targets: list[tuple[JamfNowDataUpdateCoordinator, str]] = []
    for ha_device_id in call.data["device_id"]:
        device = registry.async_get(ha_device_id)
        jamf_id = None
        if device:
            jamf_id = next((i[1] for i in device.identifiers if i[0] == DOMAIN), None)
        if not jamf_id:
            raise ServiceValidationError(f"{ha_device_id} is not a Jamf Now device")
        coordinator = next((e.runtime_data for e in entries if e.runtime_data.device_present(jamf_id)), None)
        if coordinator is None:
            raise ServiceValidationError(f"Device {jamf_id} not found in Jamf Now data")
        targets.append((coordinator, jamf_id))
    return targets


def _register_services(hass: HomeAssistant) -> None:
    def _simple(method: str):
        async def handler(call: ServiceCall) -> None:
            for coordinator, jamf_id in _resolve_targets(hass, call):
                await getattr(coordinator, method)(jamf_id)

        return handler

    async def handle_set_blueprint(call: ServiceCall) -> None:
        for coordinator, jamf_id in _resolve_targets(hass, call):
            await coordinator.async_set_blueprint(jamf_id, call.data["blueprint_id"])

    async def handle_enable_lost_mode(call: ServiceCall) -> None:
        for coordinator, jamf_id in _resolve_targets(hass, call):
            await coordinator.async_enable_lost_mode(
                jamf_id,
                message=call.data.get("message"),
                phone=call.data.get("phone"),
                footnote=call.data.get("footnote"),
                play_sound=call.data.get("play_sound"),
            )

    base = {vol.Optional("entity_id"): cv.match_all, **DEVICE_SCHEMA}
    simple = vol.Schema(base, extra=vol.ALLOW_EXTRA)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_BLUEPRINT,
        handle_set_blueprint,
        vol.Schema({**base, vol.Required("blueprint_id"): cv.string}, extra=vol.ALLOW_EXTRA),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ENABLE_LOST_MODE,
        handle_enable_lost_mode,
        vol.Schema(
            {
                **base,
                vol.Optional("message"): cv.string,
                vol.Optional("phone"): cv.string,
                vol.Optional("footnote"): cv.string,
                vol.Optional("play_sound"): cv.boolean,
            },
            extra=vol.ALLOW_EXTRA,
        ),
    )
    for service, method in (
        (SERVICE_DISABLE_LOST_MODE, "async_disable_lost_mode"),
        (SERVICE_PLAY_SOUND, "async_play_sound"),
        (SERVICE_RESTART_DEVICE, "async_restart"),
        (SERVICE_SHUTDOWN_DEVICE, "async_power_off"),
        (SERVICE_SYNC_INVENTORY, "async_sync_inventory"),
    ):
        hass.services.async_register(DOMAIN, service, _simple(method), simple)
