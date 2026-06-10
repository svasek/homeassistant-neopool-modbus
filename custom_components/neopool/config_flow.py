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

"""NeoPool integration for Home Assistant - Config flow."""

import asyncio
import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import translation as ha_translation
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig
from homeassistant.util import slugify
from neopool_modbus.registers import DEFAULT_MODBUS_FRAMER

from .const import (
    CONF_FILTRATION_PUMP_POWER,
    CURRENT_VERSION,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLAVE_ID,
    DOMAIN,
)
from .helpers import async_get_device_serial
from .migration import async_cleanup_old_folder, migrate_single_entry_cross_domain
from .options_flow import NeoPoolOptionsFlowHandler

_LOGGER = logging.getLogger(__name__)


async def is_host_port_open(host: str, port: int, timeout: int = 3) -> bool:
    """Return True if a TCP connection to host:port can be established."""
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
        writer.close()
        await writer.wait_closed()
    except (TimeoutError, OSError):
        return False
    else:
        return True


class NeoPoolConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Handle a config flow for NeoPool."""

    # HA contract: ConfigFlow subclasses must declare a class-level VERSION
    # used to stamp fresh entries and to detect when async_migrate_entry
    # needs to run. The single source of truth lives in const.CURRENT_VERSION
    # — this attribute just exposes it under the name HA core looks for.
    VERSION = CURRENT_VERSION

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
            # Translation lookup is best-effort; on any failure we fall
            # back to the literal English default so the form still opens.
            return DEFAULT_NAME

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step of the configuration flow.

        If a legacy `vistapool` config entry is present (left over from the
        v2.x release before the domain rename), offer the user a one-click
        import step that migrates the entry, its entities and device-level
        customizations to the new `neopool` domain. Otherwise fall through
        to the regular new-entry form.
        """
        # Detect a legacy vistapool entry the user hasn't dealt with yet.
        # We only offer the import on the first form display (user_input None);
        # if they already started typing a fresh config we don't interrupt.
        if user_input is None:
            legacy_entries = self.hass.config_entries.async_entries("vistapool")
            if legacy_entries:
                self._legacy_entry_id = legacy_entries[0].entry_id
                self._legacy_entry_title = legacy_entries[0].title
                return await self.async_step_import_from_vistapool()

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

            # Validation 3: Duplicate prevention (unique_id based on serial)
            unique_id = f"neopool_{serial_number}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            # Validation 3b: Catch unmigrated v1 entries (unique_id=None) by connection params
            for entry in self.hass.config_entries.async_entries(DOMAIN):
                if entry.unique_id is not None:
                    continue
                if (
                    entry.data.get(CONF_HOST) == user_input.get(CONF_HOST)
                    and entry.data.get(CONF_PORT) == user_input.get(CONF_PORT)
                    and entry.data.get("slave_id") == user_input.get("slave_id")
                    and entry.data.get("modbus_framer")
                    == user_input.get("modbus_framer")
                ):
                    return self.async_abort(reason="already_configured")

            # Validation 4: Unique device name (compare slugified to catch case/spacing variants)
            for entry in self.hass.config_entries.async_entries(DOMAIN):
                existing_name = entry.data.get(CONF_NAME) or entry.title
                if slugify(existing_name) == slugify(device_name):
                    errors[CONF_NAME] = "name_already_used"
                    return self.async_show_form(
                        step_id="user",
                        data_schema=data_schema,
                        errors=errors,
                    )

            # Coerce types before creating entry
            if "scan_interval" in user_input:
                user_input["scan_interval"] = int(user_input["scan_interval"])

            _LOGGER.info(
                "Creating new NeoPool config entry: %s (serial: …%s)",
                device_name,
                serial_number[-6:],
            )

            return self.async_create_entry(title=device_name, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
        )

    async def async_step_import_from_vistapool(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer to migrate an existing vistapool entry to the new neopool domain.

        On confirmation:
          1. Snapshot device-level customizations (area_id, name_by_user, labels)
             from the device tied to the legacy vistapool entry, so we can
             restore them onto the new neopool device after migration.
          2. Run the cross-domain migration via `migrate_single_entry_cross_domain`
             which retargets entity_registry rows, retargets device_registry rows,
             creates a fresh neopool ConfigEntry mirroring the legacy data, and
             removes the old vistapool entry.
          3. Try to clean up the leftover `custom_components/vistapool/` folder.
          4. Abort the flow with `migration_complete` — the new neopool entry
             was already added by the migration, so we must NOT also call
             `async_create_entry` here (would create a duplicate).

        On decline ("user said no"):
          - Fall through to the regular `async_step_user` form so the user
            can manually configure a fresh, unrelated neopool entry.
        """
        # The legacy entry might have been removed between async_step_user
        # detecting it and the user clicking Submit — re-resolve to be safe.
        legacy_entry = self.hass.config_entries.async_get_entry(self._legacy_entry_id)
        if legacy_entry is None or legacy_entry.domain != "vistapool":
            # Nothing to import any more; fall through to the regular new-entry
            # path. user_input None forces a fresh form display there.
            return await self.async_step_user()

        if user_input is None:
            return self.async_show_form(
                step_id="import_from_vistapool",
                data_schema=vol.Schema({}),
                description_placeholders={
                    "entry_title": self._legacy_entry_title,
                },
            )

        # ── Snapshot device customizations BEFORE migration ──────────────
        # The cross-domain migration retargets the device's identifiers and
        # config_entries, but it doesn't preserve user-set fields like
        # area_id, name_by_user, or labels. We capture them here keyed by
        # the device's serial-based identifier so we can match them onto the
        # new device after migration.
        device_registry = dr.async_get(self.hass)
        snapshots: dict[str, dict[str, Any]] = {}
        for device in dr.async_entries_for_config_entry(
            device_registry, legacy_entry.entry_id
        ):
            # Match the (vistapool, X) tuple — that's the serial-based key
            # the migration will rewrite to (neopool, X).
            serial_key = next(
                (ident for dom, ident in device.identifiers if dom == "vistapool"),
                None,
            )
            if not serial_key:
                continue
            snapshots[serial_key] = {
                "area_id": device.area_id,
                "name_by_user": device.name_by_user,
                "labels": set(device.labels),
                "disabled_by": device.disabled_by,
            }

        # ── Run the cross-domain migration ───────────────────────────────
        try:
            await migrate_single_entry_cross_domain(self.hass, legacy_entry)
        except Exception as exc:
            # Intentionally broad: migration walks entity / device / config
            # registries and the Modbus probe, so it can surface anything
            # from HomeAssistantError to RuntimeError / OSError / NeoPoolError
            # / ValueError. We never want a config-flow step to crash with a
            # traceback — surface the message via abort(migration_failed)
            # and let the user retry.
            _LOGGER.exception(
                "Cross-domain migration failed for %s",
                legacy_entry.entry_id,
            )
            return self.async_abort(
                reason="migration_failed",
                description_placeholders={"error": str(exc)},
            )

        # ── Restore device customizations onto the migrated device ───────
        # The migration kept the device row in place but flipped its
        # identifier to (neopool, serial_key). Find each by that tuple
        # and re-apply the user-set fields.
        for serial_key, snap in snapshots.items():
            device = device_registry.async_get_device(
                identifiers={(DOMAIN, serial_key)}
            )
            if device is None:
                continue
            device_registry.async_update_device(
                device.id,
                area_id=snap["area_id"],
                name_by_user=snap["name_by_user"],
                labels=snap["labels"],
                disabled_by=snap["disabled_by"],
            )

        # ── Clean up the leftover custom_components/vistapool/ folder ────
        await async_cleanup_old_folder(self.hass)

        # ── End the flow ─────────────────────────────────────────────────
        # `migrate_single_entry_cross_domain` already created and added the
        # new neopool entry to hass.config_entries, so we must NOT call
        # async_create_entry here. Aborting with a friendly reason gives the
        # user a confirmation dialog ("migration completed").
        return self.async_abort(reason="migration_complete")

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
                # Verify the device serial matches this entry's unique_id
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
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> NeoPoolOptionsFlowHandler:
        """Return the options flow handler for this entry."""
        return NeoPoolOptionsFlowHandler()
