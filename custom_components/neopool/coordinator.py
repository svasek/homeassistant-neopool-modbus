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
from typing import Any

from neopool_modbus import NeoPoolModbusClient
from neopool_modbus.decoders import parse_version
from neopool_modbus.exceptions import NeoPoolError
from neopool_modbus.registers import (
    COPY_TO_RTC_REGISTER,
    HEATING_SETPOINT_REGISTER,
    INTELLIGENT_SETPOINT_REGISTER,
    MAX_RELAY_GPIO,
    TIMER_BLOCKS,
)

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import slugify

from .const import (
    CAPABILITY_KEYS,
    CONF_FILTRATION_PUMP_POWER,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    FOLLOW_UP_REFRESH_DELAY,
    GPIO_REGISTERS,
)
from .helpers import is_device_time_out_of_sync, prepare_device_time

MAX_SCAN_INTERVAL = timedelta(seconds=180)  # Maximum allowed scan interval (3 minutes)

_FILT_TIMERS = ("filtration1", "filtration2", "filtration3")

_LOGGER = logging.getLogger(__name__)


class NeoPoolCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for NeoPool platform."""

    client: NeoPoolModbusClient

    def __init__(
        self,
        hass: HomeAssistant,
        client: NeoPoolModbusClient,
        entry: ConfigEntry,
        entry_id: str,
    ) -> None:
        """Initialise the NeoPool data update coordinator."""
        # Store normal and maximal intervals
        self.normal_update_interval = timedelta(
            seconds=entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)
        )
        self.max_update_interval = min(
            self.normal_update_interval * 4, MAX_SCAN_INTERVAL
        )
        self._consecutive_errors = 0

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} coordinator",
            update_interval=self.normal_update_interval,
            config_entry=entry,
        )
        self.client = client
        self.entry = entry
        self.entry_id = entry_id
        self.device_name = entry.data.get(CONF_NAME, DOMAIN)
        self.auto_time_sync = self.entry.options.get("auto_time_sync", False)
        self.winter_mode = self.entry.options.get("winter_mode", False)
        # Capability snapshot: persisted in options so platform setup survives restarts
        # in winter mode (where no real Modbus read occurs to populate coordinator.data).
        self._capability_snapshot: dict[str, Any] = dict(
            entry.options.get("_capabilities", {})
        )
        self._firmware = "?"
        self._model = "Unknown"
        self._follow_up_unsub: CALLBACK_TYPE | None = None
        self._gpio_checked = False

    def request_refresh_with_followup(
        self, delay: float = FOLLOW_UP_REFRESH_DELAY
    ) -> None:
        """Schedule a follow-up refresh after a delay.

        The follow-up catches delayed device state changes that may not
        be visible in Modbus registers immediately after a write.
        No immediate refresh is performed — callers should apply optimistic
        state updates before calling this method.
        If called again before the previous follow-up fires, the old one
        is cancelled to avoid stacking.
        """
        self._schedule_follow_up_refresh(delay)

    def cancel_follow_up_refresh(self) -> None:
        """Cancel any pending follow-up refresh (e.g. on config entry unload)."""
        if self._follow_up_unsub:
            self._follow_up_unsub()
            self._follow_up_unsub = None

    def _schedule_follow_up_refresh(self, delay: float) -> None:
        """Schedule a delayed follow-up refresh."""
        if self._follow_up_unsub:
            self._follow_up_unsub()
            self._follow_up_unsub = None

        @callback
        def _do_refresh(_now: Any) -> None:
            self._follow_up_unsub = None
            self.hass.async_create_task(self.async_request_refresh())

        self._follow_up_unsub = async_call_later(self.hass, delay, _do_refresh)

    def _check_gpio_registers(self, data: dict) -> None:
        """Validate GPIO register values after first successful read.

        GPIO registers assign physical relay outputs (valid range 0-MAX_RELAY_GPIO).
        A value outside this range indicates register corruption, which can happen
        when the Modbus gateway framing mode does not match the integration's framer
        setting (e.g. transparent gateway with TCP framer).
        """
        corrupted = []
        for key, label in GPIO_REGISTERS.items():
            value = data.get(key)
            if value is not None and not (0 <= value <= MAX_RELAY_GPIO):
                corrupted.append((key, label, value))
                _LOGGER.error(
                    "Corrupted GPIO register %s (%s): value %d (0x%04X) is outside "
                    "valid range 0-%d. The pool controller may malfunction",
                    key,
                    label,
                    value,
                    value & 0xFFFF,
                    MAX_RELAY_GPIO,
                )

        # Dismiss legacy persistent notification from versions before repair-issues migration
        persistent_notification.async_dismiss(self.hass, f"{DOMAIN}_corrupted_gpio")

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
            # Clear any previous issue if registers are now valid
            ir.async_delete_issue(self.hass, DOMAIN, "corrupted_gpio")
            _LOGGER.info("GPIO registers passed sanity check: all values are valid")

    def _get_enabled_timers(self) -> list[str]:
        """Return the list of timer block names enabled in entry options.

        Filtration timer blocks are always included so the countdown
        aggregation has fresh data even when the user hasn't enabled
        their configuration entities.
        """
        options = self.entry.options
        enabled: list[str] = []
        for key in TIMER_BLOCKS:
            if key.startswith("relay_aux"):
                option_key = f"use_aux{key[len('relay_aux')]}"
            elif key == "relay_light":
                option_key = "use_light"
            else:
                option_key = f"use_{key}"
            if options.get(option_key, False):
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
            data[f"{t_name}_start"] = t["on"]  # saved as seconds since midnight
            data[f"{t_name}_interval"] = t["interval"]
            data[f"{t_name}_period"] = t["period"]
            data[f"{t_name}_countdown"] = t["countdown"]
            if t["on"] is not None and t["interval"] is not None:
                data[f"{t_name}_stop"] = (t["on"] + t["interval"]) % 86400
            else:
                data[f"{t_name}_stop"] = None

        # Aggregate filtration remaining time from active filtration timers
        filt_remaining: int | None = None
        for n in (1, 2, 3):
            cd = data.get(f"filtration{n}_countdown")
            if cd is not None and cd > 0:
                filt_remaining = max(filt_remaining or 0, cd)
        data["FILTRATION_REMAINING"] = filt_remaining

    def _apply_dev_overrides(self, data: dict[str, Any]) -> None:
        """Apply developer override values to data, if enabled."""
        if not self.entry.options.get("dev_overrides_enabled", False):
            return
        raw = self.entry.options.get("dev_overrides", "{}")
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

    async def _sync_heating_intelligent_setpoints(self, data: dict[str, Any]) -> None:
        """Keep heating and intelligent setpoints synchronized last-change-wins.

        If exactly one register changed since the previous snapshot, mirror
        it to the other. If both changed in the same cycle, revert both to
        their previous values to avoid conflicts. If neither changed but
        the values differ, perform an initial sync using heating as the
        source of truth.
        """
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
            # Exactly one changed: sync the other to match (last-change-wins)
            winner_val = int(heat if heating_changed else intel)
            loser_reg = (
                INTELLIGENT_SETPOINT_REGISTER
                if heating_changed
                else HEATING_SETPOINT_REGISTER
            )
            await self.client.async_write_register(loser_reg, winner_val, apply=True)
            data["MBF_PAR_HEATING_TEMP"] = winner_val
            data["MBF_PAR_INTELLIGENT_TEMP"] = winner_val
            _LOGGER.debug(
                "Auto-synced setpoints (last-change-wins) -> heating=%s, intelligent=%s",
                data["MBF_PAR_HEATING_TEMP"],
                data["MBF_PAR_INTELLIGENT_TEMP"],
            )
        elif heating_changed and intelligent_changed:
            # Both changed this cycle; revert both to previous values
            _LOGGER.warning(
                "Both heating and intelligent setpoints changed simultaneously "
                "(heating: %s→%s, intelligent: %s→%s). Reverting both to previous values to prevent conflict.",
                h_old,
                heat,
                i_old,
                intel,
            )
            if h_old is not None and i_old is not None:
                await self.client.async_write_register(
                    HEATING_SETPOINT_REGISTER, int(h_old), apply=False
                )
                await self.client.async_write_register(
                    INTELLIGENT_SETPOINT_REGISTER, int(i_old), apply=True
                )
                data["MBF_PAR_HEATING_TEMP"] = h_old
                data["MBF_PAR_INTELLIGENT_TEMP"] = i_old
                _LOGGER.debug(
                    "Reverted setpoints -> heating=%s, intelligent=%s",
                    data["MBF_PAR_HEATING_TEMP"],
                    data["MBF_PAR_INTELLIGENT_TEMP"],
                )
        else:
            # Neither changed but they differ: initial sync (heating wins)
            _LOGGER.info(
                "Setpoints differ but neither changed (heating=%s, intelligent=%s). "
                "Performing initial sync: setting intelligent to match heating",
                heat,
                intel,
            )
            await self.client.async_write_register(
                INTELLIGENT_SETPOINT_REGISTER, int(heat), apply=True
            )
            data["MBF_PAR_INTELLIGENT_TEMP"] = heat
            _LOGGER.debug(
                "Initial sync completed -> heating=%s, intelligent=%s",
                data["MBF_PAR_HEATING_TEMP"],
                data["MBF_PAR_INTELLIGENT_TEMP"],
            )

    def _persist_capability_snapshot(self, data: dict[str, Any]) -> None:
        """Persist the capability snapshot so platform setup survives HA restarts.

        While Modbus is down (e.g. because winter mode is on), platforms
        still need to know which entities to register; the snapshot stored
        in entry.options gives them that visibility.
        """
        new_snapshot = {k: data[k] for k in CAPABILITY_KEYS if k in data}
        if new_snapshot == self._capability_snapshot:
            return
        self._capability_snapshot = new_snapshot
        options = dict(self.entry.options)
        options["_capabilities"] = new_snapshot
        self.hass.config_entries.async_update_entry(self.entry, options=options)

    async def _handle_modbus_failure(self, err: Exception) -> None:
        """Increment the error counter and slow down polling exponentially."""
        self._consecutive_errors += 1
        _LOGGER.error("Modbus communication error: %s (%s)", err, type(err).__name__)
        current_interval = self.update_interval or self.normal_update_interval
        next_interval = min(current_interval * 2, self.max_update_interval)
        if self.update_interval != next_interval:
            _LOGGER.warning(
                "Increasing update interval to %s seconds due to communication errors",
                int(next_interval.total_seconds()),
            )
            self.update_interval = next_interval
        _LOGGER.warning("Modbus error - marking all entities unavailable")

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch the latest data from the pool controller."""
        # Winter mode: skip all Modbus communication; entities remain but show unknown values
        if self.winter_mode:
            _LOGGER.debug("Winter mode active - skipping Modbus communication")
            return self.data if self.data is not None else self._capability_snapshot

        try:
            data = await self.client.async_read_all()
        except (NeoPoolError, OSError, TimeoutError) as err:
            await self._handle_modbus_failure(err)
            raise UpdateFailed(f"Modbus communication error: {err}") from err

        self._consecutive_errors = 0

        # Reset interval after success
        if self.update_interval != self.normal_update_interval:  # pragma: no cover
            _LOGGER.info(
                "Communication OK, resetting update interval to %s seconds",
                self.normal_update_interval.total_seconds(),
            )
            self.update_interval = self.normal_update_interval

        self._firmware = parse_version(data.get("MBF_POWER_MODULE_VERSION"))
        self._model = "NeoPool"

        # One-time GPIO sanity check after first successful read
        if not self._gpio_checked:
            self._gpio_checked = True
            self._check_gpio_registers(data)

        await self._read_timers_into_data(data)

        pump_power = max(
            0, int(self.entry.options.get(CONF_FILTRATION_PUMP_POWER, 0) or 0)
        )
        data[CONF_FILTRATION_PUMP_POWER] = (
            pump_power if data.get("Filtration Pump") else 0
        )

        if self.auto_time_sync and is_device_time_out_of_sync(data, self.hass):
            _LOGGER.debug("Device time is out of sync, updating...")
            await self.client.async_write_register(
                0x0408, prepare_device_time(self.hass)
            )
            await self.client.async_write_register(COPY_TO_RTC_REGISTER, 1)

        self._apply_dev_overrides(data)

        try:
            await self._sync_heating_intelligent_setpoints(data)
        except Exception as sync_err:  # noqa: BLE001  # pragma: no cover
            # Setpoint sync is best-effort: it walks coordinator data and
            # writes a register, so anything from KeyError / TypeError /
            # ValueError up to NeoPoolError / OSError can surface here. A
            # failed sync must not poison the rest of the update cycle.
            _LOGGER.debug("Setpoint auto-sync skipped due to error: %s", sync_err)

        self._persist_capability_snapshot(data)
        return data

    async def set_auto_time_sync(self, enabled: bool):
        """Persist the auto_time_sync flag and refresh the entry options."""
        self.auto_time_sync = enabled
        # Update the entry options to reflect the change
        # This is necessary to persist the setting across restarts
        # and to ensure that the coordinator uses the updated value
        # when fetching data
        options = dict(self.entry.options)
        options["auto_time_sync"] = enabled
        self.hass.config_entries.async_update_entry(self.entry, options=options)

    async def set_winter_mode(self, enabled: bool):
        """Toggle winter mode and persist the capability snapshot."""
        self.winter_mode = enabled
        options = dict(self.entry.options)
        options["winter_mode"] = enabled
        if enabled:
            # Refresh snapshot from live data (if available) and persist so that
            # platform setup can reconstruct the correct entity set after a restart.
            if self.data:
                self._capability_snapshot = {
                    k: self.data[k] for k in CAPABILITY_KEYS if k in self.data
                }
            options["_capabilities"] = dict(self._capability_snapshot)
        self.hass.config_entries.async_update_entry(self.entry, options=options)
        if enabled:
            self.async_set_updated_data(dict(self._capability_snapshot))

    @property
    def firmware(self) -> str:
        """Return the device firmware version string."""
        return self._firmware

    @property
    def model(self) -> str:
        """Return the device model string."""
        return self._model

    @property
    def device_slug(self) -> str:  # pragma: no cover
        """Return the slugified device name used as object_id prefix."""
        return slugify(self.device_name)
