"""Support for binary sensor entities through the SmartThings cloud API."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pysmartthings import Attribute, Capability

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DATA_BROKERS,
    DOMAIN,
    CustomAttribute,
    CustomCapability,
)
from .entity import SmartThingsEntity

@dataclass
class SmartThingsBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Class to describe a SmartThings binary sensor entity."""

    entity_category: str[EntityCategory] | None = EntityCategory.DIAGNOSTIC
    is_on: Callable[[Any], bool] = lambda value: value

BINARY_SENSOR_DESCRIPTIONS: dict[str, list[SmartThingsBinarySensorEntityDescription]] = {
    Capability.lock: [
        SmartThingsBinarySensorEntityDescription(
            key=Attribute.lock,
            name="Status",
            device_class=BinarySensorDeviceClass.LOCK,
            is_on=lambda value: bool(value == "unlocked"),
        ),
    ],
    Capability.tamper_alert: [
        SmartThingsBinarySensorEntityDescription(
            key=Attribute.tamper,
            name="Tamper Detected",
            device_class=BinarySensorDeviceClass.TAMPER,
            is_on=lambda value: bool(value == "detected"),
        ),
    ],
    Capability.water_sensor: [
        SmartThingsBinarySensorEntityDescription(
            key=Attribute.water,
            name="Water Detected",
            device_class=BinarySensorDeviceClass.MOISTURE,
            is_on=lambda value: bool(value == "wet"),
        ),
    ],
    CustomCapability.door_state: [
        SmartThingsBinarySensorEntityDescription(
            key=CustomAttribute.door_state,
            name="Door State",
            device_class=BinarySensorDeviceClass.DOOR,
            is_on=lambda value: bool(value == "open"),
        ),
    ],
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add binary sensor entities for a config entry."""
    broker = hass.data[DOMAIN][DATA_BROKERS][config_entry.entry_id]
    entities: list[SmartThingsBinarySensorEntity] = []
    for device in broker.devices.values():
        room = broker.rooms[device.room_id]
        for capability in broker.get_capabilities(device):
            if attributes := BINARY_SENSOR_DESCRIPTIONS.get(capability):
                for attribute in attributes:
                    entities.append(
                        SmartThingsBinarySensorEntity(
                            device, capability, attribute, room,
                        )
                    )

    async_add_entities(entities)


class SmartThingsBinarySensorEntity(SmartThingsEntity, BinarySensorEntity):
    """Define a SmartThings binary sensor entity."""

    entity_description: SmartThingsBinarySensorEntityDescription

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        value = self._device.status.attributes[self.entity_description.key].value
        return self.entity_description.is_on(value)
