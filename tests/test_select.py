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

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from custom_components.neopool.const import SELECT_DEFINITIONS
from custom_components.neopool.select import (
    PERIOD_MAP,
    PERIOD_SECONDS_TO_KEY,
    NeoPoolEntity,
    NeoPoolSelect,
    async_setup_entry,
)


@pytest.fixture(autouse=True)
def _fast_sleep(monkeypatch):
    """Patch asyncio.sleep to a no-op for all tests in this module to speed them up."""
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())


@pytest.fixture
def mock_coordinator():
    mock = AsyncMock()
    mock.data = {}
    mock.device_slug = "neopool"
    mock.winter_mode = False
    mock.async_set_updated_data = MagicMock()
    mock.request_refresh_with_followup = MagicMock()
    config_entry = MagicMock()
    config_entry.entry_id = "test_entry"
    config_entry.unique_id = "test_slug"
    config_entry.options = {}
    mock.config_entry = config_entry
    mock.entry = config_entry
    return mock


def make_props(**kwargs):
    d = {}
    d.update(kwargs)
    return d


DELAY_OPTIONS_MAP = {
    10: "10",
    20: "20",
    30: "30",
    40: "40",
    50: "50",
    60: "60",
    120: "120",
    180: "180",
    300: "300",
    900: "900",
    1800: "1800",
    3600: "3600",
    10800: "10800",
}


@pytest.fixture
def boost_props():
    return {
        "options_map": {
            0: "inactive",
            1: "active (redox disabled)",
            2: "active (redox enabled)",
        },
    }


def test_options_basic_options_map(mock_coordinator):
    props = make_props(options_map={0: "auto", 1: "manual", 2: "off"})
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "MBF_PAR_FILT_MODE", props)
    mock_coordinator.data = {}
    opts = ent.options
    assert set(opts) <= {"auto", "manual", "off"}


def test_options_hide_heating_intelligent(mock_coordinator):
    props = make_props(
        options_map={0: "auto", 2: "heating", 3: "intelligent", 4: "off"}
    )
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "MBF_PAR_FILT_MODE", props)
    mock_coordinator.data = {"MBF_PAR_HEATING_MODE": 0, "MBF_PAR_TEMPERATURE_ACTIVE": 0}
    opts = ent.options
    assert "heating" not in opts and "intelligent" not in opts


def test_options_hide_smart_temp_sensor(mock_coordinator):
    props = make_props(options_map={0: "auto", 3: "smart", 4: "off"})
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "MBF_PAR_FILT_MODE", props)
    mock_coordinator.data = {"MBF_PAR_HEATING_MODE": 0, "MBF_PAR_TEMPERATURE_ACTIVE": 0}
    opts = ent.options
    assert "smart" not in opts


def test_options_add_backwash(mock_coordinator):
    props = make_props(options_map={0: "auto", 1: "manual", 2: "off", 13: "backwash"})
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "MBF_PAR_FILT_MODE", props)
    mock_coordinator.data = {}
    mock_coordinator.config_entry.options = {"enable_backwash_option": True}
    opts = ent.options
    assert "backwash" in opts


def test_options_add_backwash_via_filtvalve(mock_coordinator):
    """Backwash appears automatically when a Besgo valve is enabled.

    MBF_PAR_FILTVALVE_ENABLE=1 must add backwash to the options list even
    without enable_backwash_option set in config options.
    """
    props = make_props(options_map={0: "auto", 1: "manual", 2: "off", 13: "backwash"})
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "MBF_PAR_FILT_MODE", props)
    mock_coordinator.data = {"MBF_PAR_FILTVALVE_ENABLE": 1}
    mock_coordinator.config_entry.options = {}
    opts = ent.options
    assert "backwash" in opts


def test_options_no_backwash_without_valve_or_option(mock_coordinator):
    """Backwash must be hidden when neither enable_backwash_option nor Besgo valve."""
    props = make_props(options_map={0: "auto", 1: "manual", 2: "off", 13: "backwash"})
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "MBF_PAR_FILT_MODE", props)
    mock_coordinator.data = {"MBF_PAR_FILTVALVE_ENABLE": 0, "MBF_PAR_FILTVALVE_GPIO": 0}
    mock_coordinator.config_entry.options = {}
    opts = ent.options
    assert "backwash" not in opts


def test_options_add_backwash_via_gpio_only(mock_coordinator):
    """Backwash must appear when MBF_PAR_FILTVALVE_GPIO!=0 even with ENABLE=0."""
    props = make_props(options_map={0: "auto", 1: "manual", 2: "off", 13: "backwash"})
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "MBF_PAR_FILT_MODE", props)
    mock_coordinator.data = {"MBF_PAR_FILTVALVE_ENABLE": 0, "MBF_PAR_FILTVALVE_GPIO": 5}
    mock_coordinator.config_entry.options = {}
    opts = ent.options
    assert "backwash" in opts


def test_options_backwash_kept_when_active(mock_coordinator):
    """Backwash stays in options if the device is currently in mode 13.

    Even when backwash is not normally allowed, keeping it in options lets
    current_option remain valid for the active mode.
    """
    props = make_props(options_map={0: "auto", 1: "manual", 2: "off", 13: "backwash"})
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "MBF_PAR_FILT_MODE", props)
    mock_coordinator.data = {
        "MBF_PAR_FILTVALVE_ENABLE": 0,
        "MBF_PAR_FILTVALVE_GPIO": 0,
        "MBF_PAR_FILT_MODE": 13,
    }
    mock_coordinator.config_entry.options = {}
    opts = ent.options
    assert "backwash" in opts


def test_options_timer_time(mock_coordinator):
    props = make_props(select_type="timer_time")
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "relay_aux1_start", props)
    mock_coordinator.data = {"relay_aux1_start": 0}
    mock_coordinator.config_entry.options = {"timer_resolution": 5}
    opts = ent.options
    assert all(isinstance(x, str) for x in opts)


