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

"""
VistaPool Integration for Home Assistant - Helpers Module

This module contains helper functions for the VistaPool integration.
It includes functions to handle device time, prepare data for writing to the device,
and parse version information.
"""

import datetime
import logging

import homeassistant.util.dt as dt_util
from homeassistant.exceptions import ServiceValidationError

_LOGGER = logging.getLogger(__name__)


# This function takes a dictionary of data and returns the device time as a datetime object
# It extracts the low and high parts of the time from the dictionary, combines them into a single timestamp,
# and converts it to a datetime object in UTC timezone
def get_device_time(data, hass=None) -> datetime.datetime | None:
    """Get device time and convert to datetime object."""
    low = data.get("MBF_PAR_TIME_LOW")
    high = data.get("MBF_PAR_TIME_HIGH")
    if low is None or high is None:
        return None
    unix_ts = (high << 16) | low
    if hass:
        local_tz = dt_util.get_time_zone(hass.config.time_zone)
        # WORKAROUND: This is the naive datetime object, without timezone info
        dt_naive = datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=unix_ts)
        dt_local = dt_naive.replace(tzinfo=local_tz)
        dt_utc = dt_local.astimezone(datetime.timezone.utc)
        return dt_utc
    else:
        return datetime.datetime.fromtimestamp(unix_ts, tz=datetime.timezone.utc)


# This function prepares the device time for writing to the device
# It takes the current time in the local timezone and converts it to a format suitable for the device
def prepare_device_time(hass=None) -> list[int]:
    """
    Prepare device time for writing to the device.
    Returns a list of two integers representing the low and high parts of the time.
    """
    if hass:
        ha_tz = dt_util.get_time_zone(hass.config.time_zone)
        now_local = datetime.datetime.now(ha_tz)
        # WORKAROUND: This is the naive datetime object, without timezone info
        epoch_local = datetime.datetime(1970, 1, 1, tzinfo=ha_tz)
        unix_time_local = int((now_local - epoch_local).total_seconds())
    else:  # pragma: no cover
        unix_time_local = int(datetime.datetime.now().timestamp())
    low = unix_time_local & 0xFFFF
    high = (unix_time_local >> 16) & 0xFFFF
    return [low, high]


def parse_version(val) -> str:
    """Parse version from integer or string."""
    if isinstance(val, int):
        major = (val >> 8) & 0xFF
        minor = val & 0xFF
        return f"{major}.{minor:02d}"
    return "?"


# This function checks if the device time is out of sync with the Home Assistant time
# It compares the device time with the current time in UTC and returns True if the difference is greater than the threshold
def is_device_time_out_of_sync(data, hass=None, threshold_seconds=60) -> bool:
    """
    Returns True if device time and HA time differ by more than threshold_seconds.
    """
    device_dt = get_device_time(data, hass)
    if device_dt is None:
        return False
    now_dt = dt_util.utcnow().replace(tzinfo=datetime.timezone.utc)
    diff = abs((device_dt - now_dt).total_seconds())
    return diff > threshold_seconds


def calculate_next_interval_time(seconds, hass=None) -> datetime.datetime | None:
    """
    Calculate the timestamp for the next interval start.

    Args:
        seconds: Number of seconds until the next interval starts (countdown).
        hass: Home Assistant instance for timezone info (optional).

    Returns:
        datetime object representing when the next interval will start,
        or None if seconds is None, not a number, or <= 0.
        Time is rounded to the nearest minute (no seconds).
    """
    if seconds is None or not isinstance(seconds, (int, float)) or seconds <= 0:
        return None

    if hass:
        # Get current time in HA's local timezone
        ha_tz = dt_util.get_time_zone(hass.config.time_zone)
        now_local = datetime.datetime.now(ha_tz)
        # Add seconds using timedelta
        target_time = now_local + datetime.timedelta(seconds=seconds)
    else:
        # Fallback to UTC if hass is not available
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        target_time = now_utc + datetime.timedelta(seconds=seconds)

    # Round to nearest minute (set seconds and microseconds to 0)
    return target_time.replace(second=0, microsecond=0)


