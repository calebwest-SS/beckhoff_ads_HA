import voluptuous as vol
from homeassistant.helpers import config_validation as cv
from .const import ENTITY_TYPES, DOMAIN, CONF_ENTITIES

# YAML Schema for scaling filter
SCALING_SCHEMA = vol.Schema({
    vol.Required("low_in"): vol.Coerce(float),
    vol.Required("high_in"): vol.Coerce(float),
    vol.Required("low_out"): vol.Coerce(float),
    vol.Required("high_out"): vol.Coerce(float),
})

# YAML Schema for entities
ENTITY_SCHEMA = vol.Schema({
    vol.Required("name"): cv.string,
    vol.Required("type"): vol.In(ENTITY_TYPES),
    vol.Required("plc_address"): cv.string,
    vol.Optional("unit_of_measurement"): cv.string,
    vol.Optional("device_class"): cv.string,
    vol.Optional("icon"): cv.string,
    vol.Optional("options", default=[]): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional("scan_interval", default=5): cv.positive_int,
    vol.Optional("use_notifications", default=True): cv.boolean,
    vol.Optional("plc_type", default="REAL"): cv.string,  # For sensors/numbers
    vol.Optional("factor", default=1.0): vol.Coerce(float),  # Scaling factor
    vol.Optional("offset", default=0.0): vol.Coerce(float),  # Offset
    vol.Optional("precision", default=None): vol.Any(None, vol.Coerce(int)),  # Decimal places
    vol.Optional("range_scale"): SCALING_SCHEMA,
    # Number-specific options
    vol.Optional("min_value", default=0): vol.Coerce(float),  # Minimum value
    vol.Optional("max_value", default=100): vol.Coerce(float),  # Maximum value
    vol.Optional("step", default=1): vol.Coerce(float),  # Step size
    vol.Optional("mode", default="slider"): vol.In(["slider", "box"]),  # UI mode
})

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_ENTITIES, default=[]): vol.All(cv.ensure_list, [ENTITY_SCHEMA])
    })
}, extra=vol.ALLOW_EXTRA)