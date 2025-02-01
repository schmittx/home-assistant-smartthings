"""Support for light entities through the SmartThings cloud API."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.fan import ATTR_PERCENTAGE_STEP
from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity, LightEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item,
)

from .const import (
    DATA_BROKERS,
    DOMAIN,
    CustomAttribute,
    CustomCapability,
    CustomComponent,
)
from .entity import SmartThingsEntity

@dataclass
class SmartThingsLightEntityDescription(LightEntityDescription):
    """Class to describe a SmartThings light entity."""

LIGHT_DESCRIPTIONS: dict[str, list[SmartThingsLightEntityDescription]] = {
    CustomCapability.lamp: [
        SmartThingsLightEntityDescription(
            key=CustomAttribute.brightness_level,
            name="Light",
        ),
    ],
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add light entities for a config entry."""
    broker = hass.data[DOMAIN][DATA_BROKERS][config_entry.entry_id]
    entities: list[SmartThingsLightEntity] = []
    for device in broker.devices.values():
        room = broker.rooms[device.room_id]
        for capability in broker.get_capabilities(device):
            if attributes := LIGHT_DESCRIPTIONS.get(capability):
                for attribute in attributes:
                    entities.append(
                        SmartThingsLightEntity(
                            device, capability, attribute, room,
                        )
                    )

    async_add_entities(entities)


class SmartThingsLightEntity(SmartThingsEntity, LightEntity):
    """Define a SmartThings light entity."""

    _attr_color_mode: ColorMode | str | None = ColorMode.BRIGHTNESS
    _attr_supported_color_modes: set[ColorMode] | set[str] | None = set([ColorMode.BRIGHTNESS])
    entity_description: SmartThingsLightEntityDescription

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        brightness_level = percentage_to_ordered_list_item(
            self._brightness_levels,
            int(kwargs.get(ATTR_BRIGHTNESS, 255) * 100 / 255),
        )
        await self._async_set_brightness_level(brightness_level)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        await self._async_set_brightness_level("off")

    async def _async_set_brightness_level(self, brightness: str | None) -> None:
        result = await self._device.command(
            CustomComponent.hood,
            self._capability,
            "setBrightnessLevel",
            [brightness],
        )
        if result:
            self._device.status.components[CustomComponent.hood].update_attribute_value(self.entity_description.key, brightness)
        # State is set optimistically in the command above, therefore update
        # the entity state ahead of receiving the confirming push updates
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        return bool(self._brightness_level != "off")

    @property
    def brightness(self) -> int | None:
        """Return the brightness of this light between 0..255."""
        if self._brightness_level == "off":
            return 0
        return int((ordered_list_item_to_percentage(self._brightness_levels, self._brightness_level) / 100) * 255)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return device specific state attributes."""
        state_attrs = super().extra_state_attributes
        state_attrs[ATTR_PERCENTAGE_STEP] = 100 / len(self._brightness_levels)
        return state_attrs

    @property
    def _brightness_level(self) -> str:
        """Return brightness level."""
        return self._device.status.components[CustomComponent.hood].attributes[self.entity_description.key].value

    @property
    def _brightness_levels(self) -> list[str]:
        """Return valid brightness levels."""
        brightness_levels = self._device.status.components[CustomComponent.hood].attributes[CustomAttribute.supported_brightness_level].value
        return [level for level in brightness_levels if level != "off"]
