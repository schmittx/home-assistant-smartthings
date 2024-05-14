"""Support for SmartThings Cloud."""
from __future__ import annotations

import asyncio
from collections.abc import Iterable
from http import HTTPStatus
import json
import logging

from aiohttp.client_exceptions import ClientConnectionError, ClientResponseError
from pysmartapp.event import EVENT_TYPE_DEVICE
from pysmartthings import Attribute, Capability, DeviceEntity, RoomEntity, SmartThings

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import (
    ATTR_BATTERY_LEVEL,
    CONF_ACCESS_TOKEN,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_loaded_integration
from homeassistant.setup import SetupPhases, async_pause_setup

from .const import (
    CONF_APP_ID,
    CONF_INSTALLED_APP_ID,
    CONF_LOCATION_ID,
    CONF_REFRESH_TOKEN,
    DATA_BROKERS,
    DATA_MANAGER,
    DEVICE_INFO_MAP,
    DOMAIN,
    PLATFORMS,
    SIGNAL_SMARTTHINGS_BUTTON,
    SIGNAL_SMARTTHINGS_UPDATE,
    TOKEN_REFRESH_INTERVAL,
)
from .smartapp import (
    format_unique_id,
    setup_smartapp,
    setup_smartapp_endpoint,
    smartapp_sync_subscriptions,
    unload_smartapp_endpoint,
    validate_installed_app,
    validate_webhook_requirements,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Initialize the SmartThings platform."""
    await setup_smartapp_endpoint(hass, False)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Handle migration of a previous version config entry.

    A config entry created under a previous version must go through the
    integration setup again so we can properly retrieve the needed data
    elements. Force this by removing the entry and triggering a new flow.
    """
    # Remove the entry which will invoke the callback to delete the app.
    hass.async_create_task(hass.config_entries.async_remove(entry.entry_id))
    # only create new flow if there isn't a pending one for SmartThings.
    if not hass.config_entries.flow.async_progress_by_handler(DOMAIN):
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}
            )
        )

    # Return False because it could not be migrated.
    return False


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Initialize config entry which represents an installed SmartApp."""
    # For backwards compat
    if entry.unique_id is None:
        hass.config_entries.async_update_entry(
            entry,
            unique_id=format_unique_id(
                entry.data[CONF_APP_ID], entry.data[CONF_LOCATION_ID]
            ),
        )

    if not validate_webhook_requirements(hass):
        _LOGGER.warning(
            "The 'base_url' of the 'http' integration must be configured and start with"
            " 'https://'"
        )
        return False

    api = SmartThings(async_get_clientsession(hass), entry.data[CONF_ACCESS_TOKEN])

    # Ensure platform modules are loaded since the DeviceBroker will
    # import them below and we want them to be cached ahead of time
    # so the integration does not do blocking I/O in the event loop
    # to import the modules.
    await async_get_loaded_integration(hass, DOMAIN).async_get_platforms(PLATFORMS)

    remove_entry = False
    try:
        # See if the app is already setup. This occurs when there are
        # installs in multiple SmartThings locations (valid use-case)
        manager = hass.data[DOMAIN][DATA_MANAGER]
        smart_app = manager.smartapps.get(entry.data[CONF_APP_ID])
        if not smart_app:
            # Validate and setup the app.
            app = await api.app(entry.data[CONF_APP_ID])
            smart_app = setup_smartapp(hass, app)

        # Validate and retrieve the installed app.
        installed_app = await validate_installed_app(
            api, entry.data[CONF_INSTALLED_APP_ID]
        )

        # Get rooms
        rooms = await api.rooms(location_id=entry.data[CONF_LOCATION_ID])

        # Get scenes
        scenes = await async_get_entry_scenes(entry, api)

        # Get SmartApp token to sync subscriptions
        token = await api.generate_tokens(
            entry.data[CONF_CLIENT_ID],
            entry.data[CONF_CLIENT_SECRET],
            entry.data[CONF_REFRESH_TOKEN],
        )
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_REFRESH_TOKEN: token.refresh_token}
        )

        # Get devices and their current status
        devices = await api.devices(location_ids=[installed_app.location_id])

        async def retrieve_device_status(device):
            try:
                await device.status.refresh()
            except ClientResponseError:
                _LOGGER.debug(
                    (
                        "Unable to update status for device: %s (%s), the device will"
                        " be excluded"
                    ),
                    device.label,
                    device.device_id,
                    exc_info=True,
                )
                devices.remove(device)

        await asyncio.gather(*(retrieve_device_status(d) for d in devices.copy()))
        # Custom Component >>
        for device in devices:
            _LOGGER.debug(
                "Adding device:\n - name: %s\n - components: %s\n - capabilities: %s",
                device.label,
                device.components,
                device.capabilities,
            )
        # Custom Component <<

        # Sync device subscriptions
        await smartapp_sync_subscriptions(
            hass,
            token.access_token,
            installed_app.location_id,
            installed_app.installed_app_id,
            devices,
        )

        # Setup device broker
        with async_pause_setup(hass, SetupPhases.WAIT_IMPORT_PLATFORMS):
            # DeviceBroker has a side effect of importing platform
            # modules when its created. In the future this should be
            # refactored to not do this.
            broker = await hass.async_add_import_executor_job(
                DeviceBroker, hass, entry, token, smart_app, devices, rooms, scenes,
            )
        broker.connect()
        hass.data[DOMAIN][DATA_BROKERS][entry.entry_id] = broker

    except ClientResponseError as ex:
        if ex.status in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
            _LOGGER.exception(
                (
                    "Unable to setup configuration entry '%s' - please reconfigure the"
                    " integration"
                ),
                entry.title,
            )
            remove_entry = True
        else:
            _LOGGER.debug(ex, exc_info=True)
            raise ConfigEntryNotReady from ex
    except (ClientConnectionError, RuntimeWarning) as ex:
        _LOGGER.debug(ex, exc_info=True)
        raise ConfigEntryNotReady from ex

    if remove_entry:
        hass.async_create_task(hass.config_entries.async_remove(entry.entry_id))
        # only create new flow if there isn't a pending one for SmartThings.
        if not hass.config_entries.flow.async_progress_by_handler(DOMAIN):
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN, context={"source": SOURCE_IMPORT}
                )
            )
        return False

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_get_entry_scenes(entry: ConfigEntry, api):
    """Get the scenes within an integration."""
    try:
        return await api.scenes(location_id=entry.data[CONF_LOCATION_ID])
    except ClientResponseError as ex:
        if ex.status == HTTPStatus.FORBIDDEN:
            _LOGGER.exception(
                (
                    "Unable to load scenes for configuration entry '%s' because the"
                    " access token does not have the required access"
                ),
                entry.title,
            )
        else:
            raise
    return []


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    broker = hass.data[DOMAIN][DATA_BROKERS].pop(entry.entry_id, None)
    if broker:
        broker.disconnect()

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Perform clean-up when entry is being removed."""
    api = SmartThings(async_get_clientsession(hass), entry.data[CONF_ACCESS_TOKEN])

    # Remove the installed_app, which if already removed raises a HTTPStatus.FORBIDDEN error.
    installed_app_id = entry.data[CONF_INSTALLED_APP_ID]
    try:
        await api.delete_installed_app(installed_app_id)
    except ClientResponseError as ex:
        if ex.status == HTTPStatus.FORBIDDEN:
            _LOGGER.debug(
                "Installed app %s has already been removed",
                installed_app_id,
                exc_info=True,
            )
        else:
            raise
    _LOGGER.debug("Removed installed app %s", installed_app_id)

    # Remove the app if not referenced by other entries, which if already
    # removed raises a HTTP_FORBIDDEN error.
    all_entries = hass.config_entries.async_entries(DOMAIN)
    app_id = entry.data[CONF_APP_ID]
    app_count = sum(1 for entry in all_entries if entry.data[CONF_APP_ID] == app_id)
    if app_count > 1:
        _LOGGER.debug(
            (
                "App %s was not removed because it is in use by other configuration"
                " entries"
            ),
            app_id,
        )
        return
    # Remove the app
    try:
        await api.delete_app(app_id)
    except ClientResponseError as ex:
        if ex.status == HTTPStatus.FORBIDDEN:
            _LOGGER.debug("App %s has already been removed", app_id, exc_info=True)
        else:
            raise
    _LOGGER.debug("Removed app %s", app_id)

    if len(all_entries) == 1:
        await unload_smartapp_endpoint(hass)


