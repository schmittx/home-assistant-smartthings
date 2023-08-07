"""Support for select entities through the SmartThings cloud API."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SmartThingsEntity
from .const import (
    DATA_BROKERS,
    DOMAIN,
    CustomAttribute,
    CustomCapability,
    CustomComponent,
)

HOOD_FAN_SPEED_TO_STATE = {
    "0": "off",
    "1": "low",
    "2": "medium",
    "3": "high",
}

STATE_TO_HOOD_FAN_SPEED = {value: key for key, value in HOOD_FAN_SPEED_TO_STATE.items()}

@dataclass
class SmartThingsSelectEntityDescription(SelectEntityDescription):
    """Class to describe a SmartThings select entity."""

    entity_category: str[EntityCategory] | None = EntityCategory.CONFIG
    component: CustomComponent | None = None
    current_option: Callable[[Any], bool] = lambda value: value
    select_option: str | None = None
    translation_key: str | None = "all"

SELECT_DESCRIPTIONS: dict[str, list[SmartThingsSelectEntityDescription]] = {
    CustomCapability.hood_fan_speed: [
        SmartThingsSelectEntityDescription(
            key=CustomAttribute.hood_fan_speed,
            name="Hood Fan Speed",
            component=CustomComponent.hood,
            options=CustomAttribute.supported_hood_fan_speed,
            current_option=lambda value: HOOD_FAN_SPEED_TO_STATE.get(str(value), str(value)),
            select_option="setHoodFanSpeed",
        ),
    ],
    CustomCapability.lamp: [
        SmartThingsSelectEntityDescription(
            key=CustomAttribute.brightness_level,
            name="Lamp Brightness Level",
            component=CustomComponent.hood,
            options=CustomAttribute.supported_brightness_level,
            select_option="setBrightnessLevel",
        ),
    ],
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add select entities for a config entry."""
    broker = hass.data[DOMAIN][DATA_BROKERS][config_entry.entry_id]
    entities: list[SmartThingsSelectEntity] = []
    for device in broker.devices.values():
        room = broker.rooms[device.room_id]
        for capability in broker.get_capabilities(device):
            if attributes := SELECT_DESCRIPTIONS.get(capability):
                for attribute in attributes:
                    entities.append(
                        SmartThingsSelectEntity(
                            device, capability, attribute, room,
                        )
                    )

    async_add_entities(entities)


class SmartThingsSelectEntity(SmartThingsEntity, SelectEntity):
    """Define a SmartThings select entity."""

    entity_description: SmartThingsSelectEntityDescription

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if self.entity_description.key == CustomAttribute.hood_fan_speed:
            option = int(STATE_TO_HOOD_FAN_SPEED[option])
        result = await self._device.command(
            self.entity_description.component,
            self._capability,
            self.entity_description.select_option,
            [option],
        )
        if result:
            self._device.status.components[self.entity_description.component].update_attribute_value(self.entity_description.key, option)
        # State is set optimistically in the command above, therefore update
        # the entity state ahead of receiving the confirming push updates
        self.async_write_ha_state()

    @property
    def options(self) -> list[str]:
        """Return valid options."""
        options = self._device.status.components[self.entity_description.component].attributes[self.entity_description.options].value
        if self.entity_description.key == CustomAttribute.hood_fan_speed:
            min_speed = self._device.status.components[self.entity_description.component].attributes[CustomAttribute.min_fan_speed].value
            max_speed = self._device.status.components[self.entity_description.component].attributes[CustomAttribute.max_fan_speed].value
            return [HOOD_FAN_SPEED_TO_STATE[str(option)] for option in options if option >= min_speed and option <= max_speed]
        return options

    @property
    def current_option(self) -> str | None:
        """Return current option."""
        option = self._device.status.components[self.entity_description.component].attributes[self.entity_description.key].value
        return self.entity_description.current_option(option)

