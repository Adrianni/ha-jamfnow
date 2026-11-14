"""Lost Mode switch."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import LOST_MODE_ACTIVE, JamfNowDataUpdateCoordinator
from .entity import JamfNowEntity, async_setup_device_entities


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_setup_device_entities(
        entry,
        async_add_entities,
        lambda coordinator, device_id: [
            JamfNowLostModeSwitch(coordinator, device_id),
            JamfNowAppStoreSwitch(coordinator, device_id),
        ],
    )


class JamfNowLostModeSwitch(JamfNowEntity, SwitchEntity):
    """Turns managed Lost Mode on/off, using the lock screen message set in the text entities."""

    _attr_translation_key = "lost_mode_switch"

    def __init__(self, coordinator: JamfNowDataUpdateCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "lost_mode_switch")

    @property
    def is_on(self) -> bool | None:
        device = self.device
        if not device or device.lost_mode is None:
            return None
        return device.lost_mode in LOST_MODE_ACTIVE

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        device = self.device
        return {"lost_mode_status": device.lost_mode} if device else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_enable_lost_mode(self._device_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_disable_lost_mode(self._device_id)


class JamfNowAppStoreSwitch(JamfNowEntity, SwitchEntity):
    """On = App Store allowed. Changes the blueprint, so every device on it is affected."""

    _attr_translation_key = "app_store_switch"

    def __init__(self, coordinator: JamfNowDataUpdateCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "app_store_switch")

    @property
    def is_on(self) -> bool | None:
        device = self.device
        return device.app_store_allowed if device else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        device = self.device
        if not device:
            return None
        return {
            "blueprint": self.coordinator.blueprint_name(device.blueprint_id),
            "blueprint_id": device.blueprint_id,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_app_store(self._device_id, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_app_store(self._device_id, False)