class DeviceBroker:
    """Manages an individual SmartThings config entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        token,
        smart_app,
        devices: Iterable,
        rooms: Iterable,
        scenes: Iterable,
    ) -> None:
        """Create a new instance of the DeviceBroker."""
        self._hass = hass
        self._entry = entry
        self._installed_app_id = entry.data[CONF_INSTALLED_APP_ID]
        self._smart_app = smart_app
        self._token = token
        self._event_disconnect = None
        self._regenerate_token_remove = None
        self.devices = {device.device_id: device for device in devices}
        self.rooms = {room.room_id: room for room in rooms}
        self.scenes = {scene.scene_id: scene for scene in scenes}

    def get_capabilities(self, device: DeviceEntity):
        """Assign capabilities to devices."""
        capabilities = device.capabilities.copy()
        for _capabilities in device.components.values():
            capabilities.extend(_capabilities)
        return capabilities

    def connect(self):
        """Connect handlers/listeners for device/lifecycle events."""

        # Setup interval to regenerate the refresh token on a periodic basis.
        # Tokens expire in 30 days and once expired, cannot be recovered.
        async def regenerate_refresh_token(now):
            """Generate a new refresh token and update the config entry."""
            await self._token.refresh(
                self._entry.data[CONF_CLIENT_ID],
                self._entry.data[CONF_CLIENT_SECRET],
            )
            self._hass.config_entries.async_update_entry(
                self._entry,
                data={
                    **self._entry.data,
                    CONF_REFRESH_TOKEN: self._token.refresh_token,
                },
            )
            _LOGGER.debug(
                "Regenerated refresh token for installed app: %s",
                self._installed_app_id,
            )

        self._regenerate_token_remove = async_track_time_interval(
            self._hass, regenerate_refresh_token, TOKEN_REFRESH_INTERVAL
        )

        # Connect handler to incoming device events
        self._event_disconnect = self._smart_app.connect_event(self._event_handler)

    def disconnect(self):
        """Disconnects handlers/listeners for device/lifecycle events."""
        if self._regenerate_token_remove:
            self._regenerate_token_remove()
        if self._event_disconnect:
            self._event_disconnect()

    async def _event_handler(self, req, resp, app):
        """Broker for incoming events."""
        # Do not process events received from a different installed app
        # under the same parent SmartApp (valid use-scenario)
        if req.installed_app_id != self._installed_app_id:
            return

        updated_buttons = set()
        updated_devices = set()
        for evt in req.events:
            if evt.event_type != EVENT_TYPE_DEVICE:
                continue
            if not (device := self.devices.get(evt.device_id)):
                continue
            device.status.apply_attribute_update(
                evt.component_id,
                evt.capability,
                evt.attribute,
                evt.value,
                data=evt.data,
            )

            data = {
                "location_id": evt.location_id,
                "device_id": evt.device_id,
                "component_id": evt.component_id,
                "capability": evt.capability,
                "attribute": evt.attribute,
                "value": evt.value,
                "data": evt.data,
            }
            if all(
                [
                    evt.capability == Capability.button,
                    evt.attribute == Attribute.button,
                ]
            ):
                _LOGGER.debug("Button pressed: %s", data)
                updated_buttons.add(device.device_id)
            else:
                _LOGGER.debug("Update received: %s", data)
                updated_devices.add(device.device_id)

        if updated_buttons:
            async_dispatcher_send(self._hass, SIGNAL_SMARTTHINGS_BUTTON, updated_buttons)
        if updated_devices:
            async_dispatcher_send(self._hass, SIGNAL_SMARTTHINGS_UPDATE, updated_devices)


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
