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

import datetime

import pytest

from custom_components.neopool.helpers import (
    build_timer_block,
    generate_time_options,
    get_device_time,
    get_filtration_pump_type,
    get_filtration_speed,
    get_machine_name,
    get_timer_interval,
    hhmm_to_seconds,
    is_device_time_out_of_sync,
    is_hydrolysis_in_percent,
    modbus_regs_to_ascii,
    modbus_regs_to_hex_string,
    pad_list,
    parse_timer_block,
    parse_version,
    prepare_device_time,
    seconds_to_hhmm,
)


def test_parse_version():
    assert parse_version(0x0123) == "1.35"
    assert parse_version("invalid") == "?"


def test_pad_list():
    assert pad_list([1, 2], 5) == [1, 2, 0, 0, 0]
    assert pad_list([], 3, pad_value=7) == [7, 7, 7]


def test_modbus_regs_to_ascii():
    assert modbus_regs_to_ascii([0x4142, 0x4300]) == "ABC"
    assert modbus_regs_to_ascii([0x4100]) == "A"


def test_build_timer_block():
    d = {"enable": 1, "on": 60, "off": 120, "function": 3, "work_time": 30}
    regs = build_timer_block(d)
    assert isinstance(regs, list) and len(regs) == 15


def test_get_filtration_speed_mid():
    d = {
        "MBF_RELAY_STATE": 0x0202,
        "MBF_PAR_FILTRATION_CONF": 0x0000,
        "Filtration Pump": True,
    }
    # relay_speed == 2 → Mid
    assert get_filtration_speed(d) == 2


def test_get_filtration_speed_high():
    d = {
        "MBF_RELAY_STATE": 0x0402,
        "MBF_PAR_FILTRATION_CONF": 0x0000,
        "Filtration Pump": True,
    }
    # relay_speed == 4 → High
    assert get_filtration_speed(d) == 3


def test_get_filtration_speed_conf_speed_0():
    d = {
        "MBF_RELAY_STATE": 0x0002,
        "MBF_PAR_FILTRATION_CONF": 0x0000,
        "Filtration Pump": True,
    }
    assert get_filtration_speed(d) == 1


def test_get_filtration_speed_conf_speed_1():
    d = {
        "MBF_RELAY_STATE": 0x0002,
        "MBF_PAR_FILTRATION_CONF": 0x0010,
        "Filtration Pump": True,
    }
    assert get_filtration_speed(d) == 2


def test_get_filtration_speed_conf_speed_2():
    d = {
        "MBF_RELAY_STATE": 0x0002,
        "MBF_PAR_FILTRATION_CONF": 0x0020,
        "Filtration Pump": True,
    }
    assert get_filtration_speed(d) == 3


def test_get_filtration_speed_relay_speed_1():
    d = {
        "MBF_RELAY_STATE": 0x0102,
        "MBF_PAR_FILTRATION_CONF": 0x0000,
        "Filtration Pump": True,
    }
    # relay_speed == 1, should return 1 (Low)
    assert get_filtration_speed(d) == 1


@pytest.mark.parametrize(
    ("relay_state", "expected"),
    [
        (0x0302, 2),  # cumulative mid: bits 8+9 → relay_speed 0x03
        (0x0702, 3),  # cumulative high: bits 8+9+10 → relay_speed 0x07
    ],
    ids=["cumulative-mid", "cumulative-high"],
)
def test_get_filtration_speed_cumulative_encoding(relay_state, expected):
    """Controllers using cumulative (thermometer) speed bits (#152)."""
    d = {
        "MBF_RELAY_STATE": relay_state,
        "MBF_PAR_FILTRATION_CONF": 0x0020,  # conf says high – must be ignored
        "Filtration Pump": True,
    }
    assert get_filtration_speed(d) == expected


@pytest.mark.parametrize("aux_bit", [0x0010, 0x0020, 0x0040])
def test_get_filtration_speed_aux_bits_do_not_affect_speed(aux_bit):
    # filtration ON (0x0002), speed MID (0x0200), plus AUX relay bit set
    d = {
        "MBF_RELAY_STATE": 0x0202 | aux_bit,
        "MBF_PAR_FILTRATION_CONF": 0x0000,
        "Filtration Pump": True,
    }
    assert get_filtration_speed(d) == 2


