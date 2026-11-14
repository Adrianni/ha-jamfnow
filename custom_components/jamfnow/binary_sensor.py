"""Whether Lost Mode can be turned on (the blueprint must allow passcode changes)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import JamfNowDataUpdateCoordinator
from .entity import JamfNowEntity, async_setup_device_entities


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_setup_device_entities(
        entry,
        async_add_entities,
        lambda coordinator, device_id: [JamfNowLostModeAvailableSensor(coordinator, device_id)],
    )


class JamfNowLostModeAvailableSensor(JamfNowEntity, BinarySensorEntity):
    """On = Lost Mode can be turned on. Off = the blueprint has "Prevent changes to passcode" on."""

    _attr_translation_key = "lost_mode_available"

    def __init__(self, coordinator: JamfNowDataUpdateCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "passcode_change_blocked")  # unique id kept

    @property
    def is_on(self) -> bool | None:
        device = self.device
        if not device or device.passcode_change_allowed is None:
            return None
        return device.passcode_change_allowed

    @property
    def extra_state_attributes(self) -> dict[str, str | None] | None:
        device = self.device
        if not device:
            return None
        attrs: dict[str, str | None] = {
            "blueprint": self.coordinator.blueprint_name(device.blueprint_id)
        }
        if device.passcode_change_allowed is False:
            attrs["reason"] = (
                "The blueprint has 'Prevent changes to passcode' turned on. Turn it off in "
                "Jamf Now (Blueprint > Restrictions > Security & Privacy)"
            )
        return attrs