def test_options_timer_period(mock_coordinator):
    props = make_props(select_type="timer_period")
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "relay_aux1_period", props)
    mock_coordinator.data = {"relay_aux1_period": 600}
    opts = ent.options
    assert any(isinstance(x, str) for x in opts)


def test_options_relay_mode_disabled(mock_coordinator):
    props = make_props(select_type="relay_mode", options_map={1: "auto"})
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "relay_aux1_enable", props)
    mock_coordinator.data = {"relay_aux1_enable": 0}
    opts = ent.options
    assert "disabled" in opts


def test_options_boost_hide_redox(mock_coordinator):
    props = make_props(
        options_map={
            0: "inactive",
            1: "active (redox disabled)",
            2: "active (redox enabled)",
        }
    )
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "MBF_CELL_BOOST", props)
    mock_coordinator.data = {"Redox measurement module detected": False}
    opts = ent.options
    assert "active (redox enabled)" not in opts


def test_current_option_cell_boost(mock_coordinator):
    props = make_props(
        options_map={
            0: "inactive",
            1: "active (redox disabled)",
            2: "active (redox enabled)",
        }
    )
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "MBF_CELL_BOOST", props)
    mock_coordinator.data = {"MBF_CELL_BOOST": 0x8000}
    assert ent.current_option == "active (redox disabled)"
    mock_coordinator.data["MBF_CELL_BOOST"] = 0x05A0
    assert ent.current_option == "active (redox enabled)"


def test_current_option_filtration_speed(mock_coordinator):
    props = {
        "options_map": {0: "low", 1: "mid", 2: "high"},
        "mask": 0x70,
        "shift": 4,
    }
    ent = NeoPoolSelect(
        mock_coordinator, "test_entry", "MBF_PAR_FILTRATION_SPEED", props
    )
    mock_coordinator.data = {"MBF_PAR_FILTRATION_CONF": 32}
    assert ent.current_option == "high"
    mock_coordinator.data = {"MBF_PAR_FILTRATION_CONF": 16}
    assert ent.current_option == "mid"
    mock_coordinator.data = {"MBF_PAR_FILTRATION_CONF": 0}
    assert ent.current_option == "low"


def test_current_option_timer_period(mock_coordinator):
    props = make_props(select_type="timer_period")
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "relay_aux1_period", props)
    value = list(PERIOD_MAP.values())[0]
    mock_coordinator.data = {"relay_aux1_period": value}
    assert ent.current_option == PERIOD_SECONDS_TO_KEY[value]


def test_current_option_relay_mode(mock_coordinator):
    props = make_props(select_type="relay_mode", options_map={1: "auto", 2: "manual"})
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "relay_aux1_enable", props)
    mock_coordinator.data = {"relay_aux1_enable": 0}
    assert ent.current_option == "disabled"
    mock_coordinator.data["relay_aux1_enable"] = 2
    assert ent.current_option == "auto_linked"


def test_current_option_default(mock_coordinator):
    props = make_props(options_map={0: "auto", 1: "manual", 2: "off"})
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "MBF_PAR_FILT_MODE", props)
    mock_coordinator.data = {"MBF_PAR_FILT_MODE": 1}
    assert ent.current_option == "manual"


def _intelligent_min_time_props():
    return {
        "select_type": "mapped_register",
        "fallback_suffix": "m",
        "options_map": {
            120: "2h",
            180: "3h",
            240: "4h",
            300: "5h",
            360: "6h",
            420: "7h",
            480: "8h",
            540: "9h",
            600: "10h",
            660: "11h",
            720: "12h",
        },
        "register": 0x041D,
    }


def test_options_intelligent_min_time_unknown_value(mock_coordinator):
    props = _intelligent_min_time_props()
    ent = NeoPoolSelect(
        mock_coordinator, "test_entry", "MBF_PAR_INTELLIGENT_FILT_MIN_TIME", props
    )
    # Known value → just labels, no numeric prefix
    mock_coordinator.data = {"MBF_PAR_INTELLIGENT_FILT_MIN_TIME": 360}
    opts = ent.options
    assert opts[0] == "2h" and "6h" in opts
    # Unknown value → prepend numeric string with 'm'
    mock_coordinator.data = {"MBF_PAR_INTELLIGENT_FILT_MIN_TIME": 365}
    opts = ent.options
    assert opts[0] == "365m"


def test_current_option_intelligent_min_time(mock_coordinator):
    props = _intelligent_min_time_props()
    ent = NeoPoolSelect(
        mock_coordinator, "test_entry", "MBF_PAR_INTELLIGENT_FILT_MIN_TIME", props
    )
    mock_coordinator.data = {"MBF_PAR_INTELLIGENT_FILT_MIN_TIME": 360}
    assert ent.current_option == "6h"
    mock_coordinator.data = {"MBF_PAR_INTELLIGENT_FILT_MIN_TIME": 365}
    assert ent.current_option == "365m"


@pytest.mark.asyncio
async def test_async_select_option_timer_time(mock_coordinator):
    props = make_props(select_type="timer_time")
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "relay_aux1_start", props)
    ent.hass = MagicMock()
    ent.hass.services.async_call = AsyncMock()
    mock_coordinator.data = {"relay_aux1_stop": 0}
    await ent.async_select_option("06:00")
    ent.hass.services.async_call.assert_awaited()


@pytest.mark.asyncio
async def test_async_select_option_timer_period(mock_coordinator):
    props = make_props(select_type="timer_period")
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "relay_aux1_period", props)
    ent.hass = MagicMock()
    ent.hass.services.async_call = AsyncMock()
    await ent.async_select_option("10")
    ent.hass.services.async_call.assert_awaited()