def test_get_filtration_speed_no_match():
    d = {
        "MBF_RELAY_STATE": 0x0002,
        "MBF_PAR_FILTRATION_CONF": 0x00F0,
        "Filtration Pump": True,
    }
    # relay_speed == 0, conf_speed == 15 (not 0,1,2) → default 0
    assert get_filtration_speed(d) == 0


def test_get_filtration_speed_none():
    # Empty dict: "Filtration Pump" is None (not yet decoded) → treated as off.
    assert get_filtration_speed({}) == 0


def test_get_filtration_speed_pump_off():
    # "Filtration Pump" explicitly False → 0 (off)
    assert get_filtration_speed({"Filtration Pump": False}) == 0


def test_get_filtration_pump_type():
    assert get_filtration_pump_type(0x0001) == 1


def test_hhmm_seconds_conversion():
    assert hhmm_to_seconds("01:30") == 5400
    assert seconds_to_hhmm(5400) == "01:30"


def test_prepare_device_time_tz():
    class DummyHass:
        class Config:
            time_zone = "Europe/Prague"

        config = Config()

    hass = DummyHass()
    result = prepare_device_time(hass)
    # Result can be either a single integer or a list of two integers
    assert isinstance(result, (int, list))
    if isinstance(result, list):
        assert len(result) == 2
        assert all(isinstance(x, int) for x in result)
    else:
        assert 0 <= result < 2400  # HHMM


def test_parse_version_invalid():
    assert parse_version(None) == "?"
    assert parse_version("not-a-number") == "?"
    assert parse_version(0xFFFF) == "255.255"


def test_parse_version_with_zero():
    assert parse_version(0x0000) == "0.00"


def test_modbus_regs_to_ascii_empty():
    assert modbus_regs_to_ascii([]) == ""


def test_build_timer_block_with_missing_keys():
    # Missing work_time, function, etc.
    data = {"enable": 1, "on": 0, "off": 0}
    regs = build_timer_block(data)
    assert len(regs) == 15


def test_get_device_time_utc():
    """Test get_device_time returns correct UTC datetime."""
    # Example: 0x0001_0002 → timestamp = (high << 16) | low
    data = {"MBF_PAR_TIME_LOW": 0x5678, "MBF_PAR_TIME_HIGH": 0x1234}
    ts = (0x1234 << 16) | 0x5678
    expected = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
    dt = get_device_time(data)
    assert dt == expected


def test_get_device_time_missing_keys():
    """Test get_device_time returns None if missing data."""
    assert get_device_time({}) is None
    assert get_device_time({"MBF_PAR_TIME_LOW": 1}) is None
    assert get_device_time({"MBF_PAR_TIME_HIGH": 1}) is None


def test_get_device_time_epoch_zero():
    """Test get_device_time returns 1970-01-01T00:00:00Z for zero."""
    data = {"MBF_PAR_TIME_LOW": 0, "MBF_PAR_TIME_HIGH": 0}
    dt = get_device_time(data)
    assert dt == datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)


def test_get_device_time_with_hass(monkeypatch):
    """Test get_device_time returns UTC even with hass object."""

    # Prepare a dummy hass with config.time_zone
    class DummyConfig:
        time_zone = "Europe/Prague"

    class DummyHass:
        config = DummyConfig()

    # Patch dt_util.get_time_zone to always return UTC for test simplicity
    import homeassistant.util.dt as dt_util

    monkeypatch.setattr(dt_util, "get_time_zone", lambda tz: datetime.timezone.utc)

    ts = 1234567890
    data = {"MBF_PAR_TIME_LOW": ts & 0xFFFF, "MBF_PAR_TIME_HIGH": (ts >> 16) & 0xFFFF}
    dt = get_device_time(data, DummyHass())
    expected = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
    assert dt == expected


def test_generate_time_options_default():
    """Test generate_time_options produces every 15 min option in a day."""
    opts = generate_time_options()
    assert len(opts) == 96  # 24h * 4 per hour
    assert opts[0] == "00:00"
    assert opts[-1] == "23:45"


def test_generate_time_options_step_30():
    """Test generate_time_options with 30-minute steps."""
    opts = generate_time_options(step_minutes=30)
    assert len(opts) == 48
    assert opts[0] == "00:00"
    assert opts[1] == "00:30"
    assert opts[-1] == "23:30"


