"""Last known location of a device (reported by Lost Mode)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
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
        lambda coordinator, device_id: [JamfNowLocationTracker(coordinator, device_id)],
    )


class JamfNowLocationTracker(JamfNowEntity, TrackerEntity):
    """Position from Jamf Now. Only known after Lost Mode has located the device."""

    _attr_translation_key = "location"
    _attr_source_type = SourceType.GPS

    def __init__(self, coordinator: JamfNowDataUpdateCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "location")

    @property
    def latitude(self) -> float | None:
        return self.device.latitude if self.device else None

    @property
    def longitude(self) -> float | None:
        return self.device.longitude if self.device else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        device = self.device
        if not device or not device.location_time:
            return None
        return {"location_time": device.location_time.isoformat()}