@pytest.mark.asyncio
async def test_async_select_option_relay_mode(mock_coordinator):
    props = make_props(select_type="relay_mode", options_map={0: "auto", 1: "manual"})
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "relay_aux1_enable", props)
    ent.hass = MagicMock()
    ent.hass.services.async_call = AsyncMock()
    await ent.async_select_option("manual")
    ent.hass.services.async_call.assert_awaited()
    mock_coordinator.async_set_updated_data.assert_called()


@pytest.mark.asyncio
async def test_async_select_option_backwash(mock_coordinator):
    # Use real SELECT_DEFINITIONS props — backwash (13) is NOT pre-populated in options_map.
    # It is injected dynamically by the options property when enable_backwash_option is True.
    props = SELECT_DEFINITIONS["MBF_PAR_FILT_MODE"]
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "MBF_PAR_FILT_MODE", props)
    ent.hass = MagicMock()
    ent.hass.services.async_call = AsyncMock()
    ent.coordinator.data = {
        "MBF_PAR_FILT_MODE": 1,  # current: auto (avoids manual→other double-write)
        "MBF_PAR_HEATING_GPIO": 0,
        "MBF_PAR_TEMPERATURE_ACTIVE": 0,
    }
    ent.coordinator.device_name = "neopool"
    ent.coordinator.entry.options = {"enable_backwash_option": True}
    ent.coordinator.client = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    # Verify the injection path works: options property must include "backwash"
    assert "backwash" in ent.options
    # Should write value 13 to the filtration mode register
    await ent.async_select_option("backwash")
    ent.coordinator.client.async_write_register.assert_awaited_once_with(0x0411, 13)


@pytest.mark.asyncio
async def test_async_select_option_backwash_from_manual(mock_coordinator):
    """Switching from manual to backwash with a MANUAL valve must stop the pump first.

    The user needs the pump stopped so they can safely rotate the multi-way valve.
    """
    props = SELECT_DEFINITIONS["MBF_PAR_FILT_MODE"]
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "MBF_PAR_FILT_MODE", props)
    ent.hass = MagicMock()
    ent.coordinator.data = {
        "MBF_PAR_FILT_MODE": 0,  # current: manual
        "MBF_PAR_HEATING_GPIO": 0,
        "MBF_PAR_TEMPERATURE_ACTIVE": 0,
        "MBF_PAR_FILTVALVE_ENABLE": 0,
        "MBF_PAR_FILTVALVE_GPIO": 0,  # no valve => manual
    }
    ent.coordinator.device_name = "neopool"
    ent.coordinator.entry.options = {"enable_backwash_option": True}
    ent.coordinator.client = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    assert "backwash" in ent.options
    await ent.async_select_option("backwash")
    calls = ent.coordinator.client.async_write_register.await_args_list
    # First call: stop manual filtration (safety - user must turn valve manually)
    assert calls[0].args == (0x0413, 0)
    # Second call: set backwash mode
    assert calls[1].args == (0x0411, 13)


@pytest.mark.asyncio
async def test_async_select_option_backwash_from_manual_auto_valve(mock_coordinator):
    """Switching from manual to backwash with an AUTOMATIC valve must keep the pump running.

    A Besgo automatic valve needs flow to open correctly, so the pump must
    keep running across the mode transition.
    """
    props = SELECT_DEFINITIONS["MBF_PAR_FILT_MODE"]
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "MBF_PAR_FILT_MODE", props)
    ent.hass = MagicMock()
    ent.coordinator.data = {
        "MBF_PAR_FILT_MODE": 0,  # current: manual
        "MBF_PAR_HEATING_GPIO": 0,
        "MBF_PAR_TEMPERATURE_ACTIVE": 0,
        "MBF_PAR_FILTVALVE_ENABLE": 1,  # Besgo auto valve present
        "MBF_PAR_FILTVALVE_GPIO": 5,
    }
    ent.coordinator.device_name = "neopool"
    ent.coordinator.entry.options = {"enable_backwash_option": True}
    ent.coordinator.client = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    assert "backwash" in ent.options
    await ent.async_select_option("backwash")
    calls = ent.coordinator.client.async_write_register.await_args_list
    # Only one write: set backwash mode - pump must NOT be stopped
    assert len(calls) == 1
    assert calls[0].args == (0x0411, 13)


@pytest.mark.asyncio
async def test_async_select_option_cell_boost(mock_coordinator):
    props = make_props(
        options_map={
            0: "inactive",
            1: "active (redox disabled)",
            2: "active (redox enabled)",
        }
    )
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "MBF_CELL_BOOST", props)
    ent.hass = MagicMock()
    ent.coordinator.client = AsyncMock()
    await ent.async_select_option("active (redox enabled)")
    ent.coordinator.client.async_write_register.assert_awaited()


@pytest.mark.asyncio
async def test_async_select_option_filtration_speed(mock_coordinator):
    props = {
        "options_map": {0: "low", 1: "mid", 2: "high"},
        "mask": 0x70,
        "shift": 4,
        "register": 0x050F,
    }
    ent = NeoPoolSelect(
        mock_coordinator, "test_entry", "MBF_PAR_FILTRATION_SPEED", props
    )
    ent.hass = MagicMock()
    ent.coordinator.client = AsyncMock()
    ent.coordinator.device_name = "neopool"
    # Start with current=0 (should be "low"). Set to "mid" (1).
    mock_coordinator.data = {"MBF_PAR_FILTRATION_CONF": 0}
    await ent.async_select_option("mid")
    ent.coordinator.client.async_write_register.assert_awaited_with(
        0x050F, 16, apply=True
    )
    # Now try "high"
    ent.coordinator.client.reset_mock()
    mock_coordinator.data = {"MBF_PAR_FILTRATION_CONF": 0}
    await ent.async_select_option("high")
    ent.coordinator.client.async_write_register.assert_awaited_with(
        0x050F, 32, apply=True
    )