def test_parse_timer_block_full():
    """Test parse_timer_block with a full list of 15 registers."""
    regs = list(range(1, 16))
    result = parse_timer_block(regs)
    assert isinstance(result, dict)
    assert set(result.keys()) == {
        "enable",
        "on",
        "off",
        "period",
        "interval",
        "countdown",
        "function",
        "work_time",
    }
    # Example: on = u32(regs[1], regs[2]) == (regs[2] << 16) | regs[1]
    assert result["enable"] == 1
    assert result["on"] == (3 << 16) | 2


def test_parse_timer_block_short():
    """Test parse_timer_block pads missing registers with zeros."""
    regs = [1, 2, 3]  # Only first three
    result = parse_timer_block(regs)
    assert result["enable"] == 1
    assert result["on"] == (3 << 16) | 2  # padded msb=3
    assert result["off"] == 0
    assert len(result) == 8


def test_modbus_regs_to_hex_string_basic():
    """Test modbus_regs_to_hex_string converts list to hex string."""
    regs = [0x1234, 0xABCD, 0x0001]
    hexstr = modbus_regs_to_hex_string(regs)
    assert hexstr == "1234ABCD0001"


def test_modbus_regs_to_hex_string_empty():
    """Test modbus_regs_to_hex_string handles empty and invalid input."""
    assert modbus_regs_to_hex_string([]) == ""
    assert modbus_regs_to_hex_string(None) == ""
    assert modbus_regs_to_hex_string("notalist") == ""


def test_is_device_time_out_of_sync_false(monkeypatch):
    """Test is_device_time_out_of_sync returns False for small delta."""
    now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    data = {
        "MBF_PAR_TIME_LOW": now & 0xFFFF,
        "MBF_PAR_TIME_HIGH": (now >> 16) & 0xFFFF,
    }
    monkeypatch.setattr(
        "homeassistant.util.dt.utcnow",
        lambda: datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc),
    )
    assert is_device_time_out_of_sync(data, None, threshold_seconds=60) is False


def test_is_device_time_out_of_sync_true(monkeypatch):
    """Test is_device_time_out_of_sync returns True for large delta."""
    # Device time 2 hours behind
    now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    device_time = now - 7200  # 2 hours ago
    data = {
        "MBF_PAR_TIME_LOW": device_time & 0xFFFF,
        "MBF_PAR_TIME_HIGH": (device_time >> 16) & 0xFFFF,
    }
    monkeypatch.setattr(
        "homeassistant.util.dt.utcnow",
        lambda: datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc),
    )
    assert is_device_time_out_of_sync(data, None, threshold_seconds=60) is True


def test_is_device_time_out_of_sync_none():
    """Test is_device_time_out_of_sync returns False if no device time."""
    assert is_device_time_out_of_sync({}, None, threshold_seconds=60) is False


def test_get_timer_interval_daytime():
    """Test get_timer_interval with stop >= start."""
    assert get_timer_interval(3600, 7200) == 3600  # 01:00 - 02:00


def test_get_timer_interval_overnight():
    """Test get_timer_interval with stop < start (over midnight)."""
    assert get_timer_interval(82800, 3600) == 3600 + (
        86400 - 82800
    )  # 23:00 - 01:00 = 2h


def test_get_timer_interval_zero():
    """Test get_timer_interval returns 0 if times are equal."""
    assert get_timer_interval(5000, 5000) == 0


def test_calculate_next_interval_time_with_hass():
    """Test calculate_next_interval_time with hass instance."""
    from datetime import datetime, timedelta
    from unittest.mock import MagicMock
    from zoneinfo import ZoneInfo

    from custom_components.neopool.helpers import calculate_next_interval_time

    # Mock hass with Prague timezone
    mock_hass = MagicMock()
    mock_hass.config.time_zone = "Europe/Prague"

    # Calculate with 3600 seconds (1 hour)
    result = calculate_next_interval_time(3600, mock_hass)

    # Should be a datetime object
    assert isinstance(result, datetime)

    # Should have timezone information
    assert result.tzinfo is not None

    # Should have seconds set to 0 (rounded to nearest minute)
    assert result.second == 0
    assert result.microsecond == 0

    # Should be approximately 1 hour from now (allow 1 minute tolerance)
    prague_tz = ZoneInfo("Europe/Prague")
    expected_time = (datetime.now(prague_tz) + timedelta(seconds=3600)).replace(
        second=0, microsecond=0
    )
    time_diff = abs((result - expected_time).total_seconds())
    assert time_diff < 60, f"Time difference {time_diff} seconds is too large"


