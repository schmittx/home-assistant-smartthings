"""Support for event entities through the SmartThings cloud API."""
from __future__ import annotations

from dataclasses import dataclass

from pysmartthings import Attribute, Capability

from homeassistant.components.event import (
    EventDeviceClass,
    EventEntity,
    EventEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DATA_BROKERS,
    DOMAIN,
    SIGNAL_SMARTTHINGS_BUTTON,
)
from .entity import SmartThingsEntity

@dataclass
class SmartThingsEventEntityDescription(EventEntityDescription):
    """Class to describe a SmartThings event entity."""

    entity_category: str[EntityCategory] | None = EntityCategory.DIAGNOSTIC

EVENT_DESCRIPTIONS: dict[str, list[SmartThingsEventEntityDescription]] = {
    Capability.button: [
        SmartThingsEventEntityDescription(
            key=Attribute.button,
            name="Pressed",
            device_class=EventDeviceClass.BUTTON,
            event_types=["pushed", "double", "held"],
        ),
    ],
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add event entities for a config entry."""
    broker = hass.data[DOMAIN][DATA_BROKERS][config_entry.entry_id]
    entities: list[SmartThingsEventEntity] = []
    for device in broker.devices.values():
        room = broker.rooms[device.room_id]
        for capability in broker.get_capabilities(device):
            if attributes := EVENT_DESCRIPTIONS.get(capability):
                for attribute in attributes:
                    entities.append(
                        SmartThingsEventEntity(
                            device, capability, attribute, room,
                        )
                    )

    async_add_entities(entities)


class SmartThingsEventEntity(SmartThingsEntity, EventEntity):
    """Define a SmartThings event entity."""

    entity_description: SmartThingsEventEntityDescription

    async def async_added_to_hass(self):
        """Device added to hass."""

        async def async_handle_event(devices):
            """Handle device event."""
            if self._device.device_id in devices:
                event_type = self._device.status.attributes[self.entity_description.key].value
                self._trigger_event(event_type)
                self.async_write_ha_state()

        self._dispatcher_remove = async_dispatcher_connect(
            self.hass, SIGNAL_SMARTTHINGS_BUTTON, async_handle_event
        )