@pytest.mark.asyncio
async def test_async_select_option_default(mock_coordinator):
    props = make_props(options_map={0: "auto", 1: "manual", 2: "off"}, register=0x0200)
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "MBF_PAR_FILT_MODE", props)
    ent.hass = MagicMock()
    ent.coordinator.client = AsyncMock()
    ent.coordinator.data = {"MBF_PAR_FILT_MODE": 1}
    ent.coordinator.async_request_refresh = AsyncMock()
    ent.async_write_ha_state = Mock()
    await ent.async_select_option("manual")
    ent.coordinator.client.async_write_register.assert_awaited()


@pytest.mark.asyncio
async def test_async_select_option_intelligent_min_time_label(mock_coordinator):
    props = _intelligent_min_time_props()
    ent = NeoPoolSelect(
        mock_coordinator, "test_entry", "MBF_PAR_INTELLIGENT_FILT_MIN_TIME", props
    )
    ent.hass = MagicMock()
    ent.coordinator.client = AsyncMock()
    ent.coordinator.async_request_refresh = AsyncMock()
    ent.async_write_ha_state = Mock()
    await ent.async_select_option("6h")
    ent.coordinator.client.async_write_register.assert_awaited_with(0x041D, 360)


@pytest.mark.asyncio
async def test_async_select_option_intelligent_min_time_numeric(mock_coordinator):
    props = _intelligent_min_time_props()
    ent = NeoPoolSelect(
        mock_coordinator, "test_entry", "MBF_PAR_INTELLIGENT_FILT_MIN_TIME", props
    )
    ent.hass = MagicMock()
    ent.coordinator.client = AsyncMock()
    ent.coordinator.async_request_refresh = AsyncMock()
    ent.async_write_ha_state = Mock()
    await ent.async_select_option("365m")
    ent.coordinator.client.async_write_register.assert_awaited_with(0x041D, 365)


def test_select_cell_boost_current_option(mock_coordinator, boost_props):
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "MBF_CELL_BOOST", boost_props)

    # case: Inactive
    mock_coordinator.data["MBF_CELL_BOOST"] = 0
    assert ent.current_option == "inactive"

    # case: Active (redox disabled)
    mock_coordinator.data["MBF_CELL_BOOST"] = 0x8000  # bit 0x8000 set
    assert ent.current_option == "active (redox disabled)"

    # case: Active (redox enabled)
    mock_coordinator.data["MBF_CELL_BOOST"] = 0x05A0  # 0x0500 | 0x00A0
    assert ent.current_option == "active (redox enabled)"

    # fallback
    mock_coordinator.data["MBF_CELL_BOOST"] = 12345  # invalid value
    assert ent.current_option == "inactive"


def test_select_filtration_speed_current_option(mock_coordinator):
    props = make_props(
        options_map={0: "low", 1: "mid", 2: "high"}, mask=0x0070, shift=4
    )
    ent = NeoPoolSelect(
        mock_coordinator, "test_entry", "MBF_PAR_FILTRATION_SPEED", props
    )
    # mask=0x0070, shift=4; tedy 16 => 1 (mid)
    mock_coordinator.data = {"MBF_PAR_FILTRATION_CONF": 16}
    assert ent.current_option == "mid"
    mock_coordinator.data = {"MBF_PAR_FILTRATION_CONF": 0}
    assert ent.current_option == "low"
    mock_coordinator.data = {"MBF_PAR_FILTRATION_CONF": 32}
    assert ent.current_option == "high"


def test_filtration_speed_unavailable_in_non_manual_mode(mock_coordinator):
    props = make_props(
        options_map={0: "low", 1: "mid", 2: "high"}, mask=0x0070, shift=4
    )
    ent = NeoPoolSelect(
        mock_coordinator, "test_entry", "MBF_PAR_FILTRATION_SPEED", props
    )
    mock_coordinator.last_update_success = True
    # Non-manual mode (1 = auto) -> unavailable
    mock_coordinator.data = {"MBF_PAR_FILTRATION_CONF": 0, "MBF_PAR_FILT_MODE": 1}
    assert ent.available is False
    # Manual mode (0) -> available
    mock_coordinator.data = {"MBF_PAR_FILTRATION_CONF": 0, "MBF_PAR_FILT_MODE": 0}
    assert ent.available is True
    # Coordinator not ready (last_update_success=False) -> unavailable regardless of mode
    mock_coordinator.last_update_success = False
    mock_coordinator.data = {"MBF_PAR_FILTRATION_CONF": 0, "MBF_PAR_FILT_MODE": 0}
    assert ent.available is False


