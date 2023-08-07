"""Support for lock entities through the SmartThings cloud API."""
from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import Any

from pysmartthings import Attribute, Capability

from homeassistant.components.lock import LockEntity, LockEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SmartThingsEntity
from .const import DATA_BROKERS, DOMAIN, CustomAttribute

LOCK_ATTR_MAP = {
    "codeId": "code_id",
    "codeName": "code_name",
    "lockName": "lock_name",
    "method": "method",
    "timeout": "timeout",
    "usedCode": "used_code",
}

@dataclass
class SmartThingsLockEntityDescription(LockEntityDescription):
    """Class to describe a SmartThings lock entity."""

LOCK_DESCRIPTIONS: dict[str, list[SmartThingsLockEntityDescription]] = {
    Capability.lock: [
        SmartThingsLockEntityDescription(
            key=Attribute.lock,
            name=None,
        ),
    ],
}

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add lock entities for a config entry."""
    broker = hass.data[DOMAIN][DATA_BROKERS][config_entry.entry_id]
    entities: list[SmartThingsLockEntity] = []
    for device in broker.devices.values():
        room = broker.rooms[device.room_id]
        for capability in broker.get_capabilities(device):
            if attributes := LOCK_DESCRIPTIONS.get(capability):
                for attribute in attributes:
                    entities.append(
                        SmartThingsLockEntity(
                            device, capability, attribute, room,
                        )
                    )

    async_add_entities(entities)


class SmartThingsLockEntity(SmartThingsEntity, LockEntity):
    """Define a SmartThings lock entity."""

    entity_description: SmartThingsLockEntityDescription

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the lock."""
        await self._device.lock(set_status=True)
        self.async_write_ha_state()

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the lock."""
        await self._device.unlock(set_status=True)
        self.async_write_ha_state()

    @property
    def is_locked(self) -> bool | None:
        """Return true if the lock is locked."""
        value = self._device.status.attributes[self.entity_description.key].value
        return bool(value == "locked")

    @property
    def changed_by(self) -> str | None:
        """Last change triggered by."""
        status = self._device.status.attributes[self.entity_description.key]
        if isinstance(status.data, dict):
            if code_id := status.data.get("code_id"):
                if code_name := self._lock_codes.get(code_id):
                    return code_name
            if method := status.data.get("method"):
                return method
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return device specific state attributes."""
        state_attrs = super().extra_state_attributes
        status = self._device.status.attributes[self.entity_description.key]
        if isinstance(status.data, dict):
            _LOGGER.debug(f"Lock status Data: {status.data}")
            for key, attr in LOCK_ATTR_MAP.items():
                if value := status.data.get(key):
                    state_attrs[attr] = value
                    if attr == "code_id":
                        if code_name := self._lock_codes.get(value):
                            state_attrs["code_name"] = code_name
        return state_attrs

    @property
    def _lock_codes(self) -> dict[str, str]:
        """Return true if the lock is locked."""
        lock_codes = self._device.status.attributes[CustomAttribute.lock_codes].value
        return json.loads(lock_codes.replace("'\'", ""))
