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

import asyncio
import logging
from typing import Any

from neopool_modbus.registers import DEFAULT_MODBUS_FRAMER
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import translation as ha_translation

from . import NeoPoolConfigEntry
from .const import (
    CONF_FILTRATION_PUMP_POWER,
    CURRENT_VERSION,
    DEFAULT_PORT,
    DEFAULT_UNIT_ID,
    DOMAIN,
    NAME,
)
from .helpers import async_get_device_serial
from .migration import (
    async_abort_if_unmigrated_v1_match,
    async_handle_import_step,
    async_offer_vistapool_import_if_present,
)
from .options_flow import NeoPoolOptionsFlowHandler

_LOGGER = logging.getLogger(__name__)


async def is_host_port_open(host: str, port: int, timeout: int = 3) -> bool:
    """Probe a TCP host:port to verify it accepts connections."""
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
    except (TimeoutError, OSError):
        return False
    writer.close()
    await writer.wait_closed()
    return True


class NeoPoolConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for NeoPool."""

    # HA contract: ConfigFlow subclasses must declare a class-level VERSION
    # used to stamp fresh entries and to detect when async_migrate_entry
    # needs to run. The single source of truth lives in const.CURRENT_VERSION
    # — this attribute just exposes it under the name HA core looks for.
    VERSION = CURRENT_VERSION

    async def _async_validate_connection(self, user_input: dict) -> dict:
        """Validate host/port connectivity and return an errors dict."""
        errors = {}
        host: str = user_input[CONF_HOST]
        port: int = user_input.get(CONF_PORT, DEFAULT_PORT)
        if not await is_host_port_open(host, port):
            errors[CONF_HOST] = "cannot_connect"
        return errors

    async def _async_get_default_title(self) -> str:
        """Return the localized default entry title.

        Reads the `name_default` translation key (e.g. "Pool" / "Bazén"
        / "Piscine") so a fresh entry's UI label matches the user's
        language. Falls back to the English brand name on lookup error.
        """
        try:
            t = await ha_translation.async_get_translations(
                self.hass, self.hass.config.language, "config", {DOMAIN}
            )
            key = f"component.{DOMAIN}.config.step.user.data.name_default"
            return t.get(key) or NAME
        except Exception:  # noqa: BLE001
            return NAME

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step of the configuration flow."""
        # CUSTOM-ONLY START — vistapool→neopool import detection.
        # If a legacy `vistapool` config entry is present (left over from the
        # v2.x release before the domain rename), offer the user a one-click
        # import step that migrates the entry, its entities and device-level
        # customizations to the new `neopool` domain. Otherwise fall through
        # to the regular new-entry form.
        # Detect a legacy vistapool entry the user hasn't dealt with yet.
        # We only offer the import on the first form display (user_input None);
        # if they already started typing a fresh config we don't interrupt.
        if user_input is None:
            if (
                result := await async_offer_vistapool_import_if_present(self)
            ) is not None:
                return result
        # CUSTOM-ONLY END

        data_schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Optional("unit_id", default=DEFAULT_UNIT_ID): int,
                vol.Optional(
                    "modbus_framer",
                    default=DEFAULT_MODBUS_FRAMER,
                ): vol.In(("tcp", "rtu")),
                vol.Optional(
                    CONF_FILTRATION_PUMP_POWER,
                    default=0,
                ): vol.All(int, vol.Range(min=0)),
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
            errors = await self._async_validate_connection(user_input)
            if errors:
                return self.async_show_form(
                    step_id="user",
                    data_schema=data_schema,
                    errors=errors,
                )

            serial_number = await async_get_device_serial(user_input)
            if not serial_number:
                errors[CONF_HOST] = "cannot_read_modbus"
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

            unique_id = f"neopool_{serial_number}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            # CUSTOM-ONLY START — historic v1 entries had no unique_id, so
            # the abort_if_unique_id_configured check above can't catch them.
            # Validation 3b: Catch unmigrated v1 entries (unique_id=None) by connection params
            if (
                result := async_abort_if_unmigrated_v1_match(self, user_input)
            ) is not None:
                return result
            # CUSTOM-ONLY END

            _LOGGER.info(
                "Creating new NeoPool config entry (serial: …%s)",
                serial_number[-6:],
            )

            return self.async_create_entry(
                title=await self._async_get_default_title(), data=user_input
            )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
        )

    # CUSTOM-ONLY START — vistapool import step is HACS-only.
    async def async_step_import_from_vistapool(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer to migrate an existing vistapool entry to the new neopool domain.

        Thin dispatcher — see :func:`migration.async_handle_import_step` for
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
                ): int,
                vol.Optional(
                    "unit_id",
                    default=current.get(
                        "unit_id", current.get("slave_id", DEFAULT_UNIT_ID)
                    ),
                ): int,
                vol.Optional(
                    "modbus_framer",
                    default=current.get("modbus_framer", DEFAULT_MODBUS_FRAMER),
                ): vol.In(("tcp", "rtu")),
            }
        )

        errors = {}
        if user_input is not None:
            errors = await self._async_validate_connection(user_input)
            if not errors:
                if entry.unique_id:
                    serial = await async_get_device_serial({**current, **user_input})
                    if serial and f"neopool_{serial}" != entry.unique_id:
                        errors[CONF_HOST] = "serial_mismatch"
                    elif not serial:
                        errors[CONF_HOST] = "cannot_read_modbus"

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
    @callback
    def async_get_options_flow(
        config_entry: NeoPoolConfigEntry,
    ) -> NeoPoolOptionsFlowHandler:
        """Return the options flow."""
        return NeoPoolOptionsFlowHandler()