@pytest.mark.parametrize(
    "key, mask, shift, conf_bits, expected",
    [
        # filtration1_speed: mask=0x0380, shift=7; slow=0<<7=0, mid=1<<7=128, fast=2<<7=256
        ("filtration1_speed", 0x0380, 7, 0, "low"),
        ("filtration1_speed", 0x0380, 7, 128, "mid"),
        ("filtration1_speed", 0x0380, 7, 256, "high"),
        # filtration2_speed: mask=0x1C00, shift=10; slow=0, mid=1<<10=1024, fast=2<<10=2048
        ("filtration2_speed", 0x1C00, 10, 0, "low"),
        ("filtration2_speed", 0x1C00, 10, 1024, "mid"),
        ("filtration2_speed", 0x1C00, 10, 2048, "high"),
        # filtration3_speed: mask=0xE000, shift=13; slow=0, mid=1<<13=8192, fast=2<<13=16384
        ("filtration3_speed", 0xE000, 13, 0, "low"),
        ("filtration3_speed", 0xE000, 13, 8192, "mid"),
        ("filtration3_speed", 0xE000, 13, 16384, "high"),
    ],
)
def test_current_option_filtration_timer_speed(
    mock_coordinator, key, mask, shift, conf_bits, expected
):
    props = {
        "options_map": {0: "low", 1: "mid", 2: "high"},
        "mask": mask,
        "shift": shift,
    }
    ent = NeoPoolSelect(mock_coordinator, "test_entry", key, props)
    mock_coordinator.data = {"MBF_PAR_FILTRATION_CONF": conf_bits}
    assert ent.current_option == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key, mask, shift, initial_conf, option, expected_written",
    [
        # filtration1_speed: mask=0x0380, shift=7
        ("filtration1_speed", 0x0380, 7, 0, "mid", 128),  # 1<<7
        ("filtration1_speed", 0x0380, 7, 0, "high", 256),  # 2<<7
        # filtration2_speed: mask=0x1C00, shift=10
        ("filtration2_speed", 0x1C00, 10, 0, "mid", 1024),  # 1<<10
        # filtration3_speed: mask=0xE000, shift=13
        ("filtration3_speed", 0xE000, 13, 0, "high", 16384),  # 2<<13
        # Non-zero initial_conf: verify unrelated bits are preserved
        # initial_conf=0x0001 (pump type=Hayward); setting filtration1 to "high" (2<<7=256)
        # should yield 0x0001 | 256 = 257, keeping bit 0 intact
        ("filtration1_speed", 0x0380, 7, 0x0001, "high", 0x0001 | (2 << 7)),
        # initial_conf has filtration2 set to "high" (2<<10=0x0800); setting filtration1 to "mid"
        # should preserve filtration2 bits: 0x0800 | (1<<7) = 0x0880
        ("filtration1_speed", 0x0380, 7, 0x0800, "mid", 0x0800 | (1 << 7)),
        # initial_conf has filtration1 set to "high" (2<<7=0x0100); setting filtration3 to "mid"
        # should preserve filtration1 bits: 0x0100 | (1<<13) = 0x0100 | 0x2000 = 0x2100
        ("filtration3_speed", 0xE000, 13, 0x0100, "mid", 0x0100 | (1 << 13)),
    ],
)
async def test_async_select_option_filtration_timer_speed(
    mock_coordinator, key, mask, shift, initial_conf, option, expected_written
):
    props = {
        "options_map": {0: "low", 1: "mid", 2: "high"},
        "mask": mask,
        "shift": shift,
        "register": 0x050F,
    }
    ent = NeoPoolSelect(mock_coordinator, "test_entry", key, props)
    ent.hass = MagicMock()
    ent.coordinator.client = AsyncMock()
    mock_coordinator.data = {"MBF_PAR_FILTRATION_CONF": initial_conf}
    await ent.async_select_option(option)
    ent.coordinator.client.async_write_register.assert_awaited_with(
        0x050F, expected_written, apply=True
    )


@pytest.mark.asyncio
async def test_select_async_setup_entry_adds_entities(monkeypatch):
    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        # FILTRATION_CONF: 1 → get_filtration_pump_type=True, MBF_CELL_BOOST: model OK
        data = {
            "MBF_PAR_FILTRATION_CONF": 1,
            "MBF_PAR_MODEL": 0x0002,
        }
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "neopool"

    hass = MagicMock()
    entry = DummyEntry()
    entry.runtime_data = DummyCoordinator()
    async_add_entities = MagicMock()

    # Patch SELECT_DEFINITIONS to make the test predictable
    from custom_components.neopool import select as select_module

    monkeypatch.setitem(
        select_module.SELECT_DEFINITIONS, "MBF_PAR_FILTRATION_SPEED", {"option": None}
    )
    monkeypatch.setitem(
        select_module.SELECT_DEFINITIONS, "MBF_CELL_BOOST", {"option": None}
    )

    # Patch get_filtration_pump_type to always return True
    monkeypatch.setattr(
        "custom_components.neopool.select.get_filtration_pump_type", lambda x: True
    )

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    entities = async_add_entities.call_args[0][0]
    keys = [e._key for e in entities]
    assert "MBF_PAR_FILTRATION_SPEED" in keys
    assert "MBF_CELL_BOOST" in keys


@pytest.mark.asyncio
async def test_select_async_setup_entry_option_disabled(monkeypatch):
    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {"test_option": False}

    class DummyCoordinator:
        data = {"MBF_PAR_FILTRATION_CONF": 1, "MBF_PAR_MODEL": 0x0002}
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "neopool"

    hass = MagicMock()
    entry = DummyEntry()
    entry.runtime_data = DummyCoordinator()
    async_add_entities = MagicMock()
    from custom_components.neopool import select as select_module

    monkeypatch.setitem(
        select_module.SELECT_DEFINITIONS, "TEST_SELECT", {"option": "test_option"}
    )
    monkeypatch.setattr(
        "custom_components.neopool.select.get_filtration_pump_type", lambda x: True
    )

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    entities = async_add_entities.call_args[0][0]
    keys = [e._key for e in entities]
    # Should not include TEST_SELECT, as option is False
    assert "TEST_SELECT" not in keys


@pytest.mark.asyncio
async def test_select_async_setup_entry_no_data(caplog):
    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data = None
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "neopool"

    hass = MagicMock()
    entry = DummyEntry()
    entry.runtime_data = DummyCoordinator()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    async_add_entities.assert_not_called()
    assert "No data from Modbus" in caplog.text


