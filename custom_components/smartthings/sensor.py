"""Support for sensor entities through the SmartThings cloud API."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pysmartthings import Attribute, Capability

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import SmartThingsEntity
from .const import DATA_BROKERS, DOMAIN

OVEN_MODE_MAP = {
    "Autocook": "autocook",
    "ConvectionBake": "convection_bake",
    "ConvectionRoast": "convection_roast",
    "KeepWarm": "keep_warm",
    "Microwave": "microwave",
    "MicroWave": "microwave",
    "NoOperation": "no_operation",
    "Others": "other",
    "warming": "warming",
    "SpeedBake": "speed_bake",
    "SpeedRoast": "speed_roast",
    "SteamClean": "steam_clean",
}

UNIT_MAP = {
    "C": UnitOfTemperature.CELSIUS,
    "F": UnitOfTemperature.FAHRENHEIT,
    "%": PERCENTAGE,
}

@dataclass
class SmartThingsSensorEntityDescription(SensorEntityDescription):
    """Class to describe a SmartThings sensor entity."""

    entity_category: str[EntityCategory] | None = EntityCategory.DIAGNOSTIC
    native_value: Callable[[Any], bool] = lambda value: value
    translation_key: str | None = "all"

SENSOR_DESCRIPTIONS: dict[str, list[SmartThingsSensorEntityDescription]] = {
    Capability.battery: [
        SmartThingsSensorEntityDescription(
            key=Attribute.battery,
            name="Battery",
            device_class=SensorDeviceClass.BATTERY,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=PERCENTAGE,
        ),
    ],
    Capability.oven_mode: [
        SmartThingsSensorEntityDescription(
            key=Attribute.oven_mode,
            name="Oven Mode",
            native_value=lambda value: OVEN_MODE_MAP.get(value, value),
        ),
    ],
    Capability.oven_operating_state: [
        SmartThingsSensorEntityDescription(
            key=Attribute.completion_time,
            name="Oven Completion Time",
            device_class=SensorDeviceClass.TIMESTAMP,
            native_value=lambda value: dt_util.parse_datetime(value),
        ),
        SmartThingsSensorEntityDescription(
            key=Attribute.oven_job_state,
            name="Oven Job State",
        ),
        SmartThingsSensorEntityDescription(
            key=Attribute.machine_state,
            name="Oven Machine State",
        ),
    ],
    Capability.oven_setpoint: [
        SmartThingsSensorEntityDescription(
            key=Attribute.oven_setpoint,
            name="Oven Set Point",
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        ),
    ],
    Capability.temperature_measurement: [
        SmartThingsSensorEntityDescription(
            key=Attribute.temperature,
            name="Temperature Measurement",
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
        ),
    ],
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add sensor entities for a config entry."""
    broker = hass.data[DOMAIN][DATA_BROKERS][config_entry.entry_id]
    entities: list[SmartThingsSensorEntity] = []
    for device in broker.devices.values():
        room = broker.rooms[device.room_id]
        for capability in broker.get_capabilities(device):
            if attributes := SENSOR_DESCRIPTIONS.get(capability):
                for attribute in attributes:
                    entities.append(
                        SmartThingsSensorEntity(
                            device, capability, attribute, room,
                        )
                    )

    async_add_entities(entities)


class SmartThingsSensorEntity(SmartThingsEntity, SensorEntity):
    """Define a SmartThings sensor entity."""

    entity_description: SmartThingsSensorEntityDescription

    @property
    def native_value(self):
        """Return the state of the sensor."""
        value = self._device.status.attributes[self.entity_description.key].value
        return self.entity_description.native_value(value)

    @property
    def native_unit_of_measurement(self):
        """Return the unit this state is expressed in."""
        if unit := self._device.status.attributes[self.entity_description.key].unit:
            return UNIT_MAP.get(unit, unit)
        return self.entity_description.native_unit_of_measurement