def test_calculate_next_interval_time_without_hass():
    """Test calculate_next_interval_time without hass (UTC fallback)."""
    from datetime import datetime, timedelta, timezone

    from custom_components.neopool.helpers import calculate_next_interval_time

    # Calculate with 7200 seconds (2 hours), no hass
    result = calculate_next_interval_time(7200, None)

    # Should be a datetime object
    assert isinstance(result, datetime)

    # Should have timezone information (UTC)
    assert result.tzinfo is not None
    assert result.tzinfo == timezone.utc

    # Should have seconds set to 0 (rounded to nearest minute)
    assert result.second == 0
    assert result.microsecond == 0

    # Should be approximately 2 hours from now in UTC (allow 1 minute tolerance)
    expected_time = (datetime.now(timezone.utc) + timedelta(seconds=7200)).replace(
        second=0, microsecond=0
    )
    time_diff = abs((result - expected_time).total_seconds())
    assert time_diff < 60, f"Time difference {time_diff} seconds is too large"


def test_calculate_next_interval_time_zero_value():
    """Test calculate_next_interval_time returns None for zero value."""
    from custom_components.neopool.helpers import calculate_next_interval_time

    result = calculate_next_interval_time(0, None)
    assert result is None


def test_calculate_next_interval_time_negative_value():
    """Test calculate_next_interval_time returns None for negative value."""
    from custom_components.neopool.helpers import calculate_next_interval_time

    result = calculate_next_interval_time(-100, None)
    assert result is None


def test_calculate_next_interval_time_none_value():
    """Test calculate_next_interval_time returns None for None value."""
    from custom_components.neopool.helpers import calculate_next_interval_time

    result = calculate_next_interval_time(None, None)
    assert result is None


def test_calculate_next_interval_time_invalid_type():
    """Test calculate_next_interval_time returns None for invalid type."""
    from custom_components.neopool.helpers import calculate_next_interval_time

    result = calculate_next_interval_time("not a number", None)
    assert result is None


def test_is_hydrolysis_in_percent_force_percentage_bit():
    """Test is_hydrolysis_in_percent when MBMSK_VS_FORCE_UNITS_PERCENTAGE bit is set."""
    data = {
        "MBF_PAR_UICFG_MACH_VISUAL_STYLE": 0x4000,  # bit 14 set
        "MBF_PAR_UICFG_MACHINE": 0,
    }
    assert is_hydrolysis_in_percent(data) is True


def test_is_hydrolysis_in_percent_force_grh_bit():
    """Test is_hydrolysis_in_percent when MBMSK_VS_FORCE_UNITS_GRH bit is set."""
    data = {
        "MBF_PAR_UICFG_MACH_VISUAL_STYLE": 0x2000,  # bit 13 set
        "MBF_PAR_UICFG_MACHINE": 0,
    }
    assert is_hydrolysis_in_percent(data) is False


def test_is_hydrolysis_in_percent_both_force_bits():
    """Test is_hydrolysis_in_percent when both force bits are set (percentage takes precedence)."""
    data = {
        "MBF_PAR_UICFG_MACH_VISUAL_STYLE": 0x6000,  # both bits 13 and 14 set
        "MBF_PAR_UICFG_MACHINE": 0,
    }
    assert is_hydrolysis_in_percent(data) is True


def test_is_hydrolysis_in_percent_hidrolife():
    """Test is_hydrolysis_in_percent for HIDROLIFE machine type."""
    data = {
        "MBF_PAR_UICFG_MACH_VISUAL_STYLE": 0x0000,  # no force bits
        "MBF_PAR_UICFG_MACHINE": 1,  # HIDROLIFE
    }
    assert is_hydrolysis_in_percent(data) is False


