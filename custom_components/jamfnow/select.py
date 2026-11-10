"""Blueprint selection per device."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
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
        lambda coordinator, device_id: [JamfNowBlueprintSelect(coordinator, device_id)],
    )


class JamfNowBlueprintSelect(JamfNowEntity, SelectEntity):
    """Assign the device to another Jamf Now blueprint."""

    _attr_translation_key = "blueprint_select"

    def __init__(self, coordinator: JamfNowDataUpdateCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "blueprint_select")

    @property
    def options(self) -> list[str]:
        if not self.coordinator.data:
            return []
        return [self._format_option(bp.name, bp.id) for bp in self.coordinator.data.blueprints]

    @property
    def current_option(self) -> str | None:
        device = self.device
        if not device or not device.blueprint_id or not self.coordinator.data:
            return None
        for bp in self.coordinator.data.blueprints:
            if str(bp.id) == str(device.blueprint_id):
                return self._format_option(bp.name, bp.id)
        return None

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_blueprint(self._device_id, self._parse_option(option))

    @staticmethod
    def _format_option(name: str, blueprint_id: str) -> str:
        return f"{name} ({blueprint_id})"

    @staticmethod
    def _parse_option(option: str) -> str:
        if option.endswith(")") and "(" in option:
            return option.rsplit("(", 1)[-1].rstrip(")")
        return option