def modbus_regs_to_ascii(regs) -> str:
    """Convert list of uint16 Modbus registers to ASCII string (ASCIIZ, max 10 chars)."""
    chars = []
    for reg in regs:
        # High byte (1st char)
        high = (reg >> 8) & 0xFF
        # Low byte (2nd char)
        low = reg & 0xFF
        if high != 0:
            chars.append(chr(high))
        else:  # pragma: no cover
            break
        if low != 0:
            chars.append(chr(low))
        else:
            break
    return "".join(chars)


def modbus_regs_to_hex_string(regs) -> str:
    """Return Modbus registers as hex string."""
    if not regs or not isinstance(regs, list):
        return ""
    return "".join(f"{reg:04X}" for reg in regs)


def parse_timer_block(regs) -> dict:
    """Convert 15 Modbus registers to dict of timer params."""
    # Pads the regs list to length 15 with zeros if needed
    padded = pad_list(regs, 15)

    def u32(lsb, msb):
        return (msb << 16) | lsb

    return {
        "enable": padded[0],
        "on": u32(padded[1], padded[2]),
        "off": u32(padded[3], padded[4]),
        "period": u32(padded[5], padded[6]),
        "interval": u32(padded[7], padded[8]),
        "countdown": u32(padded[9], padded[10]),
        "function": padded[11],
        "work_time": u32(padded[13], padded[14]),
    }


def build_timer_block(data) -> list[int]:
    """Convert dict of timer params to 15 Modbus registers (all as int, never None)."""

    def safe_int(val):
        try:
            return int(val)
        except Exception:  # pragma: no cover
            return 0

    def split_u32(val):
        v = safe_int(val)
        return [v & 0xFFFF, (v >> 16) & 0xFFFF]

    regs = [
        safe_int(data.get("enable", 0)),
        *split_u32(data.get("on", 0)),
        *split_u32(data.get("off", 0)),
        *split_u32(data.get("period", 0)),
        *split_u32(data.get("interval", 0)),
        *split_u32(data.get("countdown", 0)),
        safe_int(data.get("function", 0)),
        0,
        *split_u32(data.get("work_time", 0)),
    ]
    return regs


def hhmm_to_seconds(hhmm) -> int:
    """Convert HH:MM string to seconds since midnight."""
    h, m = map(int, hhmm.split(":"))
    return h * 3600 + m * 60


def seconds_to_hhmm(seconds) -> str:
    """Convert seconds since midnight to HH:MM string."""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h:02d}:{m:02d}"


def get_timer_interval(start_sec, stop_sec) -> int:
    """Calculate interval in seconds, handle over-midnight."""
    if stop_sec >= start_sec:
        return stop_sec - start_sec
    else:
        # over-midnight
        return (86400 - start_sec) + stop_sec


def generate_time_options(step_minutes=15) -> list[str]:
    """Generate a list of HH:MM strings for every step_minutes in a day."""
    options = []
    for mins in range(0, 24 * 60, step_minutes):
        h = mins // 60
        m = mins % 60
        options.append(f"{h:02d}:{m:02d}")
    return options


def get_filtration_speed(data) -> int:
    """Get filtration speed based on relay state and configuration."""
    relay_state = data.get("MBF_RELAY_STATE", 0)
    # Use the dynamically decoded "Filtration Pump" key (set via GPIO mapping).
    # Only report a speed when the pump is explicitly on; treat both False
    # (pump off) and None (key not yet decoded / GPIO not assigned) as off.
    if data.get("Filtration Pump") is not True:
        return 0  # Filtration is off or unknown

    par_filtration_conf = data.get("MBF_PAR_FILTRATION_CONF", 0)
    relay_speed = (relay_state & 0x0700) >> 8
    if relay_speed == 1:
        return 1  # Low
    elif relay_speed == 2:
        return 2  # Mid
    elif relay_speed == 4:
        return 3  # High

    conf_speed = (par_filtration_conf & 0x0070) >> 4
    if conf_speed == 0:
        return 1
    elif conf_speed == 1:
        return 2
    elif conf_speed == 2:
        return 3
    return 0


def get_filtration_pump_type(par_filtration_conf) -> int:
    """Return the type of filtration pump based on configuration."""
    pump_type = (par_filtration_conf & 0x000F) >> 0
    return pump_type  # 0 = standard, 1/2 = variable speed