def test_is_hydrolysis_in_percent_bionet():
    """Test is_hydrolysis_in_percent for BIONET machine type."""
    data = {
        "MBF_PAR_UICFG_MACH_VISUAL_STYLE": 0x0000,  # no force bits
        "MBF_PAR_UICFG_MACHINE": 4,  # BIONET
    }
    assert is_hydrolysis_in_percent(data) is False


def test_is_hydrolysis_in_percent_generic_with_electrolisis():
    """Test is_hydrolysis_in_percent for GENERIC machine with ELECTROLISIS bit."""
    data = {
        "MBF_PAR_UICFG_MACH_VISUAL_STYLE": 0x8000,  # bit 15 (ELECTROLISIS) set
        "MBF_PAR_UICFG_MACHINE": 9,  # GENERIC
    }
    assert is_hydrolysis_in_percent(data) is False


def test_is_hydrolysis_in_percent_generic_without_electrolisis():
    """Test is_hydrolysis_in_percent for GENERIC machine without ELECTROLISIS bit."""
    data = {
        "MBF_PAR_UICFG_MACH_VISUAL_STYLE": 0x0000,  # no special bits
        "MBF_PAR_UICFG_MACHINE": 9,  # GENERIC
    }
    assert is_hydrolysis_in_percent(data) is True


def test_is_hydrolysis_in_percent_default_case():
    """Test is_hydrolysis_in_percent default case (returns True for other machine types)."""
    data = {
        "MBF_PAR_UICFG_MACH_VISUAL_STYLE": 0x0000,
        "MBF_PAR_UICFG_MACHINE": 2,  # AQUASCENIC
    }
    assert is_hydrolysis_in_percent(data) is True


def test_is_hydrolysis_in_percent_empty_data():
    """Test is_hydrolysis_in_percent with empty data (defaults to True)."""
    data = {}
    assert is_hydrolysis_in_percent(data) is True


def test_is_hydrolysis_in_percent_missing_visual_style():
    """Test is_hydrolysis_in_percent with missing visual style (defaults based on machine)."""
    data = {
        "MBF_PAR_UICFG_MACHINE": 1,  # HIDROLIFE
    }
    assert is_hydrolysis_in_percent(data) is False


def test_is_hydrolysis_in_percent_none_values():
    """Test is_hydrolysis_in_percent when Modbus populates keys with None (get_safe IndexError)."""
    # Both keys present but explicitly None — must not raise TypeError
    data = {
        "MBF_PAR_UICFG_MACH_VISUAL_STYLE": None,
        "MBF_PAR_UICFG_MACHINE": None,
    }
    assert is_hydrolysis_in_percent(data) is True  # falls through to default True

    # Only visual_style is None, machine is HIDROLIFE → g/h
    data = {
        "MBF_PAR_UICFG_MACH_VISUAL_STYLE": None,
        "MBF_PAR_UICFG_MACHINE": 1,  # HIDROLIFE
    }
    assert is_hydrolysis_in_percent(data) is False


# ---------------------------------------------------------------------------
# get_machine_name tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "machine_type, expected",
    [
        (0, ""),  # MBV_PAR_MACH_NONE → no machine assigned
        (1, "Hidrolife"),
        (2, "Aquascenic"),
        (3, "Oxilife"),
        (4, "Bionet"),
        (5, "Hidroniser"),
        (6, "UVScenic"),
        (7, "Station"),
        (8, "Brilix"),
        (9, "Generic"),  # GENERIC but no custom name → fallback
        (10, "Bayrol"),
        (11, "Hay"),
    ],
)
def test_get_machine_name_known_types(machine_type, expected):
    """All 12 known machine types return their brand name."""
    data = {"MBF_PAR_UICFG_MACHINE": machine_type}
    assert get_machine_name(data) == expected


def test_get_machine_name_unknown_type():
    """Out-of-range value returns empty string."""
    assert get_machine_name({"MBF_PAR_UICFG_MACHINE": 99}) == ""
    assert get_machine_name({"MBF_PAR_UICFG_MACHINE": 12}) == ""


def test_get_machine_name_empty_data():
    """Missing key defaults to 0 → empty string (no machine assigned)."""
    assert get_machine_name({}) == ""


def test_get_machine_name_none_value():
    """Explicit None value defaults to 0 → empty string (no machine assigned)."""
    assert get_machine_name({"MBF_PAR_UICFG_MACHINE": None}) == ""


