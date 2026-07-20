"""Config flow for Beckhoff ADS integration."""
from __future__ import annotations

import logging
from typing import Any

import pyads
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.data_entry_flow import section
from .const import CONF_AMS_NET_ID, DEFAULT_PORT, DOMAIN, CONF_ENTITIES
from .schema import ENTITY_SCHEMA

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_HOST, default=""): str,
    vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
    vol.Required(CONF_AMS_NET_ID, default=""): str,
})


class BeckhoffADSConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Beckhoff ADS."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            ams_net_id = user_input[CONF_AMS_NET_ID]

            # Test connection
            try:
                await self._test_connection(host, port, ams_net_id)
            except ConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Create entry
                await self.async_set_unique_id(f"{host}_{ams_net_id}")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"Beckhoff PLC ({host})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def _test_connection(self, host: str, port: int, ams_net_id: str) -> None:
        """Test connection to PLC."""
        try:
            plc = pyads.Connection(ams_net_id, port, host)
            await self.hass.async_add_executor_job(plc.open)
            await self.hass.async_add_executor_job(plc.read_state)
            await self.hass.async_add_executor_job(plc.close)
        except Exception as err:
            _LOGGER.error("Connection test failed: %s", err)
            raise ConnectionError from err
    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return BeckhoffADSOptionsFlow()


