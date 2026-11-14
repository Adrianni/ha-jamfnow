"""Data coordinator and command handling for Jamf Now."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    DEFAULT_LOST_MESSAGE,
    JamfNowAuthError,
    JamfNowBlueprint,
    JamfNowClient,
    JamfNowDevice,
    JamfNowError,
)
from .const import (
    CLEAR_PASSCODE_DELAY,
    DOMAIN,
    FAST_UPDATE_INTERVAL_SECONDS,
    LOST_MODE_POLL_INTERVAL,
    LOST_MODE_WAIT_TIMEOUT,
    UPDATE_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)

# Statuses where Lost Mode is on, or on its way on
LOST_MODE_ON = {"ENABLED", "PENDING"}
# Statuses where the device is still locked: includes REMOVING, because the device has not
# yet confirmed that Lost Mode was removed
LOST_MODE_ACTIVE = LOST_MODE_ON | {"REMOVING"}


class JamfNowData:
    """Snapshot of everything fetched from Jamf Now."""

    def __init__(self, devices: list[JamfNowDevice], blueprints: list[JamfNowBlueprint]) -> None:
        self.devices = devices
        self.blueprints = blueprints


class JamfNowDataUpdateCoordinator(DataUpdateCoordinator[JamfNowData]):
    """Polls Jamf Now and sends commands to devices."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: JamfNowClient) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"{DOMAIN}_coordinator",
            config_entry=entry,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )
        self.client = client
        self._refresh_timers: list[CALLBACK_TYPE] = []
        # Lock screen text used the next time Lost Mode is enabled, per Jamf device id
        self.lost_mode_settings: dict[str, dict[str, str]] = {}

    async def _async_update_data(self) -> JamfNowData:
        try:
            devices = await self.client.async_get_devices()
            blueprints = await self.client.async_get_blueprints()
        except JamfNowAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except JamfNowError as err:
            raise UpdateFailed(f"Error communicating with Jamf Now: {err}") from err
        await self._apply_restrictions(devices)
        self._adjust_interval(devices)
        return JamfNowData(devices=devices, blueprints=blueprints)

    async def _apply_restrictions(self, devices: list[JamfNowDevice]) -> None:
        """Read the App Store restriction once per blueprint (failures leave it unknown)."""
        blueprint_ids = sorted({d.blueprint_id for d in devices if d.blueprint_id})
        results = await asyncio.gather(
            *(self.client.async_get_restrictions(b) for b in blueprint_ids), return_exceptions=True
        )
        allowed: dict[str, bool] = {}
        for blueprint_id, result in zip(blueprint_ids, results):
            if isinstance(result, JamfNowAuthError):
                raise ConfigEntryAuthFailed(str(result)) from result
            if isinstance(result, Exception):
                _LOGGER.debug("Could not read restrictions for blueprint %s: %s", blueprint_id, result)
                continue
            allowed[blueprint_id] = self.client.app_store_allowed(result)
        for device in devices:
            device.app_store_allowed = allowed.get(device.blueprint_id) if device.blueprint_id else None

    # ---- lookups ---------------------------------------------------------
    def device_present(self, device_id: str) -> bool:
        return self.get_device(device_id) is not None

    def get_device(self, device_id: str) -> JamfNowDevice | None:
        if not self.data:
            return None
        for device in self.data.devices:
            if device.id == device_id:
                return device
        return None

    def blueprint_name(self, blueprint_id: str | None) -> str | None:
        if not blueprint_id or not self.data:
            return blueprint_id
        for blueprint in self.data.blueprints:
            if str(blueprint.id) == str(blueprint_id):
                return blueprint.name
        return blueprint_id

    # ---- refresh helpers -------------------------------------------------
    async def async_refresh_after_command(self) -> None:
        """Refresh now and again shortly after, so status changes show up quickly."""
        await self.async_request_refresh()
        self._cancel_timers()
        self._refresh_timers = [
            async_call_later(self.hass, delay, self._scheduled_refresh) for delay in (15, 60)
        ]

    async def _scheduled_refresh(self, _now) -> None:
        await self.async_request_refresh()

    def _adjust_interval(self, devices: list[JamfNowDevice]) -> None:
        pending = any(d.lost_mode in {"PENDING", "REMOVING"} for d in devices)
        self.update_interval = timedelta(
            seconds=FAST_UPDATE_INTERVAL_SECONDS if pending else UPDATE_INTERVAL_SECONDS
        )

    def _cancel_timers(self) -> None:
        for cancel in self._refresh_timers:
            cancel()
        self._refresh_timers = []

    async def async_shutdown(self) -> None:
        """Stop polling and pending follow-up refreshes (called when the entry unloads)."""
        self._cancel_timers()
        await super().async_shutdown()

    # ---- commands --------------------------------------------------------
    def _require_supervised(self, device_id: str) -> None:
        device = self.get_device(device_id)
        if device and device.supervised is False:
            raise HomeAssistantError("Lost Mode is only available for supervised devices")

    async def _call(self, coro) -> None:
        try:
            await coro
        except JamfNowError as err:
            raise HomeAssistantError(f"Jamf Now command failed: {err}") from err

    def lost_mode_text(self, device_id: str) -> tuple[str, str]:
        settings = self.lost_mode_settings.get(device_id, {})
        return settings.get("message") or DEFAULT_LOST_MESSAGE, settings.get("phone") or ""

    async def async_enable_lost_mode(
        self,
        device_id: str,
        message: str | None = None,
        phone: str | None = None,
        footnote: str | None = None,
        play_sound: bool | None = None,
        clear_passcode: bool = True,
    ) -> None:
        self._require_supervised(device_id)
        if clear_passcode:
            await self._clear_passcode_first(device_id)
        saved_message, saved_phone = self.lost_mode_text(device_id)
        await self._call(
            self.client.async_enable_lost_mode(
                device_id,
                message=message or saved_message,
                phone=phone if phone is not None else saved_phone,
                footnote=footnote,
                play_sound=play_sound,
            )
        )
        await self.async_refresh_after_command()

    async def _clear_passcode_first(self, device_id: str) -> None:
        await self._call(self.client.async_remove_passcode(device_id))
        await asyncio.sleep(CLEAR_PASSCODE_DELAY)

    async def async_clear_passcode(self, device_id: str) -> None:
        await self._call(self.client.async_remove_passcode(device_id))
        await self.async_refresh_after_command()

    async def async_disable_lost_mode(self, device_id: str) -> None:
        self._require_supervised(device_id)
        await self._call(self.client.async_disable_lost_mode(device_id))
        await self.async_refresh_after_command()

    async def _wait_for_lost_mode(self, device_id: str, wanted: set[str]) -> str | None:
        """Poll the device until its Lost Mode status is one of ``wanted``."""
        status: str | None = None
        waited = 0
        while True:
            try:
                state = await self.client.async_get_device_state(device_id)
            except JamfNowError as err:
                raise HomeAssistantError(f"Could not read Lost Mode status: {err}") from err
            status = state.lost_mode if state else None
            if status in wanted or waited >= LOST_MODE_WAIT_TIMEOUT:
                return status
            await asyncio.sleep(LOST_MODE_POLL_INTERVAL)
            waited += LOST_MODE_POLL_INTERVAL

    async def async_play_sound(self, device_id: str) -> None:
        """Play the Lost Mode sound; enables Lost Mode first when it is not on."""
        self._require_supervised(device_id)
        try:
            state = await self.client.async_get_device_state(device_id)
        except JamfNowError as err:
            raise HomeAssistantError(f"Could not read Lost Mode status: {err}") from err
        status = state.lost_mode if state else None

        if status == "REMOVING":
            # Wait for the disable to finish before turning it on again
            status = await self._wait_for_lost_mode(device_id, {"DISABLED"})
            if status != "DISABLED":
                raise HomeAssistantError(
                    "Lost Mode is still being removed (the device has not confirmed it); "
                    "sound was not played and Lost Mode was not re-enabled"
                )
        if status not in LOST_MODE_ON:
            message, phone = self.lost_mode_text(device_id)
            await self._clear_passcode_first(device_id)
            await self._call(
                self.client.async_enable_lost_mode(device_id, message=message, phone=phone)
            )
            status = "PENDING"
        if status != "ENABLED":
            status = await self._wait_for_lost_mode(device_id, {"ENABLED"})
        if status != "ENABLED":
            await self.async_refresh_after_command()
            raise HomeAssistantError(
                "Lost Mode was not confirmed by the device in time; sound was not played"
            )
        await self._call(self.client.async_play_lost_mode_sound(device_id))
        await self.async_refresh_after_command()

    def _block_during_lost_mode(self, device_id: str) -> None:
        """Restart/power off can drop Wi-Fi and strand a device in Lost Mode."""
        if self.is_lost_mode_active(device_id):
            raise HomeAssistantError(
                "Not allowed while Lost Mode is on or pending removal: the device could lose "
                "Wi-Fi and then never receive the command that disables Lost Mode"
            )

    def is_lost_mode_active(self, device_id: str) -> bool:
        device = self.get_device(device_id)
        return bool(device and device.lost_mode in LOST_MODE_ACTIVE)

    async def async_set_app_store(self, device_id: str, allowed: bool) -> None:
        """Allow/block the App Store. This changes the device's blueprint, so it affects every
        device that uses the same blueprint."""
        # Re-read first so the device's blueprint is current, not up to 5 minutes old
        await self.async_refresh()
        device = self.get_device(device_id)
        if not device or not device.blueprint_id:
            raise HomeAssistantError("The device has no blueprint, so the App Store cannot be changed")
        blueprint_id = device.blueprint_id
        await self._call(self.client.async_set_app_store_allowed(blueprint_id, allowed))
        # Verify that this device's blueprint (and only it) now has the wanted value
        try:
            restrictions = await self.client.async_get_restrictions(blueprint_id)
        except JamfNowError as err:
            raise HomeAssistantError(f"Could not verify the App Store change: {err}") from err
        if self.client.app_store_allowed(restrictions) != allowed:
            raise HomeAssistantError("Jamf Now did not apply the App Store change")
        await self.async_refresh_after_command()

    async def async_restart(self, device_id: str) -> None:
        self._block_during_lost_mode(device_id)
        await self._call(self.client.async_restart_device(device_id))
        await self.async_refresh_after_command()

    async def async_power_off(self, device_id: str) -> None:
        self._block_during_lost_mode(device_id)
        await self._call(self.client.async_shutdown_device(device_id))
        await self.async_refresh_after_command()

    async def async_sync_inventory(self, device_id: str) -> None:
        await self._call(self.client.async_sync_inventory(device_id))
        await self.async_refresh_after_command()

    async def async_set_blueprint(self, device_id: str, blueprint_id: str) -> None:
        await self._call(self.client.async_set_blueprint(device_id, blueprint_id))
        await self.async_refresh_after_command()