@pytest.mark.asyncio
async def test_async_added_to_hass_calls_super(mock_coordinator):
    props = make_props()
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "MBF_PAR_FILT_MODE", props)
    with patch.object(NeoPoolEntity, "async_added_to_hass", AsyncMock()) as sup:
        await ent.async_added_to_hass()
        sup.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_select_option_stop_field(mock_coordinator):
    props = make_props(select_type="timer_time")
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "relay_aux1_stop", props)
    mock_coordinator.data = {
        "relay_aux1_start": 3600,
        "relay_aux1_stop": 7200,
    }
    mock_coordinator.client = AsyncMock()
    mock_coordinator.client.async_write_register = AsyncMock(return_value=True)
    ent.hass = MagicMock()
    ent.hass.services = AsyncMock()
    ent.hass.services.async_call = AsyncMock(return_value=None)

    option = "03:00"
    with patch.object(ent, "async_write_ha_state", AsyncMock()):
        await ent.async_select_option(option)

    ent.hass.services.async_call.assert_any_call(
        "neopool",
        "set_timer",
        {
            "entry_id": "test_entry",
            "timer": "relay_aux1",
            "start": "01:00",
            "stop": "03:00",
        },
    )


def test_options_ph_pump_delay(mock_coordinator):
    """Test that the pH pump delay select returns the expected fixed options."""
    props = make_props(
        options_map=DELAY_OPTIONS_MAP, register=0x0433, select_type="mapped_register"
    )
    ent = NeoPoolSelect(
        mock_coordinator, "test_entry", "MBF_PAR_RELAY_ACTIVATION_DELAY", props
    )
    mock_coordinator.data = {"MBF_PAR_RELAY_ACTIVATION_DELAY": 20}
    opts = ent.options
    assert "10" in opts and "300" in opts
    assert "900" in opts and "1800" in opts and "3600" in opts
    # current value should be present even if not in the fixed list
    mock_coordinator.data["MBF_PAR_RELAY_ACTIVATION_DELAY"] = 25
    opts = ent.options
    assert "25" in opts


def test_current_option_ph_pump_delay(mock_coordinator):
    """Test that current_option returns the mapped label for the register value."""
    props = make_props(
        options_map=DELAY_OPTIONS_MAP, register=0x0433, select_type="mapped_register"
    )
    ent = NeoPoolSelect(
        mock_coordinator, "test_entry", "MBF_PAR_RELAY_ACTIVATION_DELAY", props
    )
    mock_coordinator.data = {"MBF_PAR_RELAY_ACTIVATION_DELAY": 120}
    assert ent.current_option == "120"
    mock_coordinator.data = {"MBF_PAR_RELAY_ACTIVATION_DELAY": None}  # type: ignore[dict-item]
    assert ent.current_option is None


@pytest.mark.asyncio
async def test_async_select_option_ph_pump_delay(mock_coordinator):
    """Test that selecting a delay writes (value - 10) to register 0x0433."""
    props = make_props(
        options_map=DELAY_OPTIONS_MAP,
        register=0x0433,
        select_type="mapped_register",
        write_offset=-10,
    )
    ent = NeoPoolSelect(
        mock_coordinator, "test_entry", "MBF_PAR_RELAY_ACTIVATION_DELAY", props
    )
    mock_coordinator.client = AsyncMock()
    ent.coordinator.client = mock_coordinator.client
    mock_coordinator.data = {"MBF_PAR_RELAY_ACTIVATION_DELAY": 60}

    # Select 180 (180s) -> should write 170 (device internally adds 10s)
    await ent.async_select_option("180")
    ent.coordinator.client.async_write_register.assert_awaited_with(0x0433, 170)
    # Optimistic update should set the register value (not the write value)
    assert mock_coordinator.data["MBF_PAR_RELAY_ACTIVATION_DELAY"] == 180


@pytest.mark.asyncio
async def test_select_option_blocked_during_winter_mode(mock_coordinator, caplog):
    """async_select_option is ignored when winter mode is active."""
    mock_coordinator.winter_mode = True
    props = {"register": 0x0412, "options_map": {1: "Manual", 2: "Auto"}}
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "MBF_PAR_FILT_MODE", props)
    with caplog.at_level("WARNING"):
        await ent.async_select_option("Manual")
    mock_coordinator.client.async_write_register.assert_not_called()
    assert "Winter mode is active" in caplog.text


def test_available_false_during_winter_mode(mock_coordinator):
    """NeoPoolSelect is unavailable when winter mode is active."""
    mock_coordinator.winter_mode = True
    props = {"register": 0x0412, "options_map": {1: "Manual", 2: "Auto"}}
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "MBF_PAR_FILT_MODE", props)
    assert ent.available is False


# ---------------------------------------------------------------------------
# MBF_PAR_FILTVALVE_PERIOD_MINUTES select tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_select_filtvalve_period_minutes_skipped_without_besgo(mock_coordinator):
    """MBF_PAR_FILTVALVE_PERIOD_MINUTES select must be skipped when Besgo valve is not configured."""
    from custom_components.neopool.select import async_setup_entry

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "neopool"
        data = {"MBF_PAR_FILTVALVE_ENABLE": 0, "MBF_PAR_FILTVALVE_GPIO": 0}

    from unittest.mock import MagicMock

    hass = MagicMock()
    entry = DummyEntry()
    entry.runtime_data = DummyCoordinator()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]

    keys = [e._key for e in async_add_entities.call_args[0][0]]
    assert "MBF_PAR_FILTVALVE_PERIOD_MINUTES" not in keys


@pytest.mark.asyncio
async def test_select_filtvalve_period_minutes_created_with_besgo(mock_coordinator):
    """MBF_PAR_FILTVALVE_PERIOD_MINUTES select must be created when Besgo valve is configured."""
    from custom_components.neopool.select import async_setup_entry

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "neopool"
        data = {"MBF_PAR_FILTVALVE_ENABLE": 1, "MBF_PAR_FILTVALVE_PERIOD_MINUTES": 1440}

    from unittest.mock import MagicMock

    hass = MagicMock()
    entry = DummyEntry()
    entry.runtime_data = DummyCoordinator()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]

    keys = [e._key for e in async_add_entities.call_args[0][0]]
    assert "MBF_PAR_FILTVALVE_PERIOD_MINUTES" in keys


