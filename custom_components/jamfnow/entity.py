"""Shared entity base and helpers for Jamf Now."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import JamfNowDevice
from .const import DOMAIN
from .coordinator import JamfNowDataUpdateCoordinator


class JamfNowEntity(CoordinatorEntity[JamfNowDataUpdateCoordinator]):
    """Base class: ties an entity to one Jamf Now device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: JamfNowDataUpdateCoordinator, device_id: str, key: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{device_id}_{key}"

    @property
    def device(self) -> JamfNowDevice | None:
        return self.coordinator.get_device(self._device_id)

    @property
    def available(self) -> bool:
        return super().available and self.device is not None

    @property
    def device_info(self) -> DeviceInfo:
        device = self.device
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device.name if device else "Jamf Now device",
            manufacturer="Apple",
            model=device.model_name or device.model if device else None,
            model_id=device.model if device else None,
            serial_number=device.serial_number if device else None,
            sw_version=device.os_version if device else None,
        )


@callback
def async_setup_device_entities(
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    factory: Callable[[JamfNowDataUpdateCoordinator, str], Iterable[Entity]],
) -> None:
    """Create entities for all devices now, and for devices that appear later."""
    coordinator: JamfNowDataUpdateCoordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new_devices() -> None:
        if not coordinator.data:
            return
        new_ids = [d.id for d in coordinator.data.devices if d.id not in known]
        if not new_ids:
            return
        known.update(new_ids)
        async_add_entities([e for device_id in new_ids for e in factory(coordinator, device_id)])

    _add_new_devices()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_devices))
