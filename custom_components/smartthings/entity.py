"""Support for SmartThings Cloud."""
from __future__ import annotations

import json
import logging

from pysmartthings import Capability, DeviceEntity, RoomEntity

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity, EntityDescription

from .const import DEVICE_INFO_MAP, DOMAIN, SIGNAL_SMARTTHINGS_UPDATE

_LOGGER = logging.getLogger(__name__)


class SmartThingsEntity(Entity):
    """Defines a SmartThings entity."""

    _attr_should_poll = False

    def __init__(
        self,
        device: DeviceEntity,
        capability: Capability,
        description: EntityDescription,
        room: RoomEntity,
    ) -> None:
        """Initialize the instance."""
        self._device = device
        self._dispatcher_remove = None
        self._capability = capability
        self._room = room
        self.entity_description = description
        _LOGGER.debug(
            "Device status attributes:\n - device: %s\n - attributes: %s",
            self._device.label,
            json.dumps(self._device.status.attributes),
        )
        for id, status in self._device.status.components.items():
            _LOGGER.debug(
                "Device status component:\n - device: %s\n - component: %s\n - attributes: %s",
                self._device.label,
                id,
                json.dumps(status.attributes),
            )

    async def async_added_to_hass(self):
        """Device added to hass."""

        async def async_update_state(devices):
            """Update device state."""
            if self._device.device_id in devices:
                await self.async_update_ha_state(True)

        self._dispatcher_remove = async_dispatcher_connect(
            self.hass, SIGNAL_SMARTTHINGS_UPDATE, async_update_state
        )

    async def async_will_remove_from_hass(self) -> None:
        """Disconnect the device when removed."""
        if self._dispatcher_remove:
            self._dispatcher_remove()

    @property
    def device_info(self) -> DeviceInfo:
        """Get attributes about the device."""
        name = self._device.name
        manufacturer, model = DEVICE_INFO_MAP.get(name, ("Unknown", name))

        return DeviceInfo(
            configuration_url="https://account.smartthings.com",
            identifiers={(DOMAIN, self._device.device_id)},
            manufacturer=manufacturer,
            model=model,
            name=self._device.label,
            suggested_area=self._room.name,
        )

    @property
    def name(self) -> str:
        """Return the name of the device."""
        label = self._device.label
        if name := self.entity_description.name:
            return f"{label} {name}"
        return label

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        device_id = self._device.device_id
        platform = self.platform.platform_name
        return f"{device_id}-{platform}-{self.entity_description.key}"

    @property
    def extra_state_attributes(self):
        """Return device specific state attributes."""
        state_attrs = {}
        return state_attrs