def pad_list(regs, length, pad_value=0) -> list[int]:
    """Return a list padded with pad_value to desired length."""
    return regs + [pad_value] * (length - len(regs))


# Machine type index → brand name (matches kNeoPoolMachineNames[] in Tasmota)
_MACHINE_NAMES = [
    "None",  # 0  MBV_PAR_MACH_NONE
    "Hidrolife",  # 1  MBV_PAR_MACH_HIDROLIFE
    "Aquascenic",  # 2  MBV_PAR_MACH_AQUASCENIC
    "Oxilife",  # 3  MBV_PAR_MACH_OXILIFE
    "Bionet",  # 4  MBV_PAR_MACH_BIONET
    "Hidroniser",  # 5  MBV_PAR_MACH_HIDRONISER
    "UVScenic",  # 6  MBV_PAR_MACH_UVSCENIC
    "Station",  # 7  MBV_PAR_MACH_STATION
    "Brilix",  # 8  MBV_PAR_MACH_BRILIX
    "Generic",  # 9  MBV_PAR_MACH_GENERIC
    "Bayrol",  # 10 MBV_PAR_MACH_BAYROL
    "Hay",  # 11 MBV_PAR_MACH_HAY
]
_MBV_PAR_MACH_GENERIC = 9


def get_machine_name(data: dict) -> str:
    """
    Return the human-readable machine/brand name.

    For GENERIC (9): assembles the custom name from the BOLD + LIGHT name registers
    stored in MBF_PAR_UICFG_MACH_NAME_BOLD / MBF_PAR_UICFG_MACH_NAME_LIGHT.
    If the custom name is empty, falls back to "Generic".
    """
    machine_type = int(data.get("MBF_PAR_UICFG_MACHINE") or 0)

    if machine_type == _MBV_PAR_MACH_GENERIC:
        bold = (data.get("MBF_PAR_UICFG_MACH_NAME_BOLD") or "").strip()
        light = (data.get("MBF_PAR_UICFG_MACH_NAME_LIGHT") or "").strip()
        custom_name = " ".join(filter(None, [bold, light]))
        if custom_name:
            return custom_name

    if 0 < machine_type < len(_MACHINE_NAMES):
        return _MACHINE_NAMES[machine_type]
    return ""  # 0 = no machine assigned, or unknown type


def is_hydrolysis_in_percent(data: dict) -> bool:
    """
    Determine if hydrolysis/electrolysis units are displayed as percentage or g/h.

    Based on Tasmota NeoPoolIsHydrolysisInPercent() logic:
    1. If MBMSK_VS_FORCE_UNITS_PERCENTAGE bit is set, "%" is displayed
    2. If MBMSK_VS_FORCE_UNITS_GRH bit is set, "g/h" is displayed
    3. If neither bit is set:
       a. If machine is HIDROLIFE or BIONET, then "g/h" is displayed
       b. If machine is GENERIC and MBMSK_ELECTROLISIS bit is set, "g/h" is displayed
       c. Otherwise "%" is displayed
    """
    # Bit masks for MBF_PAR_UICFG_MACH_VISUAL_STYLE register
    MBMSK_VS_FORCE_UNITS_GRH = 0x2000  # bit 13
    MBMSK_VS_FORCE_UNITS_PERCENTAGE = 0x4000  # bit 14
    MBMSK_ELECTROLISIS = 0x8000  # bit 15

    # Machine type values for MBF_PAR_UICFG_MACHINE register
    MBV_PAR_MACH_HIDROLIFE = 1
    MBV_PAR_MACH_BIONET = 4
    MBV_PAR_MACH_GENERIC = 9

    visual_style = int(data.get("MBF_PAR_UICFG_MACH_VISUAL_STYLE") or 0)
    machine_type = int(data.get("MBF_PAR_UICFG_MACHINE") or 0)

    # 1. If MBMSK_VS_FORCE_UNITS_PERCENTAGE bit is set, "%" is displayed
    if visual_style & MBMSK_VS_FORCE_UNITS_PERCENTAGE:
        return True

    # 2. If MBMSK_VS_FORCE_UNITS_GRH bit is set, "g/h" is displayed
    if visual_style & MBMSK_VS_FORCE_UNITS_GRH:
        return False

    # 3. If neither of the above bits is set:
    # a. If machine is HIDROLIFE or BIONET, then "g/h" is displayed
    if machine_type in (MBV_PAR_MACH_HIDROLIFE, MBV_PAR_MACH_BIONET):
        return False

    # b. If machine is GENERIC and MBMSK_ELECTROLISIS bit is set, "g/h" is displayed
    if machine_type == MBV_PAR_MACH_GENERIC and (visual_style & MBMSK_ELECTROLISIS):
        return False

    # c. Otherwise "%" is displayed
    return True