class BeckhoffADSOptionsFlow(config_entries.OptionsFlow):

    def __init__(self) -> None:
        self._entities: list[dict] = []
        self._entities_loaded: bool = False
        self._new_entity_type: str = "sensor"
        self._edit_entity_index: int | None = None

    def _build_details_schema(self, entity_type: str) -> vol.Schema:
        """Build the entity details schema for a given entity type."""
        schema_dict: dict = {
            vol.Required("name"): str,
            vol.Required("plc_address"): str,
            vol.Required("plc_type", default="REAL"): SelectSelector(SelectSelectorConfig(
                options=[
                    "BOOL", "BYTE", "SINT", "USINT", "INT", "UINT", "WORD",
                    "DINT", "UDINT", "DWORD", "REAL", "LREAL", "STRING", "TIME",
                ],
                mode=SelectSelectorMode.DROPDOWN,
            )),
            vol.Optional("device_class"): str,
            vol.Optional("icon"): str,
            vol.Optional("use_notifications", default=True): bool,
        }

        if entity_type == "sensor":
            schema_dict.update({
                vol.Optional("unit_of_measurement"): str,
                vol.Optional("factor", default=1.0): vol.Coerce(float),
                vol.Optional("offset", default=0.0): vol.Coerce(float),
                vol.Optional("precision"): vol.Any(None, vol.Coerce(int)),
            })
            schema_dict["range_scale"] = section(
                vol.Schema({
                    vol.Optional("low_in"): vol.Coerce(float),
                    vol.Optional("high_in"): vol.Coerce(float),
                    vol.Optional("low_out"): vol.Coerce(float),
                    vol.Optional("high_out"): vol.Coerce(float),
                }),
                {"collapsed": True},
            )

        elif entity_type == "number":
            schema_dict.update({
                vol.Optional("unit_of_measurement"): str,
                vol.Optional("min_value", default=0): vol.Coerce(float),
                vol.Optional("max_value", default=100): vol.Coerce(float),
                vol.Optional("step", default=1): vol.Coerce(float),
                vol.Optional("mode", default="slider"): SelectSelector(SelectSelectorConfig(
                    options=["slider", "box"],
                    mode=SelectSelectorMode.DROPDOWN,
                )),
            })

        elif entity_type == "select":
            schema_dict[vol.Optional("options", default="")] = str

        return vol.Schema(schema_dict)


    def _process_details_input(
        self, user_input: dict, entity_type: str
    ) -> tuple[dict | None, dict]:
        """Validate and clean up entity details. Returns (validated, errors)."""
        errors: dict[str, str] = {}
        try:
            if "options" in user_input and isinstance(user_input["options"], str):
                user_input["options"] = [
                    o.strip() for o in user_input["options"].split(",") if o.strip()
                ]

            rs = user_input.get("range_scale") or {}
            rs_filled = {k: v for k, v in rs.items() if v is not None}
            if rs_filled:
                if len(rs_filled) < 4:
                    errors["base"] = "range_scale_incomplete"
                else:
                    user_input["range_scale"] = rs_filled
            else:
                user_input.pop("range_scale", None)

            if not errors:
                user_input["type"] = entity_type
                from .schema import ENTITY_SCHEMA
                return ENTITY_SCHEMA(user_input), {}

        except vol.Invalid as err:
            errors["base"] = str(err)

        return None, errors

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if not self._entities_loaded:
            self._entities = list(self.config_entry.options.get(CONF_ENTITIES, []))
            self._entities_loaded = True

        if self._entities:
            entity_lines = "\n".join(
                f"- {e['name']} ({e['type']}, {e['plc_address']})"
                for e in self._entities
            )
        else:
            entity_lines = "No entities configured"

        return self.async_show_menu(
            step_id="init",
            menu_options=["add_entity","edit_entity", "remove_entity", "finish"],
            
            #description_placeholders={"entities": entity_lines},
        )

    async def async_step_add_entity(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Choose entity type."""
        if user_input is not None:
            self._new_entity_type = user_input["type"]
            return await self.async_step_add_entity_details()

        return self.async_show_form(
            step_id="add_entity",
            data_schema=vol.Schema({
                vol.Required("type", default="sensor"): SelectSelector(SelectSelectorConfig(
                    options=["sensor", "binary_sensor", "switch", "number", "select"],
                    mode=SelectSelectorMode.DROPDOWN,
                )),
            }),
        )
    
    async def async_step_add_entity_details(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        entity_type = self._new_entity_type

        if user_input is not None:
            validated, errors = self._process_details_input(user_input, entity_type)
            if validated is not None:
                self._entities.append(validated)
                return await self.async_step_init()

        return self.async_show_form(
            step_id="add_entity_details",
            data_schema=self._build_details_schema(entity_type),
            errors=errors,
            description_placeholders={"type": entity_type.replace("_", " ").title()},
        )
    async def async_step_edit_entity(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Pick which entity to edit."""
        if not self._entities:
            return await self.async_step_init()

        if user_input is not None:
            name = user_input["entity_name"]
            self._edit_entity_index = next(
                i for i, e in enumerate(self._entities) if e["name"] == name
            )
            self._new_entity_type = self._entities[self._edit_entity_index]["type"]
            return await self.async_step_edit_entity_details()

        return self.async_show_form(
            step_id="edit_entity",
            data_schema=vol.Schema({
                vol.Required("entity_name"): SelectSelector(SelectSelectorConfig(
                    options=[
                        {"value": e["name"], "label": f"{e['name']} ({e['type']}, {e['plc_address']})"}
                        for e in self._entities
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )),
            }),
        )


    async def async_step_edit_entity_details(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit the selected entity, pre-populated with existing values."""
        errors: dict[str, str] = {}
        entity_type = self._new_entity_type
        existing = dict(self._entities[self._edit_entity_index])

        if user_input is not None:
            validated, errors = self._process_details_input(user_input, entity_type)
            if validated is not None:
                self._entities[self._edit_entity_index] = validated
                return await self.async_step_init()

        # Convert stored list back to comma-separated string for the form
        suggested = dict(existing)
        if entity_type == "select" and isinstance(suggested.get("options"), list):
            suggested["options"] = ", ".join(suggested["options"])

        return self.async_show_form(
            step_id="edit_entity_details",
            data_schema=self.add_suggested_values_to_schema(
                self._build_details_schema(entity_type), suggested
            ),
            errors=errors,
            description_placeholders={"type": entity_type.replace("_", " ").title()},
        )

    async def async_step_remove_entity(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._entities = [
                e for e in self._entities if e["name"] != user_input["entity_name"]
            ]
            return await self.async_step_init()

        if not self._entities:
            return await self.async_step_init()

        return self.async_show_form(
            step_id="remove_entity",
            data_schema=vol.Schema({
                vol.Required("entity_name"): vol.In({
                    e["name"]: f"{e['name']} ({e['type']}, {e['plc_address']})"
                    for e in self._entities
                }),
            }),
        )

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return self.async_create_entry(title="", data={CONF_ENTITIES: self._entities})