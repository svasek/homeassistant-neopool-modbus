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

"""NeoPool integration for Home Assistant."""

from collections.abc import Mapping
from typing import Any

from modbus_connection import ModbusTcpParams
from neopool_modbus import NeoPoolModbusClient
from neopool_modbus.registers import framer_to_socket_name

from homeassistant.components.modbus import async_get_unit
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import CONF_MODBUS_FRAMER, CONF_UNIT_ID, DEFAULT_PORT, DOMAIN, PLATFORMS
from .coordinator import NeoPoolConfigEntry, NeoPoolCoordinator

# Re-exported for Home Assistant, HA discovers async_migrate_entry from __init__.
from .migration import (
    async_cleanup_legacy_files,
    async_migrate_entry,
    cleanup_removed_entities,
    rename_renamed_entities,
)
from .services import async_setup_services

# CUSTOM-ONLY START, re-exports the migration symbol for HA's discovery.
__all__ = ["async_migrate_entry"]
# CUSTOM-ONLY END

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def _build_modbus_params(data: Mapping[str, Any]) -> ModbusTcpParams:
    """Build the shared-connection link parameters from config entry data.

    A Modbus TCP link is always MBAP-framed, so the framer is omitted for it
    (passing it is deprecated). RTU/ASCII-over-TCP still names its framer; the
    modbus integration canonicalises that to a serial link over a ``socket://``
    device itself, so there is nothing more to translate here.
    """
    host = data[CONF_HOST]
    port = data.get(CONF_PORT, DEFAULT_PORT)
    framer = framer_to_socket_name(data.get(CONF_MODBUS_FRAMER, "tcp"))
    if framer == "socket":
        return ModbusTcpParams(host=host, port=port)
    return ModbusTcpParams(host=host, port=port, framer=framer)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the NeoPool integration."""
    async_setup_services(hass)
    return True


def _async_build_client(
    hass: HomeAssistant, entry: NeoPoolConfigEntry
) -> NeoPoolModbusClient:
    """Build the client, borrowing a shared Modbus unit from the modbus integration.

    Several integrations on one device share a single connection this way, and
    it appears in the Modbus connections panel.
    """
    try:
        unit = async_get_unit(
            hass,
            entry,
            _build_modbus_params(entry.data),
            entry.data.get(CONF_UNIT_ID, 1),
        )
    except HomeAssistantError as err:
        # The device is already in use over different link settings, which one
        # shared connection cannot honour.
        raise ConfigEntryNotReady(str(err)) from err

    return NeoPoolModbusClient(entry.data, unit=unit)


async def async_setup_entry(hass: HomeAssistant, entry: NeoPoolConfigEntry) -> bool:
    """Set up the NeoPool integration from a config entry."""
    client = _async_build_client(hass, entry)
    coordinator = NeoPoolCoordinator(hass, client, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # CUSTOM-ONLY START
    cleanup_removed_entities(hass, entry)
    rename_renamed_entities(hass, entry)
    # CUSTOM-ONLY END

    # CUSTOM-ONLY START, HACS does not prune deleted files on upgrade,
    # so we sweep modules whose implementation moved to neopool-modbus.
    await async_cleanup_legacy_files(hass)
    # CUSTOM-ONLY END

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # The first refresh ran before any entity registered its context, so
    # context-gated timer blocks were skipped; seed one more read now that
    # every context exists instead of waiting for the next scheduled poll.
    await coordinator.async_refresh()

    return True


async def async_unload_entry(hass: HomeAssistant, entry: NeoPoolConfigEntry) -> bool:
    """Unload a NeoPool config entry."""
    coordinator = entry.runtime_data
    coordinator.cancel_follow_up_refresh()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and coordinator.client is not None:
        await coordinator.client.close()
    return unload_ok
