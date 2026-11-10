"""Lock screen message and phone number used when Lost Mode is enabled."""

from __future__ import annotations

from homeassistant.components.text import TextEntity, TextEntityDescription, TextMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .api import DEFAULT_LOST_MESSAGE
from .coordinator import JamfNowDataUpdateCoordinator
from .entity import JamfNowEntity, async_setup_device_entities

TEXT_DESCRIPTIONS: tuple[TextEntityDescription, ...] = (
    TextEntityDescription(
        key="lost_mode_message",
        translation_key="lost_mode_message",
        entity_category=EntityCategory.CONFIG,
        native_max=250,
        mode=TextMode.TEXT,
    ),
    TextEntityDescription(
        key="lost_mode_phone",
        translation_key="lost_mode_phone",
        entity_category=EntityCategory.CONFIG,
        native_max=30,
        mode=TextMode.TEXT,
    ),
)

DEFAULTS = {"lost_mode_message": DEFAULT_LOST_MESSAGE, "lost_mode_phone": ""}
SETTING_KEYS = {"lost_mode_message": "message", "lost_mode_phone": "phone"}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_setup_device_entities(
        entry,
        async_add_entities,
        lambda coordinator, device_id: [
            JamfNowLostModeText(coordinator, device_id, description) for description in TEXT_DESCRIPTIONS
        ],
    )


class JamfNowLostModeText(JamfNowEntity, RestoreEntity, TextEntity):
    """Lock screen text. Sent to the device the next time Lost Mode is turned on."""

    entity_description: TextEntityDescription

    def __init__(
        self,
        coordinator: JamfNowDataUpdateCoordinator,
        device_id: str,
        description: TextEntityDescription,
    ) -> None:
        super().__init__(coordinator, device_id, description.key)
        self.entity_description = description
        self._value = DEFAULTS[description.key]
        self._apply()

    def _apply(self) -> None:
        settings = self.coordinator.lost_mode_settings.setdefault(self._device_id, {})
        settings[SETTING_KEYS[self.entity_description.key]] = self._value

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) and last.state not in (None, "unknown", "unavailable"):
            self._value = last.state
            self._apply()

    @property
    def native_value(self) -> str:
        return self._value

    async def async_set_value(self, value: str) -> None:
        self._value = value
        self._apply()
        self.async_write_ha_state()
