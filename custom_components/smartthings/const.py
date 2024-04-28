"""Constants used by the SmartThings component and platforms."""
from datetime import timedelta
import re

from pysmartthings import Attribute, Capability

from homeassistant.backports.enum import StrEnum
from homeassistant.const import Platform

DOMAIN = "smartthings"

APP_OAUTH_CLIENT_NAME = "Home Assistant"
APP_OAUTH_SCOPES = ["r:devices:*"]
APP_NAME_PREFIX = "homeassistant."

CONF_APP_ID = "app_id"
CONF_CLOUDHOOK_URL = "cloudhook_url"
CONF_INSTALLED_APP_ID = "installed_app_id"
CONF_INSTANCE_ID = "instance_id"
CONF_LOCATION_ID = "location_id"
CONF_REFRESH_TOKEN = "refresh_token"

DATA_MANAGER = "manager"
DATA_BROKERS = "brokers"

SIGNAL_SMARTTHINGS_BUTTON = "smartthings_button"
SIGNAL_SMARTTHINGS_UPDATE = "smartthings_update"
SIGNAL_SMARTAPP_PREFIX = "smartthings_smartap_"

SETTINGS_INSTANCE_ID = "hassInstanceId"

SUBSCRIPTION_WARNING_LIMIT = 40

STORAGE_KEY = DOMAIN
STORAGE_VERSION = 1

# Ordered 'specific to least-specific platform' in order for capabilities
# to be drawn-down and represented by the most appropriate platform.
PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.EVENT,
    Platform.FAN,
    Platform.LIGHT,
    Platform.LOCK,
    Platform.SELECT,
    Platform.SENSOR,
]

TOKEN_REFRESH_INTERVAL = timedelta(days=14)

VAL_UID = "^(?:([0-9a-fA-F]{32})|([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}))$"
VAL_UID_MATCHER = re.compile(VAL_UID)

ATTRIBUTION =  "Data provided by SmartThings"
DEVICE_INFO_MAP = {
    "Button": ("Aeotec", "GP-AEOBTNUS"),
    "Dome Leak Sensor": ("Dome", "DMWS1"),
    "Samsung Microwave": ("Samsung", "MC17T8000CS"),
    "Schlage Touchscreen Deadbolt Door Lock": ("Schlage", "BE469NX"),
    "SmartThings Button": ("Aeotec", "GP-AEOBTNUS"),
    "water-battery-tamper": ("Aeotec", "Water Sensor 7"),
    "water-temp-battery-tempOffset": ("Aeotec", "GP-AEOWLSUS"),
}

class CustomComponent(StrEnum):
    """Define custom components."""

    hood = "hood"


class CustomCapability(StrEnum):
    """Define custom capabilities."""

    door_state = "samsungce.doorState"
    health_check = "healthCheck"
    hood_fan_speed = "samsungce.hoodFanSpeed"
    lamp = "samsungce.lamp"
    

class CustomAttribute(StrEnum):
    """Define custom attributes."""

    brightness_level = "brightnessLevel"
    completion_time = "completionTime"
    door_state = "doorState"
    hood_fan_speed = "hoodFanSpeed"
    lock_codes = "lockCodes"
    max_fan_speed = "settableMaxFanSpeed"
    min_fan_speed = "settableMinFanSpeed"
    supported_brightness_level = "supportedBrightnessLevel"
    supported_hood_fan_speed = "supportedHoodFanSpeed"
