# Copyright 2025 Miloš Svašek

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""VistaPool Integration for Home Assistant - Config Flow"""

import asyncio
import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import translation as ha_translation
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig

from .const import (
    DEFAULT_MODBUS_FRAMER,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLAVE_ID,
    DOMAIN,
)
from .helpers import async_get_device_serial

_LOGGER = logging.getLogger(__name__)


async def is_host_port_open(host, port, timeout=3):
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout
        )
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


class VistaPoolConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Handle a config flow for VistaPool."""

    VERSION = 2

    async def _async_validate_connection(self, user_input: dict) -> dict:
        """Validate host/port connectivity and return an errors dict."""
        errors = {}
        host = user_input.get(CONF_HOST)
        port = user_input.get(CONF_PORT, DEFAULT_PORT)
        if not await is_host_port_open(host, port):
            errors[CONF_HOST] = "cannot_connect"
        return errors

    async def _async_get_default_name(self) -> str:
        """Return the localized default device name from translations."""
        try:
            t = await ha_translation.async_get_translations(
                self.hass, self.hass.config.language, "config", {DOMAIN}
            )
            key = f"component.{DOMAIN}.config.step.user.data.name_default"
            return t.get(key) or DEFAULT_NAME
        except Exception:  # noqa: BLE001
            return DEFAULT_NAME

    async def async_migrate_entry(self, config_entry: ConfigEntry) -> bool:
        """Migrate config entry from v1 (no unique_id) to v2 (serial-based unique_id).

        Old format: entry.unique_id = None
        New format: entry.unique_id = "neopool_{serial}"
        """
        _LOGGER.info(
            "Migrating VistaPool config entry %s from v1 to v2", config_entry.entry_id
        )

        # Trial read to get serial (dict() unwraps MappingProxy for the Modbus client)
        serial = await async_get_device_serial(dict(config_entry.data))
        if not serial:
            _LOGGER.warning(
                "Migration for %s: Cannot read device serial. "
                "Will use entry_id as fallback identifier.",
                config_entry.entry_id,
            )
            # Fallback: use entry_id as unique_id (not ideal, but safe)
            new_unique_id = config_entry.entry_id
        else:
            new_unique_id = f"neopool_{serial}"

        # Check if this serial is already registered (duplicate after migration)
        if serial:
            for entry in self.hass.config_entries.async_entries(DOMAIN):
                if (
                    entry.entry_id != config_entry.entry_id
                    and entry.unique_id == new_unique_id
                ):
                    _LOGGER.error(
                        "Migration failed: Device %s is already configured",
                        new_unique_id,
                    )
                    return False

        # Update config entry unique_id
        self.hass.config_entries.async_update_entry(
            config_entry, unique_id=new_unique_id
        )

        # Migrate entity unique_ids in registry
        entity_registry = er.async_get(self.hass)
        old_entry_id = config_entry.entry_id
        migrated_count = 0

        for entity_entry in list(
            er.async_entries_for_config_entry(entity_registry, config_entry.entry_id)
        ):
            # Old format: {entry_id}_{key}
            # New format: {new_unique_id}_{key}
            if entity_entry.unique_id and entity_entry.unique_id.startswith(
                old_entry_id
            ):
                key_part = entity_entry.unique_id.replace(f"{old_entry_id}_", "", 1)
                migrated_unique_id = f"{new_unique_id}_{key_part}"

                _LOGGER.debug(
                    "Migrating entity %s: %s → %s",
                    entity_entry.entity_id,
                    entity_entry.unique_id,
                    migrated_unique_id,
                )

                try:
                    entity_registry.async_update_entity(
                        entity_entry.entity_id,
                        new_unique_id=migrated_unique_id,
                    )
                    migrated_count += 1
                except Exception as err:
                    _LOGGER.error(
                        "Failed to migrate entity %s: %s", entity_entry.entity_id, err
                    )

        _LOGGER.info(
            "Migration completed for %s: %d entities migrated, unique_id=%s",
            config_entry.title,
            migrated_count,
            new_unique_id,
        )
        return True

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        """Handle the initial step of the configuration flow."""
        default_name = await self._async_get_default_name()
        data_schema = vol.Schema(
            {
                vol.Optional(CONF_NAME, default=default_name): str,
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Optional("slave_id", default=DEFAULT_SLAVE_ID): int,
                vol.Optional(
                    "modbus_framer",
                    default=DEFAULT_MODBUS_FRAMER,
                ): vol.In(["tcp", "rtu"]),
                vol.Optional(
                    "scan_interval",
                    default=str(DEFAULT_SCAN_INTERVAL),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            str(v) for v in [5, 10, 15, 20, 30, 45, 60, 120, 180, 300]
                        ]
                    )
                ),
                vol.Optional(
                    "use_filtration1",
                    default=True,
                ): bool,
                vol.Optional(
                    "use_filtration2",
                    default=False,
                ): bool,
                vol.Optional(
                    "use_filtration3",
                    default=False,
                ): bool,
                vol.Optional(
                    "use_light",
                    default=False,
                ): bool,
                vol.Optional(
                    "use_cover_sensor",
                    default=False,
                ): bool,
            }
        )
        errors = {}
        if user_input is not None:
            device_name = (
                user_input.get(CONF_NAME) or await self._async_get_default_name()
            )
            user_input[CONF_NAME] = device_name

            # Validation 1: TCP connection
            errors = await self._async_validate_connection(user_input)
            if errors:
                return self.async_show_form(
                    step_id="user",
                    data_schema=data_schema,
                    errors=errors,
                )

            # Validation 2: Trial Modbus read → get serial number
            serial_number = await async_get_device_serial(user_input)
            if not serial_number:
                errors["host"] = "cannot_read_modbus"
                _LOGGER.warning(
                    "User cannot read from Modbus device at %s:%s",
                    user_input.get(CONF_HOST),
                    user_input.get(CONF_PORT),
                )
                return self.async_show_form(
                    step_id="user",
                    data_schema=data_schema,
                    errors=errors,
                )

            # Validation 3: Duplicate prevention (unique_id based on serial)
            unique_id = f"neopool_{serial_number}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            # Coerce types before creating entry
            if "scan_interval" in user_input:
                user_input["scan_interval"] = int(user_input["scan_interval"])

            _LOGGER.info(
                "Creating new VistaPool config entry: %s (serial: %s)",
                device_name,
                serial_number,
            )

            return self.async_create_entry(title=device_name, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
        )

    async def async_step_reconfigure(self, user_input=None) -> ConfigFlowResult:
        """Handle reconfiguration of an existing entry."""
        entry_id = self.context.get("entry_id")
        if entry_id is None:
            return self.async_abort(reason="entry_not_found")
        entry = self.hass.config_entries.async_get_entry(entry_id)
        if entry is None:
            return self.async_abort(reason="entry_not_found")

        current = entry.data

        data_schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=current.get(CONF_HOST, "")): str,
                vol.Optional(
                    CONF_PORT, default=current.get(CONF_PORT, DEFAULT_PORT)
                ): int,
                vol.Optional(
                    "slave_id", default=current.get("slave_id", DEFAULT_SLAVE_ID)
                ): int,
                vol.Optional(
                    "modbus_framer",
                    default=current.get("modbus_framer", DEFAULT_MODBUS_FRAMER),
                ): vol.In(["tcp", "rtu"]),
            }
        )

        errors = {}
        if user_input is not None:
            errors = await self._async_validate_connection(user_input)
            if not errors:
                new_data = {**current, **user_input}
                return self.async_update_reload_and_abort(
                    entry,
                    data=new_data,
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=data_schema,
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        from .options_flow import VistaPoolOptionsFlowHandler

        return VistaPoolOptionsFlowHandler()
