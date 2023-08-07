"""Support for fan entities through the SmartThings cloud API."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityDescription, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.percentage import (
    int_states_in_range,
    percentage_to_ranged_value,
    ranged_value_to_percentage,
)

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
class SmartThingsFanEntityDescription(FanEntityDescription):
    """Class to describe a SmartThings fan entity."""

FAN_DESCRIPTIONS: dict[str, list[SmartThingsFanEntityDescription]] = {
    CustomCapability.hood_fan_speed: [
        SmartThingsFanEntityDescription(
            key=CustomAttribute.hood_fan_speed,
            name="Exhaust Fan",
        ),
    ],
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add fan entities for a config entry."""
    broker = hass.data[DOMAIN][DATA_BROKERS][config_entry.entry_id]
    entities: list[SmartThingsFanEntity] = []
    for device in broker.devices.values():
        room = broker.rooms[device.room_id]
        for capability in broker.get_capabilities(device):
            if attributes := FAN_DESCRIPTIONS.get(capability):
                for attribute in attributes:
                    entities.append(
                        SmartThingsFanEntity(
                            device, capability, attribute, room,
                        )
                    )

    async_add_entities(entities)


class SmartThingsFanEntity(SmartThingsEntity, FanEntity):
    """Define a SmartThings fan entity."""

    _attr_supported_features = FanEntityFeature.SET_SPEED
    entity_description: SmartThingsFanEntityDescription

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the speed percentage of the fan."""
        await self._async_set_percentage(percentage)

    async def _async_set_percentage(self, percentage: int | None) -> None:
        if percentage is None:
            speed = self._speed_range[1]
        elif percentage == 0:
            speed = 0
        else:
            speed = math.ceil(percentage_to_ranged_value(self._speed_range, percentage))
        result = await self._device.command(
            CustomComponent.hood,
            self._capability,
            "setHoodFanSpeed",
            [speed],
        )
        if result:
            self._device.status.components[CustomComponent.hood].update_attribute_value(self.entity_description.key, speed)
        # State is set optimistically in the command above, therefore update
        # the entity state ahead of receiving the confirming push updates
        self.async_write_ha_state()

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn the fan on."""
        await self._async_set_percentage(percentage)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the fan off."""
        await self._async_set_percentage(0)

    @property
    def is_on(self) -> bool:
        """Return true if fan is on."""
        return bool(self._speed)

    @property
    def percentage(self) -> int:
        """Return the current speed percentage."""
        return ranged_value_to_percentage(self._speed_range, self._speed)

    @property
    def speed_count(self) -> int:
        """Return the number of speeds the fan supports."""
        return int_states_in_range(self._speed_range)

    @property
    def _speed(self) -> int:
        """Return true if fan is on."""
        return self._device.status.components[CustomComponent.hood].attributes[self.entity_description.key].value

    @property
    def _speed_list(self) -> list[int]:
        """Return valid speeds."""
        speed_list = self._device.status.components[CustomComponent.hood].attributes[CustomAttribute.supported_hood_fan_speed].value
        max_speed = self._device.status.components[CustomComponent.hood].attributes[CustomAttribute.max_fan_speed].value
        min_speed = self._device.status.components[CustomComponent.hood].attributes[CustomAttribute.min_fan_speed].value
        return [speed for speed in speed_list if (speed > min_speed and speed <= max_speed)]

    @property
    def _speed_range(self) -> tuple[int, int]:
        """Return speed range."""
        return (min(self._speed_list), max(self._speed_list))