def has_filtvalve(data: dict) -> bool:
    """Return True if a Besgo automatic filter valve is configured.

    Primary signal is MBF_PAR_FILTVALVE_GPIO (relay assigned to the valve,
    valid range 1-7). MBF_PAR_FILTVALVE_ENABLE is honoured as a fallback
    for cases where GPIO is 0 but the feature flag is explicitly set.
    Values outside the valid relay range (1-7) are treated as not present.
    """
    from .const import is_valid_relay_gpio

    gpio = data.get("MBF_PAR_FILTVALVE_GPIO") or 0
    enable = data.get("MBF_PAR_FILTVALVE_ENABLE") or 0
    return is_valid_relay_gpio(gpio) or enable != 0


def parse_register_int(raw, name: str) -> int:
    """Parse an integer from decimal or hex string (e.g. '1539' or '0x0603')."""
    if isinstance(raw, bool):
        raise ServiceValidationError(
            f"Invalid {name} '{raw}': use a decimal number or hex (0x\u2026)"
        )
    if isinstance(raw, float):
        raise ServiceValidationError(
            f"Invalid {name} '{raw}': use an integer, not a float"
        )
    try:
        val = int(raw, 0) if isinstance(raw, str) else int(raw)
    except (ValueError, TypeError):
        raise ServiceValidationError(
            f"Invalid {name} '{raw}': use a decimal number or hex (0x\u2026)"
        )
    if not 0 <= val <= 65535:
        raise ServiceValidationError(f"{name} {val} out of range (0\u201365535)")
    return val


async def async_get_device_serial(config: dict, timeout: float = 5.0) -> str | None:
    """Perform minimal Modbus read to get device serial number.

    Reads only MBF_POWER_MODULE_NODEID (registers 0x0004–0x0009, 6 regs)
    instead of a full register dump.

    Args:
        config: Configuration dict with host, port, slave_id, modbus_framer.
        timeout: Timeout in seconds for the Modbus read operation.

    Returns:
        Hex string from 6 registers (24 chars, e.g. "0000000100AC00CD00120034"),
        or None on failure.
    """
    import asyncio

    from homeassistant.const import CONF_HOST, CONF_PORT
    from pymodbus.client import AsyncModbusTcpClient
    from pymodbus.framer import FramerType

    from .modbus_compat import modbus_acall

    host = config.get(CONF_HOST, "")
    port = config.get(CONF_PORT, 502)
    slave_id = config.get("slave_id", 1)
    framer_str = config.get("modbus_framer", "tcp").strip().lower()
    framer = FramerType.RTU if framer_str == "rtu" else FramerType.SOCKET

    client = AsyncModbusTcpClient(host, port=port, timeout=timeout, framer=framer)
    try:
        connected = await asyncio.wait_for(client.connect(), timeout=timeout)
        if not connected:
            _LOGGER.warning("Trial Modbus connect returned False for %s:%s", host, port)
            return None
        rr = await asyncio.wait_for(
            modbus_acall(
                client.read_holding_registers,
                slave_id,
                address=0x0004,
                count=6,
            ),
            timeout=timeout,
        )
        if not rr.isError():
            serial = modbus_regs_to_hex_string(list(rr.registers))
            if serial:
                _LOGGER.debug("Trial Modbus read successful, serial: %s", serial)
                return serial
    except asyncio.TimeoutError:
        _LOGGER.warning(
            "Trial Modbus read timed out for %s:%s",
            host,
            port,
        )
    except Exception as err:
        _LOGGER.warning("Trial Modbus read failed: %s", err)
    finally:
        try:
            result: object = client.close()
            if asyncio.iscoroutine(result):
                await result
        except Exception:  # noqa: BLE001
            pass

    return None