@pytest.mark.asyncio
async def test_select_filtvalve_period_minutes_created_with_gpio_only(mock_coordinator):
    """MBF_PAR_FILTVALVE_PERIOD_MINUTES select must be created when only GPIO is set (ENABLE=0)."""
    from custom_components.neopool.select import async_setup_entry

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "neopool"
        data = {
            "MBF_PAR_FILTVALVE_ENABLE": 0,
            "MBF_PAR_FILTVALVE_GPIO": 5,
            "MBF_PAR_FILTVALVE_PERIOD_MINUTES": 1440,
        }

    from unittest.mock import MagicMock

    hass = MagicMock()
    entry = DummyEntry()
    entry.runtime_data = DummyCoordinator()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]

    keys = [e._key for e in async_add_entities.call_args[0][0]]
    assert "MBF_PAR_FILTVALVE_PERIOD_MINUTES" in keys


def test_select_filtvalve_period_minutes_current_option_known(mock_coordinator):
    """current_option returns the mapped label for a known minute value."""
    from custom_components.neopool.const import SELECT_DEFINITIONS

    props = SELECT_DEFINITIONS["MBF_PAR_FILTVALVE_PERIOD_MINUTES"]
    ent = NeoPoolSelect(
        mock_coordinator, "test_entry", "MBF_PAR_FILTVALVE_PERIOD_MINUTES", props
    )
    mock_coordinator.data = {"MBF_PAR_FILTVALVE_PERIOD_MINUTES": 1440}
    assert ent.current_option == "1_day"


def test_select_filtvalve_period_minutes_current_option_unknown(mock_coordinator):
    """current_option returns raw minutes string for an unmapped value."""
    from custom_components.neopool.const import SELECT_DEFINITIONS

    props = SELECT_DEFINITIONS["MBF_PAR_FILTVALVE_PERIOD_MINUTES"]
    ent = NeoPoolSelect(
        mock_coordinator, "test_entry", "MBF_PAR_FILTVALVE_PERIOD_MINUTES", props
    )
    mock_coordinator.data = {"MBF_PAR_FILTVALVE_PERIOD_MINUTES": 999}
    assert ent.current_option == "999m"


def test_select_filtvalve_period_minutes_options_prepend_unknown(mock_coordinator):
    """options prepends raw value when device holds an unmapped minute count."""
    from custom_components.neopool.const import SELECT_DEFINITIONS

    props = SELECT_DEFINITIONS["MBF_PAR_FILTVALVE_PERIOD_MINUTES"]
    ent = NeoPoolSelect(
        mock_coordinator, "test_entry", "MBF_PAR_FILTVALVE_PERIOD_MINUTES", props
    )
    mock_coordinator.data = {"MBF_PAR_FILTVALVE_PERIOD_MINUTES": 999}
    opts = ent.options
    assert opts[0] == "999m"
    assert "1_day" in opts


def test_select_filtvalve_period_minutes_options_known_value(mock_coordinator):
    """options returns standard list without prepend when device holds a known value."""
    from custom_components.neopool.const import SELECT_DEFINITIONS

    props = SELECT_DEFINITIONS["MBF_PAR_FILTVALVE_PERIOD_MINUTES"]
    ent = NeoPoolSelect(
        mock_coordinator, "test_entry", "MBF_PAR_FILTVALVE_PERIOD_MINUTES", props
    )
    mock_coordinator.data = {"MBF_PAR_FILTVALVE_PERIOD_MINUTES": 1440}
    opts = ent.options
    assert opts[0] == "1_day"
    assert "999m" not in opts


@pytest.mark.asyncio
async def test_async_select_option_filtvalve_period_minutes_label(mock_coordinator):
    """async_select_option writes the correct minute value for a mapped label."""
    from custom_components.neopool.const import SELECT_DEFINITIONS

    props = SELECT_DEFINITIONS["MBF_PAR_FILTVALVE_PERIOD_MINUTES"]
    ent = NeoPoolSelect(
        mock_coordinator, "test_entry", "MBF_PAR_FILTVALVE_PERIOD_MINUTES", props
    )
    ent.hass = MagicMock()
    ent.coordinator.client = AsyncMock()
    ent.coordinator.async_request_refresh = AsyncMock()
    ent.async_write_ha_state = Mock()
    await ent.async_select_option("1_day")
    ent.coordinator.client.async_write_register.assert_awaited_with(0x04ED, 1440)


@pytest.mark.asyncio
async def test_async_select_option_filtvalve_period_minutes_raw_m(mock_coordinator):
    """async_select_option parses and writes a raw 'Xm' string."""
    from custom_components.neopool.const import SELECT_DEFINITIONS

    props = SELECT_DEFINITIONS["MBF_PAR_FILTVALVE_PERIOD_MINUTES"]
    ent = NeoPoolSelect(
        mock_coordinator, "test_entry", "MBF_PAR_FILTVALVE_PERIOD_MINUTES", props
    )
    ent.hass = MagicMock()
    ent.coordinator.client = AsyncMock()
    ent.coordinator.async_request_refresh = AsyncMock()
    ent.async_write_ha_state = Mock()
    await ent.async_select_option("999m")
    ent.coordinator.client.async_write_register.assert_awaited_with(0x04ED, 999)


