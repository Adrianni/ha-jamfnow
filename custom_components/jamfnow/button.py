"""Action buttons: play sound and restart."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import JamfNowDataUpdateCoordinator
from .entity import JamfNowEntity, async_setup_device_entities


@dataclass(frozen=True, kw_only=True)
class JamfNowButtonDescription(ButtonEntityDescription):
    """Describes one Jamf Now button."""

    press_fn: Callable[[JamfNowDataUpdateCoordinator, str], Awaitable[None]]


BUTTON_DESCRIPTIONS: tuple[JamfNowButtonDescription, ...] = (
    JamfNowButtonDescription(
        key="play_sound",
        translation_key="play_sound",
        press_fn=lambda coordinator, device_id: coordinator.async_play_sound(device_id),
    ),
    JamfNowButtonDescription(
        key="restart",
        translation_key="restart",
        device_class=ButtonDeviceClass.RESTART,
        press_fn=lambda coordinator, device_id: coordinator.async_restart(device_id),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_setup_device_entities(
        entry,
        async_add_entities,
        lambda coordinator, device_id: [
            JamfNowButton(coordinator, device_id, description) for description in BUTTON_DESCRIPTIONS
        ],
    )


class JamfNowButton(JamfNowEntity, ButtonEntity):
    """Sends one command to a Jamf Now device."""

    entity_description: JamfNowButtonDescription

    def __init__(
        self,
        coordinator: JamfNowDataUpdateCoordinator,
        device_id: str,
        description: JamfNowButtonDescription,
    ) -> None:
        super().__init__(coordinator, device_id, f"{description.key}_button")
        self.entity_description = description

    async def async_press(self) -> None:
        await self.entity_description.press_fn(self.coordinator, self._device_id)
