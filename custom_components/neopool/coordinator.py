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

"""Data update coordinator for the NeoPool integration."""

from datetime import timedelta
import json
import logging
from typing import Any, override

from neopool_modbus import NeoPoolModbusClient
from neopool_modbus.decoders import aggregate_filtration_remaining
from neopool_modbus.exceptions import NeoPoolError
from neopool_modbus.registers import (
    MAX_RELAY_GPIO,
    TIMER_BLOCKS,
    SetpointKind,
    find_corrupted_gpio_registers,
    is_valid_relay_gpio,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CAPABILITY_KEYS,
    CONF_AUTO_TIME_SYNC,
    CONF_CAPABILITIES,
    CONF_DEV_OVERRIDES,
    CONF_DEV_OVERRIDES_ENABLED,
    CONF_FILTRATION_PUMP_POWER,
    CONF_SCAN_INTERVAL,
    CONF_USE_LIGHT,
    CONF_WINTER_MODE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    FOLLOW_UP_REFRESH_DELAY,
)
from .helpers import is_device_time_out_of_sync, prepare_device_time

_FILT_TIMERS = ("filtration1", "filtration2", "filtration3")

_LOGGER = logging.getLogger(__name__)


type NeoPoolConfigEntry = ConfigEntry["NeoPoolCoordinator"]


class NeoPoolCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for NeoPool platform."""

    client: NeoPoolModbusClient
    config_entry: NeoPoolConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        client: NeoPoolModbusClient,
        entry: NeoPoolConfigEntry,
    ) -> None:
        """Initialise the NeoPool data update coordinator."""
        # CUSTOM-ONLY START, HACS-only per-instance polling-interval override.
        update_interval = timedelta(
            seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        # CUSTOM-ONLY END

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} coordinator",
            update_interval=update_interval,
            config_entry=entry,
        )
        self.client = client
        self.auto_time_sync = entry.options.get(CONF_AUTO_TIME_SYNC, False)
        self.winter_mode = entry.options.get(CONF_WINTER_MODE, False)
        # Persisted in options for winter mode (no Modbus reads).
        self._capability_snapshot: dict[str, Any] = dict(
            entry.options.get(CONF_CAPABILITIES, {})
        )
        self._follow_up_unsub: CALLBACK_TYPE | None = None
        # None (not frozenset()) so the first poll clears any stale issue
        # persisted from a previous session.
        self._corrupted_gpio_state: frozenset[tuple[str, int]] | None = None

    def request_refresh_with_followup(
        self, delay: float = FOLLOW_UP_REFRESH_DELAY
    ) -> None:
        """Schedule a follow-up refresh after a delay.

        The follow-up catches delayed device state changes that may not
        be visible in Modbus registers immediately after a write.
        """
        self._schedule_follow_up_refresh(delay)

    def cancel_follow_up_refresh(self) -> None:
        """Cancel any pending follow-up refresh."""
        if self._follow_up_unsub:
            self._follow_up_unsub()
            self._follow_up_unsub = None

    def _schedule_follow_up_refresh(self, delay: float) -> None:
        """Schedule a delayed follow-up refresh."""
        self.cancel_follow_up_refresh()

        @callback
        def _do_refresh(_now: Any) -> None:
            self._follow_up_unsub = None
            self.hass.async_create_task(self.async_request_refresh())

        self._follow_up_unsub = async_call_later(self.hass, delay, _do_refresh)

    def _check_gpio_registers(self, data: dict) -> None:
        """Validate GPIO register values and (re-)raise or clear the repair issue."""
        corrupted = find_corrupted_gpio_registers(data)
        corrupted_state = frozenset((key, value) for key, _, value in corrupted)

        if corrupted_state == self._corrupted_gpio_state:
            return

        for key, label, value in corrupted:
            _LOGGER.error(
                "Corrupted GPIO register %s (%s): value %d (0x%04X) is outside "
                "valid range 0-%d. The pool controller may malfunction",
                key,
                label,
                value,
                value & 0xFFFF,
                MAX_RELAY_GPIO,
            )

        self._corrupted_gpio_state = corrupted_state

        if corrupted:
            details = "\n".join(
                f"- **{label}** (`{key}`): value **{value}** (expected 0-{MAX_RELAY_GPIO})"
                for key, label, value in corrupted
            )
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                "corrupted_gpio",
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key="corrupted_gpio",
                translation_placeholders={"details": details},
            )
        else:
            # Clear a previously raised repair issue once the device is healthy.
            ir.async_delete_issue(self.hass, DOMAIN, "corrupted_gpio")

    def _get_enabled_timers(self) -> list[str]:
        """Return the list of timer block names enabled in entry options."""
        options = self.config_entry.options
        data = self.data or {}
        enabled: list[str] = []
        for key in TIMER_BLOCKS:
            if key.startswith("relay_aux"):
                option_key = f"use_aux{key[len('relay_aux')]}"
            elif key == "relay_light":
                option_key = CONF_USE_LIGHT
            else:
                option_key = f"use_{key}"
            if not options.get(option_key, False):
                continue
            # Skip if the lighting GPIO is invalid; the light entity gates
            # on the same condition, so relay_light_enable has no consumer.
            if key == "relay_light" and not is_valid_relay_gpio(
                data.get("MBF_PAR_LIGHTING_GPIO", 0) or 0
            ):
                continue
            enabled.append(key)
        for ft in _FILT_TIMERS:
            if ft not in enabled:
                enabled.append(ft)
        return enabled

    async def _read_timers_into_data(self, data: dict[str, Any]) -> None:
        """Read every enabled timer block and merge derived fields into data."""
        prev_remaining = self.data.get("FILTRATION_REMAINING") if self.data else None
        filtration_active = bool(data.get("Filtration Pump")) or bool(
            prev_remaining and prev_remaining > 0
        )
        timers = await self.client.read_all_timers(
            enabled_timers=self._get_enabled_timers(),
            force_read=_FILT_TIMERS if filtration_active else None,
        )
        for t_name, t in timers.items():
            data[f"{t_name}_enable"] = t["enable"]
            data[f"{t_name}_start"] = t["on"]  # seconds since midnight
            data[f"{t_name}_interval"] = t["interval"]
            data[f"{t_name}_period"] = t["period"]
            data[f"{t_name}_countdown"] = t["countdown"]
            data[f"{t_name}_stop"] = t.get("stop")

        data["FILTRATION_REMAINING"] = aggregate_filtration_remaining(data)

    # CUSTOM-ONLY START, HACS-only dev override hatch for live data injection.
    def _apply_dev_overrides(self, data: dict[str, Any]) -> None:
        """Apply developer override values to data, if enabled."""
        if not self.config_entry.options.get(CONF_DEV_OVERRIDES_ENABLED, False):
            return
        raw = self.config_entry.options.get(CONF_DEV_OVERRIDES, "{}")
        try:
            overrides = json.loads(raw) if isinstance(raw, str) else raw
        except (
            json.JSONDecodeError,
            TypeError,
            ValueError,
        ) as dev_err:  # pragma: no cover
            _LOGGER.warning("Failed to apply dev_overrides: %s", dev_err)
            return
        if not isinstance(overrides, dict):  # pragma: no cover
            _LOGGER.warning("Developer overrides must be a JSON object (dict)")
            return
        data.update(overrides)
        _LOGGER.debug("Applied dev overrides: %s", overrides)

    # CUSTOM-ONLY END

    async def _sync_heating_intelligent_setpoints(self, data: dict[str, Any]) -> None:
        """Keep heating and intelligent setpoints synchronized last-change-wins."""
        prev = self.data
        heat = data.get("MBF_PAR_HEATING_TEMP")
        intel = data.get("MBF_PAR_INTELLIGENT_TEMP")
        if heat is None or intel is None or heat == intel:
            return
        h_old = prev.get("MBF_PAR_HEATING_TEMP") if prev else None
        i_old = prev.get("MBF_PAR_INTELLIGENT_TEMP") if prev else None
        heating_changed = h_old is None or heat != h_old
        intelligent_changed = i_old is None or intel != i_old

        if heating_changed ^ intelligent_changed:
            winner_val = int(heat if heating_changed else intel)
            loser_kind = (
                SetpointKind.INTELLIGENT if heating_changed else SetpointKind.HEATING
            )
            await self.client.async_set_setpoint(loser_kind, winner_val, apply=True)
            data["MBF_PAR_HEATING_TEMP"] = winner_val
            data["MBF_PAR_INTELLIGENT_TEMP"] = winner_val
            _LOGGER.debug(
                "Auto-synced setpoints (last-change-wins) -> heating=%s, intelligent=%s",
                data["MBF_PAR_HEATING_TEMP"],
                data["MBF_PAR_INTELLIGENT_TEMP"],
            )
        elif heating_changed and intelligent_changed:
            _LOGGER.warning(
                "Both heating and intelligent setpoints changed simultaneously "
                "(heating: %s→%s, intelligent: %s→%s). Reverting both to previous values to prevent conflict",
                h_old,
                heat,
                i_old,
                intel,
            )
            if h_old is not None and i_old is not None:
                await self.client.async_set_setpoint(
                    SetpointKind.HEATING, int(h_old), apply=False
                )
                await self.client.async_set_setpoint(
                    SetpointKind.INTELLIGENT, int(i_old), apply=True
                )
                data["MBF_PAR_HEATING_TEMP"] = h_old
                data["MBF_PAR_INTELLIGENT_TEMP"] = i_old
                _LOGGER.debug(
                    "Reverted setpoints -> heating=%s, intelligent=%s",
                    data["MBF_PAR_HEATING_TEMP"],
                    data["MBF_PAR_INTELLIGENT_TEMP"],
                )
        else:
            _LOGGER.info(
                "Setpoints differ but neither changed (heating=%s, intelligent=%s). "
                "Performing initial sync: setting intelligent to match heating",
                heat,
                intel,
            )
            await self.client.async_set_setpoint(
                SetpointKind.INTELLIGENT, int(heat), apply=True
            )
            data["MBF_PAR_INTELLIGENT_TEMP"] = heat
            _LOGGER.debug(
                "Initial sync completed -> heating=%s, intelligent=%s",
                data["MBF_PAR_HEATING_TEMP"],
                data["MBF_PAR_INTELLIGENT_TEMP"],
            )

    def _persist_capability_snapshot(self, data: dict[str, Any]) -> None:
        """Persist the capability snapshot so platform setup survives HA restarts."""
        new_snapshot = {k: data[k] for k in CAPABILITY_KEYS if k in data}
        if new_snapshot == self._capability_snapshot:
            return
        self._capability_snapshot = new_snapshot
        options = dict(self.config_entry.options)
        options[CONF_CAPABILITIES] = new_snapshot
        self.hass.config_entries.async_update_entry(self.config_entry, options=options)

    @override
    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch the latest data from the pool controller."""
        if self.winter_mode:
            _LOGGER.debug("Winter mode active - skipping Modbus communication")
            return self.data if self.data is not None else self._capability_snapshot

        try:
            data = await self.client.async_read_all()
            await self._read_timers_into_data(data)

            if self.auto_time_sync and is_device_time_out_of_sync(data, self.hass):
                _LOGGER.debug("Device time is out of sync, updating")
                await self.client.async_sync_device_time(prepare_device_time(self.hass))
        except (NeoPoolError, OSError, TimeoutError) as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="modbus_communication_error",
                translation_placeholders={"error": str(err)},
            ) from err

        self._check_gpio_registers(data)

        pump_power = max(
            0, int(self.config_entry.options.get(CONF_FILTRATION_PUMP_POWER, 0) or 0)
        )
        data[CONF_FILTRATION_PUMP_POWER] = (
            pump_power if data.get("Filtration Pump") else 0
        )

        # CUSTOM-ONLY START
        self._apply_dev_overrides(data)
        # CUSTOM-ONLY END

        try:
            await self._sync_heating_intelligent_setpoints(data)
        except Exception as sync_err:  # noqa: BLE001  # pragma: no cover
            _LOGGER.debug("Setpoint auto-sync skipped due to error: %s", sync_err)

        self._persist_capability_snapshot(data)
        return data

    async def set_auto_time_sync(self, enabled: bool) -> None:
        """Persist the auto_time_sync flag and refresh the entry options."""
        self.auto_time_sync = enabled
        options = dict(self.config_entry.options)
        options[CONF_AUTO_TIME_SYNC] = enabled
        self.hass.config_entries.async_update_entry(self.config_entry, options=options)

    async def set_winter_mode(self, enabled: bool) -> None:
        """Toggle winter mode and persist the capability snapshot."""
        self.winter_mode = enabled
        options = dict(self.config_entry.options)
        options[CONF_WINTER_MODE] = enabled
        if enabled:
            if self.data:
                self._capability_snapshot = {
                    k: self.data[k] for k in CAPABILITY_KEYS if k in self.data
                }
            options[CONF_CAPABILITIES] = dict(self._capability_snapshot)
        self.hass.config_entries.async_update_entry(self.config_entry, options=options)
        if enabled:
            self.async_set_updated_data(dict(self._capability_snapshot))