def test_get_machine_name_generic_with_custom_name():
    """GENERIC (9) with both name parts returns 'bold light'."""
    data = {
        "MBF_PAR_UICFG_MACHINE": 9,
        "MBF_PAR_UICFG_MACH_NAME_BOLD": "vista",
        "MBF_PAR_UICFG_MACH_NAME_LIGHT": "pool",
    }
    assert get_machine_name(data) == "vista pool"


def test_get_machine_name_generic_bold_only():
    """GENERIC with only bold part returns just that string."""
    data = {
        "MBF_PAR_UICFG_MACHINE": 9,
        "MBF_PAR_UICFG_MACH_NAME_BOLD": "aqua",
        "MBF_PAR_UICFG_MACH_NAME_LIGHT": "",
    }
    assert get_machine_name(data) == "aqua"


def test_get_machine_name_generic_light_only():
    """GENERIC with only light part returns just that string."""
    data = {
        "MBF_PAR_UICFG_MACHINE": 9,
        "MBF_PAR_UICFG_MACH_NAME_BOLD": None,
        "MBF_PAR_UICFG_MACH_NAME_LIGHT": "scenic",
    }
    assert get_machine_name(data) == "scenic"


def test_get_machine_name_generic_empty_custom_name():
    """GENERIC with both name parts empty/None falls back to 'Generic'."""
    data = {
        "MBF_PAR_UICFG_MACHINE": 9,
        "MBF_PAR_UICFG_MACH_NAME_BOLD": "",
        "MBF_PAR_UICFG_MACH_NAME_LIGHT": None,
    }
    assert get_machine_name(data) == "Generic"


def test_get_machine_name_generic_whitespace_name():
    """GENERIC with only whitespace in name parts falls back to 'Generic'."""
    data = {
        "MBF_PAR_UICFG_MACHINE": 9,
        "MBF_PAR_UICFG_MACH_NAME_BOLD": "   ",
        "MBF_PAR_UICFG_MACH_NAME_LIGHT": "   ",
    }
    assert get_machine_name(data) == "Generic"


def test_get_machine_name_non_generic_ignores_custom_name():
    """Non-GENERIC machine type ignores name registers."""
    data = {
        "MBF_PAR_UICFG_MACHINE": 11,  # Hay
        "MBF_PAR_UICFG_MACH_NAME_BOLD": "something",
        "MBF_PAR_UICFG_MACH_NAME_LIGHT": "else",
    }
    assert get_machine_name(data) == "Hay"


# ---------------------------------------------------------------------------
# has_filtvalve tests
# ---------------------------------------------------------------------------


def test_has_filtvalve_enable_only():
    from custom_components.neopool.helpers import has_filtvalve

    assert has_filtvalve({"MBF_PAR_FILTVALVE_ENABLE": 1}) is True


def test_has_filtvalve_gpio_only():
    from custom_components.neopool.helpers import has_filtvalve

    assert (
        has_filtvalve({"MBF_PAR_FILTVALVE_ENABLE": 0, "MBF_PAR_FILTVALVE_GPIO": 5})
        is True
    )


def test_has_filtvalve_both():
    from custom_components.neopool.helpers import has_filtvalve

    assert (
        has_filtvalve({"MBF_PAR_FILTVALVE_ENABLE": 1, "MBF_PAR_FILTVALVE_GPIO": 5})
        is True
    )


def test_has_filtvalve_neither():
    from custom_components.neopool.helpers import has_filtvalve

    assert (
        has_filtvalve({"MBF_PAR_FILTVALVE_ENABLE": 0, "MBF_PAR_FILTVALVE_GPIO": 0})
        is False
    )


def test_has_filtvalve_missing_keys():
    from custom_components.neopool.helpers import has_filtvalve

    assert has_filtvalve({}) is False


def test_has_filtvalve_gpio_out_of_range():
    from custom_components.neopool.helpers import has_filtvalve

    # GPIO=8 is outside the valid hardware range (1-7) and must not trigger detection
    assert (
        has_filtvalve({"MBF_PAR_FILTVALVE_ENABLE": 0, "MBF_PAR_FILTVALVE_GPIO": 8})
        is False
    )