# MBF_PAR_FILTVALVE_MODE select tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_select_filtvalve_mode_skipped_without_besgo(mock_coordinator):
    """MBF_PAR_FILTVALVE_MODE select must be skipped when Besgo valve is not configured."""
    from custom_components.neopool.select import async_setup_entry

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "neopool"
        data = {"MBF_PAR_FILTVALVE_ENABLE": 0, "MBF_PAR_FILTVALVE_GPIO": 0}

    from unittest.mock import MagicMock

    hass = MagicMock()
    entry = DummyEntry()
    entry.runtime_data = DummyCoordinator()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]

    keys = [e._key for e in async_add_entities.call_args[0][0]]
    assert "MBF_PAR_FILTVALVE_MODE" not in keys


@pytest.mark.asyncio
async def test_select_filtvalve_mode_created_with_besgo(mock_coordinator):
    """MBF_PAR_FILTVALVE_MODE select must be created when Besgo valve is configured."""
    from custom_components.neopool.select import async_setup_entry

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "neopool"
        data = {"MBF_PAR_FILTVALVE_ENABLE": 1, "MBF_PAR_FILTVALVE_MODE": 1}

    from unittest.mock import MagicMock

    hass = MagicMock()
    entry = DummyEntry()
    entry.runtime_data = DummyCoordinator()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]

    keys = [e._key for e in async_add_entities.call_args[0][0]]
    assert "MBF_PAR_FILTVALVE_MODE" in keys


@pytest.mark.asyncio
async def test_select_filtvalve_mode_created_with_gpio_only(mock_coordinator):
    """MBF_PAR_FILTVALVE_MODE select must be created when only GPIO is set (ENABLE=0)."""
    from custom_components.neopool.select import async_setup_entry

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "neopool"
        data = {
            "MBF_PAR_FILTVALVE_ENABLE": 0,
            "MBF_PAR_FILTVALVE_GPIO": 5,
            "MBF_PAR_FILTVALVE_MODE": 1,
        }

    from unittest.mock import MagicMock

    hass = MagicMock()
    entry = DummyEntry()
    entry.runtime_data = DummyCoordinator()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]

    keys = [e._key for e in async_add_entities.call_args[0][0]]
    assert "MBF_PAR_FILTVALVE_MODE" in keys


@pytest.mark.parametrize(
    "raw_value, expected_option",
    [
        (1, "enabled"),
        (3, "always_on"),
        (4, "always_off"),
        (0, None),  # disabled - not in options_map, returns None
    ],
)
def test_select_filtvalve_mode_current_option(
    mock_coordinator, raw_value, expected_option
):
    """current_option maps CTIMER enum values to the correct option strings."""
    from custom_components.neopool.const import SELECT_DEFINITIONS

    props = SELECT_DEFINITIONS["MBF_PAR_FILTVALVE_MODE"]
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "MBF_PAR_FILTVALVE_MODE", props)
    mock_coordinator.data = {"MBF_PAR_FILTVALVE_MODE": raw_value}
    assert ent.current_option == expected_option


def test_select_filtvalve_mode_options(mock_coordinator):
    """options returns the three valid CTIMER mode strings."""
    from custom_components.neopool.const import SELECT_DEFINITIONS

    props = SELECT_DEFINITIONS["MBF_PAR_FILTVALVE_MODE"]
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "MBF_PAR_FILTVALVE_MODE", props)
    mock_coordinator.data = {"MBF_PAR_FILTVALVE_MODE": 1}
    assert ent.options == ["enabled", "always_on", "always_off"]


def test_optimistic_update_relay_mode(mock_coordinator):
    """Optimistic update sets relay enable value for relay_mode selects."""
    props = SELECT_DEFINITIONS["relay_aux1_mode"]
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "relay_aux1_mode", props)
    mock_coordinator.data = {"relay_aux1_enable": 4}
    ent._optimistic_update(3)
    assert mock_coordinator.data["relay_aux1_enable"] == 3


def test_optimistic_update_filt_mode(mock_coordinator):
    """Optimistic update sets MBF_PAR_FILT_MODE value."""
    props = SELECT_DEFINITIONS["MBF_PAR_FILT_MODE"]
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "MBF_PAR_FILT_MODE", props)
    mock_coordinator.data = {"MBF_PAR_FILT_MODE": 0}
    ent._optimistic_update(1)
    assert mock_coordinator.data["MBF_PAR_FILT_MODE"] == 1


def test_optimistic_update_noop_when_data_is_none(mock_coordinator):
    """Optimistic update is a no-op when coordinator data is None."""
    props = SELECT_DEFINITIONS["MBF_PAR_FILT_MODE"]
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "MBF_PAR_FILT_MODE", props)
    mock_coordinator.data = None
    ent._optimistic_update(1)  # Should not raise


def test_optimistic_update_noop_when_value_is_none(mock_coordinator):
    """Optimistic update is a no-op when value is None."""
    props = SELECT_DEFINITIONS["MBF_PAR_FILT_MODE"]
    ent = NeoPoolSelect(mock_coordinator, "test_entry", "MBF_PAR_FILT_MODE", props)
    mock_coordinator.data = {"MBF_PAR_FILT_MODE": 0}
    ent._optimistic_update(None)
    assert mock_coordinator.data["MBF_PAR_FILT_MODE"] == 0


@pytest.mark.asyncio
async def test_setup_entry_skips_relay_activation_delay_without_ph_module():
    """MBF_PAR_RELAY_ACTIVATION_DELAY is skipped when pH module is not detected."""
    from custom_components.neopool.select import async_setup_entry

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options: dict = {}

    class DummyCoordinator:
        data = {
            # pH module NOT detected
            "pH measurement module detected": False,
        }
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "neopool"

    hass = MagicMock()
    entry = DummyEntry()
    entry.runtime_data = DummyCoordinator()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]

    entities = async_add_entities.call_args[0][0]
    keys = [e._key for e in entities]
    assert "MBF_PAR_RELAY_ACTIVATION_DELAY" not in keys
