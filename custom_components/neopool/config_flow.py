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

"""Config flow for the NeoPool integration."""

from typing import Any, override

from neopool_modbus import async_probe_serial
from neopool_modbus.exceptions import (
    NeoPoolConnectionError,
    NeoPoolModbusError,
    NeoPoolTimeoutError,
)
from neopool_modbus.registers import DEFAULT_MODBUS_FRAMER
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback

from . import NeoPoolConfigEntry
from .const import CURRENT_VERSION, DEFAULT_PORT, DEFAULT_UNIT_ID, DOMAIN
from .migration import (
    async_abort_if_unmigrated_v1_match,
    async_handle_import_step,
    async_offer_vistapool_import_if_present,
)
from .options_flow import NeoPoolOptionsFlowHandler


async def _async_probe(user_input: dict[str, Any]) -> tuple[str | None, str | None]:
    """Probe a device using user-supplied connection parameters."""
    try:
        serial = await async_probe_serial(
            user_input[CONF_HOST],
            port=user_input[CONF_PORT],
            unit_id=user_input["unit_id"],
            framer=user_input["modbus_framer"],
        )
    except (NeoPoolConnectionError, NeoPoolTimeoutError):
        return None, "cannot_connect"
    except NeoPoolModbusError:
        return None, "cannot_read_modbus"
    return serial, None


class NeoPoolConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for NeoPool."""

    VERSION = CURRENT_VERSION

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step of the configuration flow."""
        # CUSTOM-ONLY START, vistapool→neopool import detection.
        # If a legacy `vistapool` config entry is present (left over from the
        # v2.x release before the domain rename), offer the user a one-click
        # import step that migrates the entry, its entities and device-level
        # customizations to the new `neopool` domain. Otherwise fall through
        # to the regular new-entry form.
        if user_input is None:
            if (
                result := await async_offer_vistapool_import_if_present(self)
            ) is not None:
                return result
        # CUSTOM-ONLY END

        data_schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): vol.Coerce(int),
                vol.Optional("unit_id", default=DEFAULT_UNIT_ID): vol.Coerce(int),
                vol.Optional(
                    "modbus_framer",
                    default=DEFAULT_MODBUS_FRAMER,
                ): vol.In(("tcp", "rtu")),
            }
        )
        errors: dict[str, str] = {}
        if user_input is not None:
            serial, error_key = await _async_probe(user_input)
            if error_key:
                errors[CONF_HOST] = error_key
            else:
                assert serial is not None
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured()

                # CUSTOM-ONLY START, historic v1 entries had no unique_id, so
                # the abort_if_unique_id_configured check above can't catch them.
                if (
                    result := async_abort_if_unmigrated_v1_match(self, user_input)
                ) is not None:
                    return result
                # CUSTOM-ONLY END

                return self.async_create_entry(
                    title=user_input[CONF_HOST], data=user_input
                )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    # CUSTOM-ONLY START, vistapool import step is HACS-only.
    async def async_step_import_from_vistapool(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer to migrate an existing vistapool entry to the new neopool domain.

        Thin dispatcher, see :func:`migration.async_handle_import_step` for
        the full pre-check → form → migration → result-mapping pipeline.
        """
        return await async_handle_import_step(
            self, user_input, self._legacy_entry_id, self._legacy_entry_title
        )

    # CUSTOM-ONLY END

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
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
                ): vol.Coerce(int),
                vol.Optional(
                    "unit_id",
                    default=current.get("unit_id", DEFAULT_UNIT_ID),
                ): vol.Coerce(int),
                vol.Optional(
                    "modbus_framer",
                    default=current.get("modbus_framer", DEFAULT_MODBUS_FRAMER),
                ): vol.In(("tcp", "rtu")),
            }
        )

        errors: dict[str, str] = {}
        if user_input is not None:
            merged = {**current, **user_input}
            serial, error_key = await _async_probe(merged)
            if error_key:
                errors[CONF_HOST] = error_key
            elif entry.unique_id and serial != entry.unique_id:
                errors[CONF_HOST] = "serial_mismatch"
            else:
                return self.async_update_reload_and_abort(entry, data=merged)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=data_schema,
            errors=errors,
        )

    @staticmethod
    @callback
    @override
    def async_get_options_flow(
        config_entry: NeoPoolConfigEntry,
    ) -> NeoPoolOptionsFlowHandler:
        """Return the options flow."""
        return NeoPoolOptionsFlowHandler()
