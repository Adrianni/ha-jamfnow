"""Status sensors for Jamf Now devices."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import JamfNowDevice
from .coordinator import JamfNowDataUpdateCoordinator
from .entity import JamfNowEntity, async_setup_device_entities


@dataclass(frozen=True, kw_only=True)
class JamfNowSensorDescription(SensorEntityDescription):
    """Describes one Jamf Now sensor."""

    value_fn: Callable[[JamfNowDevice, JamfNowDataUpdateCoordinator], str | int | datetime | None]
    attrs_fn: Callable[[JamfNowDevice], dict[str, Any]] | None = None


def _supervised(device: JamfNowDevice, _c: JamfNowDataUpdateCoordinator) -> str | None:
    if device.supervised is None:
        return None
    return "SUPERVISED" if device.supervised else "UNSUPERVISED"


def _profile(key: str) -> Callable[[JamfNowDevice, JamfNowDataUpdateCoordinator], str | None]:
    return lambda device, _c: device.profiles.get(key)


SENSOR_DESCRIPTIONS: tuple[JamfNowSensorDescription, ...] = (
    JamfNowSensorDescription(
        key="status",
        translation_key="status",
        value_fn=lambda d, _c: d.status,
    ),
    JamfNowSensorDescription(
        key="os_version",
        translation_key="os_version",
        value_fn=lambda d, _c: d.os_version,
    ),
    JamfNowSensorDescription(
        key="blueprint",
        translation_key="blueprint",
        value_fn=lambda d, c: c.blueprint_name(d.blueprint_id),
    ),
    JamfNowSensorDescription(
        key="last_check_in",
        translation_key="last_check_in",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d, _c: d.last_check_in,
    ),
    JamfNowSensorDescription(
        key="last_inventory",
        translation_key="last_inventory",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d, _c: d.last_inventory,
    ),
    JamfNowSensorDescription(
        key="lost_mode",
        translation_key="lost_mode",
        value_fn=lambda d, _c: d.lost_mode,
    ),
    JamfNowSensorDescription(
        key="lost_mode_sound",
        translation_key="lost_mode_sound",
        value_fn=lambda d, _c: d.lost_mode_sound,
    ),
    JamfNowSensorDescription(
        key="supervised",
        translation_key="supervised",
        value_fn=_supervised,
    ),
    JamfNowSensorDescription(
        key="profile_lock_screen_message",
        translation_key="profile_lock_screen_message",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_profile("lockScreenMessage"),
    ),
    JamfNowSensorDescription(
        key="profile_restriction",
        translation_key="profile_restriction",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_profile("restriction"),
    ),
    JamfNowSensorDescription(
        key="profile_wifi",
        translation_key="profile_wifi",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_profile("wifi"),
    ),
    JamfNowSensorDescription(
        key="profile_app_lock",
        translation_key="profile_app_lock",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_profile("appLock"),
    ),
    JamfNowSensorDescription(
        key="profile_email",
        translation_key="profile_email",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_profile("email"),
    ),
    JamfNowSensorDescription(
        key="profile_security",
        translation_key="profile_security",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_profile("security"),
    ),
    JamfNowSensorDescription(
        key="profile_web_clip",
        translation_key="profile_web_clip",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_profile("webClip"),
    ),
    JamfNowSensorDescription(
        key="apps_installed",
        translation_key="apps_installed",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d, _c: len(d.apps),
        attrs_fn=lambda d: {"apps": [f"{a.name} {a.version}".strip() if a.version else a.name for a in d.apps]},
    ),
    JamfNowSensorDescription(
        key="assigned_user",
        translation_key="assigned_user",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d, _c: d.assigned_user,
    ),
    JamfNowSensorDescription(
        key="enrolled",
        translation_key="enrolled",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d, _c: d.enrolled,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_setup_device_entities(
        entry,
        async_add_entities,
        lambda coordinator, device_id: [
            JamfNowSensor(coordinator, device_id, description) for description in SENSOR_DESCRIPTIONS
        ],
    )


class JamfNowSensor(JamfNowEntity, SensorEntity):
    """A status value of a Jamf Now device."""

    entity_description: JamfNowSensorDescription

    def __init__(
        self,
        coordinator: JamfNowDataUpdateCoordinator,
        device_id: str,
        description: JamfNowSensorDescription,
    ) -> None:
        super().__init__(coordinator, device_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> str | int | datetime | None:
        device = self.device
        if not device:
            return None
        return self.entity_description.value_fn(device, self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        device = self.device
        if not device or not self.entity_description.attrs_fn:
            return None
        return self.entity_description.attrs_fn(device)
