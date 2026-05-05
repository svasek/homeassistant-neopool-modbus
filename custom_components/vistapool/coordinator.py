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

"""VistaPool Integration for Home Assistant - Coordinator Module"""

import json
import logging
from datetime import timedelta

from homeassistant.components import persistent_notification
from homeassistant.const import CONF_NAME
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import slugify

from .const import (
    CAPABILITY_KEYS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    FOLLOW_UP_REFRESH_DELAY,
    GPIO_REGISTERS,
    HEATING_SETPOINT_REGISTER,
    INTELLIGENT_SETPOINT_REGISTER,
    MAX_RELAY_GPIO,
    TIMER_BLOCKS,
)
from .helpers import is_device_time_out_of_sync, parse_version, prepare_device_time

MAX_SCAN_INTERVAL = timedelta(seconds=180)  # Maximum allowed scan interval (3 minutes)

_FILT_TIMERS = ("filtration1", "filtration2", "filtration3")

_LOGGER = logging.getLogger(__name__)


class VistaPoolCoordinator(DataUpdateCoordinator):
    """Coordinator for VistaPool platform."""

    def __init__(self, hass: HomeAssistant, client, entry, entry_id: str):
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
        self._capability_snapshot: dict = dict(entry.options.get("_capabilities", {}))
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
        def _do_refresh(_now) -> None:
            self._follow_up_unsub = None
            self.hass.async_create_task(self.async_request_refresh())

        self._follow_up_unsub = async_call_later(self.hass, delay, _do_refresh)

    def _check_gpio_registers(self, data: dict) -> None:
        """Validate GPIO register values after first successful read.

        GPIO registers assign physical relay outputs (valid range 0–MAX_RELAY_GPIO).
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
                    "valid range 0–%d. The pool controller may malfunction",
                    key,
                    label,
                    value,
                    value & 0xFFFF,
                    MAX_RELAY_GPIO,
                )

        if corrupted:
            details = "\n".join(
                f"- **{label}** (`{key}`): value **{value}** (expected 0–{MAX_RELAY_GPIO})"
                for key, label, value in corrupted
            )
            persistent_notification.async_create(
                self.hass,
                title="VistaPool: Corrupted GPIO register(s) detected",
                message=(
                    f"The following GPIO register(s) on your pool controller contain "
                    f"invalid values:\n\n{details}\n\n"
                    f"This typically happens when the Modbus gateway framing mode "
                    f"does not match the integration's framer setting. "
                    f"The affected function(s) will not work correctly until the "
                    f"register(s) are restored to valid values.\n\n"
                    f"See the integration documentation for repair instructions."
                ),
                notification_id=f"{DOMAIN}_corrupted_gpio",
            )
        else:
            # Clear any previous notification if registers are now valid
            persistent_notification.async_dismiss(self.hass, f"{DOMAIN}_corrupted_gpio")
            _LOGGER.info("GPIO registers passed sanity check: all values are valid")

    async def _async_update_data(self):
        # Winter mode: skip all Modbus communication; entities remain but show unknown values
        if self.winter_mode:
            _LOGGER.debug("Winter mode active – skipping Modbus communication")
            return self.data if self.data is not None else self._capability_snapshot

        try:
            data = await self.client.async_read_all()
            self._consecutive_errors = 0

            # Reset interval after success
            if self.update_interval != self.normal_update_interval:  # pragma: no cover
                _LOGGER.info(
                    "Communication OK, resetting update interval to %s seconds.",
                    self.normal_update_interval.total_seconds(),
                )
                self.update_interval = self.normal_update_interval

            self._firmware = parse_version(data.get("MBF_POWER_MODULE_VERSION"))
            self._model = "VistaPool"

            # One-time GPIO sanity check after first successful read
            if not self._gpio_checked:
                self._gpio_checked = True
                self._check_gpio_registers(data)

            options = self.entry.options
            enabled_timers = []
            # Collect enabled timers based on options
            # This assumes that the options are set correctly in the config entry
            for key in TIMER_BLOCKS:
                if key.startswith("relay_aux"):
                    n = key[len("relay_aux")]
                    option_key = f"use_aux{n}"
                elif key == "relay_light":
                    option_key = "use_light"
                else:
                    option_key = f"use_{key}"
                if options.get(option_key, False):
                    enabled_timers.append(key)

            # Always read filtration timer blocks for countdown aggregation,
            # even if the user hasn't enabled their configuration entities.
            for ft in _FILT_TIMERS:
                if ft not in enabled_timers:
                    enabled_timers.append(ft)

            # Bypass the notification cache for filtration timers while
            # filtration is running so the countdown values stay fresh.
            # Use both the relay bit and the previous countdown to avoid
            # missing cycles when the relay bit is unreliable.
            prev_remaining = (
                self.data.get("FILTRATION_REMAINING") if self.data else None
            )
            filtration_active = bool(data.get("Filtration Pump")) or bool(
                prev_remaining and prev_remaining > 0
            )
            timers = await self.client.read_all_timers(
                enabled_timers=enabled_timers,
                force_read=_FILT_TIMERS if filtration_active else None,
            )

            for t_name, t in timers.items():
                data[f"{t_name}_enable"] = t["enable"]
                data[f"{t_name}_start"] = t["on"]  # saved as seconds since midnight
                data[f"{t_name}_interval"] = t["interval"]
                data[f"{t_name}_period"] = t["period"]
                data[f"{t_name}_countdown"] = t["countdown"]
                if t["on"] is not None and t["interval"] is not None:
                    stop = (t["on"] + t["interval"]) % 86400
                    data[f"{t_name}_stop"] = stop
                else:
                    data[f"{t_name}_stop"] = None

            # Aggregate filtration remaining time from active filtration timers
            filt_remaining = None
            for n in (1, 2, 3):
                cd = data.get(f"filtration{n}_countdown")
                if cd is not None and cd > 0:
                    filt_remaining = max(filt_remaining or 0, cd)
            data["FILTRATION_REMAINING"] = filt_remaining

            if self.auto_time_sync:
                if is_device_time_out_of_sync(data, self.hass):
                    _LOGGER.debug("Device time is out of sync, updating...")
                    await self.client.async_write_register(
                        0x0408, prepare_device_time(self.hass)
                    )
                    await self.client.async_write_register(0x04F0, 1)

            # Apply developer overrides (for testing UI visibility without hardware)
            try:
                if self.entry.options.get("dev_overrides_enabled", False):
                    raw = self.entry.options.get("dev_overrides", "{}")
                    overrides = json.loads(raw) if isinstance(raw, str) else raw
                    if isinstance(overrides, dict):
                        for k, v in overrides.items():
                            data[k] = v
                        _LOGGER.debug("Applied dev overrides: %s", overrides)
                    else:  # pragma: no cover
                        _LOGGER.warning("dev_overrides must be a JSON object (dict)")
            except Exception as dev_err:  # pragma: no cover
                _LOGGER.warning("Failed to apply dev_overrides: %s", dev_err)

            # Keep heating and intelligent setpoints synchronized based on the last change.
            # If exactly one changed since the previous snapshot and values differ now,
            # mirror the changed value into the other register (last-change-wins).
            # If both changed at once, revert both to previous values to avoid conflicts.
            # If neither changed but they differ, sync intelligent to heating (initial sync).
            try:
                prev = getattr(self, "data", None)
                heat = data.get("MBF_PAR_HEATING_TEMP")
                intel = data.get("MBF_PAR_INTELLIGENT_TEMP")
                if heat is not None and intel is not None and heat != intel:
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
                        await self.client.async_write_register(
                            loser_reg, winner_val, apply=True
                        )
                        # Reflect in returned data so HA shows synced values immediately
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
                            # Write both back to their old values
                            await self.client.async_write_register(
                                HEATING_SETPOINT_REGISTER, int(h_old), apply=False
                            )
                            await self.client.async_write_register(
                                INTELLIGENT_SETPOINT_REGISTER, int(i_old), apply=True
                            )
                            # Reflect revert in returned data
                            data["MBF_PAR_HEATING_TEMP"] = h_old
                            data["MBF_PAR_INTELLIGENT_TEMP"] = i_old
                            _LOGGER.debug(
                                "Reverted setpoints -> heating=%s, intelligent=%s",
                                data["MBF_PAR_HEATING_TEMP"],
                                data["MBF_PAR_INTELLIGENT_TEMP"],
                            )
                    elif not heating_changed and not intelligent_changed:
                        # Neither changed but they differ: initial sync (use heating as source)
                        _LOGGER.info(
                            "Setpoints differ but neither changed (heating=%s, intelligent=%s). "
                            "Performing initial sync: setting intelligent to match heating.",
                            heat,
                            intel,
                        )
                        await self.client.async_write_register(
                            INTELLIGENT_SETPOINT_REGISTER, int(heat), apply=True
                        )
                        # Reflect in returned data
                        data["MBF_PAR_INTELLIGENT_TEMP"] = heat
                        _LOGGER.debug(
                            "Initial sync completed -> heating=%s, intelligent=%s",
                            data["MBF_PAR_HEATING_TEMP"],
                            data["MBF_PAR_INTELLIGENT_TEMP"],
                        )
            except Exception as sync_err:  # pragma: no cover
                _LOGGER.debug("Setpoint auto-sync skipped due to error: %s", sync_err)
            # Keep capability snapshot up-to-date after every successful read and
            # persist it to options so it survives HA restarts while Modbus is down.
            new_snapshot = {k: data[k] for k in CAPABILITY_KEYS if k in data}
            if new_snapshot != self._capability_snapshot:
                self._capability_snapshot = new_snapshot
                options = dict(self.entry.options)
                options["_capabilities"] = new_snapshot
                self.hass.config_entries.async_update_entry(self.entry, options=options)
            return data

        except Exception as err:
            self._consecutive_errors += 1
            _LOGGER.error("Modbus communication error: %s", err)

            # Exponential backoff: double the interval, but never more than max
            current_interval = self.update_interval or self.normal_update_interval
            next_interval = current_interval * 2
            if next_interval > self.max_update_interval:  # pragma: no cover
                next_interval = self.max_update_interval
            if self.update_interval != next_interval:
                _LOGGER.warning(
                    "Increasing update interval to %s seconds due to communication errors.",
                    int(next_interval.total_seconds()),
                )
                self.update_interval = next_interval

            # If we have never received data, prevent the entry from loading.
            if getattr(self, "data", None) is None:
                raise ConfigEntryNotReady(f"Error fetching data: {err}") from err
            # Raise UpdateFailed so the coordinator marks last_update_success=False.
            # All entities (except winter_mode and auto_time_sync switches) become unavailable.
            _LOGGER.warning("Modbus error – marking all entities unavailable")
            raise UpdateFailed(f"Modbus communication error: {err}") from err

    async def set_auto_time_sync(self, enabled: bool):
        self.auto_time_sync = enabled
        # Update the entry options to reflect the change
        # This is necessary to persist the setting across restarts
        # and to ensure that the coordinator uses the updated value
        # when fetching data
        options = dict(self.entry.options)
        options["auto_time_sync"] = enabled
        self.hass.config_entries.async_update_entry(self.entry, options=options)

    async def set_winter_mode(self, enabled: bool):
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
        return self._firmware

    @property
    def model(self) -> str:
        return self._model

    @property
    def device_slug(self):  # pragma: no cover
        return self.entry.unique_id or slugify(self.device_name)
