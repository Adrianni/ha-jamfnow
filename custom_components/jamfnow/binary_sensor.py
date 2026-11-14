"""Why Lost Mode cannot be enabled: the blueprint prevents passcode changes."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
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
        lambda coordinator, device_id: [JamfNowPasscodeBlockedSensor(coordinator, device_id)],
    )


class JamfNowPasscodeBlockedSensor(JamfNowEntity, BinarySensorEntity):
    """On (problem) when "Prevent changes to passcode" is on, which blocks Lost Mode."""

    _attr_translation_key = "passcode_change_blocked"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: JamfNowDataUpdateCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "passcode_change_blocked")

    @property
    def is_on(self) -> bool | None:
        device = self.device
        if not device or device.passcode_change_allowed is None:
            return None
        return not device.passcode_change_allowed

    @property
    def extra_state_attributes(self) -> dict[str, str | None] | None:
        device = self.device
        if not device:
            return None
        return {"blueprint": self.coordinator.blueprint_name(device.blueprint_id)}
