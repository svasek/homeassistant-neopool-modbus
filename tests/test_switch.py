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
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vistapool.const import EXEC_REGISTER
from custom_components.vistapool.switch import VistaPoolSwitch, async_setup_entry


@pytest.fixture(autouse=True)
def _fast_sleep(monkeypatch):
    """Patch asyncio.sleep to a no-op for all tests in this module to speed them up."""
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())


@pytest.fixture
def mock_coordinator():
    mock = MagicMock()
    mock.data = {}
    mock.device_slug = "vistapool"
    mock.config_entry.entry_id = "test_entry"
    mock.winter_mode = False
    mock.request_refresh_with_followup = MagicMock()
    return mock


def make_props(**kwargs):
    d = {}
    d.update(kwargs)
    return d


@pytest.mark.asyncio
async def test_turn_on_manual_filtration(mock_coordinator):
    props = make_props(switch_type="manual_filtration")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "manual", props)
    ent.coordinator.client = AsyncMock()
    ent.coordinator.async_request_refresh = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    await ent.async_turn_on()
    ent.coordinator.client.async_write_register.assert_awaited_with(0x0413, 1)


@pytest.mark.asyncio
async def test_turn_off_manual_filtration(mock_coordinator):
    props = make_props(switch_type="manual_filtration")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "manual", props)
    ent.coordinator.client = AsyncMock()
    ent.coordinator.async_request_refresh = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    await ent.async_turn_off()
    ent.coordinator.client.async_write_register.assert_awaited_with(0x0413, 0)


@pytest.mark.asyncio
async def test_turn_on_aux(mock_coordinator):
    props = make_props(switch_type="aux", relay_index=2)
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "aux2", props)
    ent.coordinator.client = AsyncMock()
    ent.coordinator.async_request_refresh = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    await ent.async_turn_on()
    ent.coordinator.client.async_write_aux_relay.assert_awaited_with(2, True)


@pytest.mark.asyncio
async def test_turn_off_aux(mock_coordinator):
    props = make_props(switch_type="aux", relay_index=2)
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "aux2", props)
    ent.coordinator.client = AsyncMock()
    ent.coordinator.async_request_refresh = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    await ent.async_turn_off()
    ent.coordinator.client.async_write_aux_relay.assert_awaited_with(2, False)


@pytest.mark.asyncio
async def test_turn_on_auto_time_sync(mock_coordinator):
    props = make_props(switch_type="auto_time_sync")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "sync", props)
    ent.coordinator.set_auto_time_sync = AsyncMock()
    ent.coordinator.async_request_refresh = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    await ent.async_turn_on()
    mock_coordinator.set_auto_time_sync.assert_awaited_with(True)


@pytest.mark.asyncio
async def test_turn_off_auto_time_sync(mock_coordinator):
    props = make_props(switch_type="auto_time_sync")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "sync", props)
    ent.coordinator.set_auto_time_sync = AsyncMock()
    ent.coordinator.async_request_refresh = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    await ent.async_turn_off()
    mock_coordinator.set_auto_time_sync.assert_awaited_with(False)


@pytest.mark.asyncio
async def test_turn_on_relay_timer(mock_coordinator):
    props = make_props(
        switch_type="relay_timer",
        function_addr=0x0100,
        function_code=7,
        timer_block_addr=0x0200,
    )
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "aux1", props)
    ent.coordinator.client = AsyncMock()
    ent.coordinator.async_request_refresh = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    await ent.async_turn_on()
    ent.coordinator.client.async_write_register.assert_any_await(0x0100, 7)
    ent.coordinator.client.async_write_register.assert_any_await(0x0200, 3)
    ent.coordinator.client.async_write_register.assert_any_await(EXEC_REGISTER, 1)


@pytest.mark.asyncio
async def test_turn_off_relay_timer(mock_coordinator):
    props = make_props(switch_type="relay_timer", timer_block_addr=0x0200)
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "aux1", props)
    ent.coordinator.client = AsyncMock()
    ent.coordinator.async_request_refresh = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    await ent.async_turn_off()
    ent.coordinator.client.async_write_register.assert_any_await(0x0200, 4)
    ent.coordinator.client.async_write_register.assert_any_await(EXEC_REGISTER, 1)


@pytest.mark.asyncio
async def test_turn_on_climate_mode(mock_coordinator):
    props = make_props(switch_type="climate_mode", function_addr=0x0417)
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "MBF_PAR_CLIMA_ONOFF", props)
    ent.coordinator.client = AsyncMock()
    ent.coordinator.async_request_refresh = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    await ent.async_turn_on()
    ent.coordinator.client.async_write_register.assert_awaited_with(0x0417, 1)


@pytest.mark.asyncio
async def test_turn_off_climate_mode(mock_coordinator):
    props = make_props(switch_type="climate_mode", function_addr=0x0417)
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "MBF_PAR_CLIMA_ONOFF", props)
    ent.coordinator.client = AsyncMock()
    ent.coordinator.async_request_refresh = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    await ent.async_turn_off()
    ent.coordinator.client.async_write_register.assert_awaited_with(0x0417, 0)


@pytest.mark.asyncio
async def test_turn_on_smart_anti_freeze(mock_coordinator):
    props = make_props(switch_type="smart_anti_freeze", function_addr=0x041A)
    ent = VistaPoolSwitch(
        mock_coordinator, "test_entry", "MBF_PAR_SMART_ANTI_FREEZE", props
    )
    ent.coordinator.client = AsyncMock()
    ent.coordinator.async_request_refresh = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    await ent.async_turn_on()
    ent.coordinator.client.async_write_register.assert_awaited_with(0x041A, 1)


@pytest.mark.asyncio
async def test_turn_off_smart_anti_freeze(mock_coordinator):
    props = make_props(switch_type="smart_anti_freeze", function_addr=0x041A)
    ent = VistaPoolSwitch(
        mock_coordinator, "test_entry", "MBF_PAR_SMART_ANTI_FREEZE", props
    )
    ent.coordinator.client = AsyncMock()
    ent.coordinator.async_request_refresh = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    await ent.async_turn_off()
    ent.coordinator.client.async_write_register.assert_awaited_with(0x041A, 0)


def test_is_on_smart_anti_freeze(mock_coordinator):
    props = make_props(switch_type="smart_anti_freeze")
    ent = VistaPoolSwitch(
        mock_coordinator, "test_entry", "MBF_PAR_SMART_ANTI_FREEZE", props
    )
    mock_coordinator.data = {"MBF_PAR_SMART_ANTI_FREEZE": 1}
    assert ent.is_on is True
    mock_coordinator.data = {"MBF_PAR_SMART_ANTI_FREEZE": 0}
    assert ent.is_on is False


def test_is_on_manual_filtration_on(mock_coordinator):
    props = make_props(switch_type="manual_filtration")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "foo", props)
    mock_coordinator.data = {"MBF_PAR_FILT_MODE": 0, "MBF_PAR_FILT_MANUAL_STATE": 1}
    assert ent.is_on is True


def test_is_on_manual_filtration_off(mock_coordinator):
    props = make_props(switch_type="manual_filtration")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "foo", props)
    mock_coordinator.data = {"MBF_PAR_FILT_MODE": 0, "MBF_PAR_FILT_MANUAL_STATE": 0}
    assert ent.is_on is False
    mock_coordinator.data = {"MBF_PAR_FILT_MODE": 1, "MBF_PAR_FILT_MANUAL_STATE": 1}
    assert ent.is_on is False


def test_is_on_aux(mock_coordinator):
    props = make_props(switch_type="aux")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "aux1", props)
    mock_coordinator.data = {"aux1": True}
    assert ent.is_on is True
    mock_coordinator.data = {"aux1": False}
    assert ent.is_on is False


def test_is_on_auto_time_sync(mock_coordinator):
    props = make_props(switch_type="auto_time_sync")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "auto_time_sync", props)
    mock_coordinator.auto_time_sync = True
    assert ent.is_on is True
    mock_coordinator.auto_time_sync = False
    assert ent.is_on is False


def test_is_on_timer_enable(mock_coordinator):
    props = make_props(switch_type="timer_enable")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "timer1", props)
    mock_coordinator.data = {"timer1": 1}
    assert ent.is_on is True
    mock_coordinator.data = {"timer1": 0}
    assert ent.is_on is False


def test_is_on_relay_timer(mock_coordinator):
    props = make_props(switch_type="relay_timer")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "aux1", props)
    mock_coordinator.data = {"relay_aux1_enable": 3}
    assert ent.is_on is True
    mock_coordinator.data = {"relay_aux1_enable": 4}
    assert ent.is_on is False
    mock_coordinator.data = {}
    assert ent.is_on is False


def test_is_on_unknown_type(mock_coordinator):
    props = make_props(switch_type="unknown")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "foo", props)
    assert ent.is_on is False


def test_is_on_climate_mode(mock_coordinator):
    props = make_props(switch_type="climate_mode")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "MBF_PAR_CLIMA_ONOFF", props)
    mock_coordinator.data = {"MBF_PAR_CLIMA_ONOFF": 1}
    assert ent.is_on is True
    mock_coordinator.data = {"MBF_PAR_CLIMA_ONOFF": 0}
    assert ent.is_on is False


def test_available_manual_filtration(mock_coordinator):
    props = make_props(switch_type="manual_filtration")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "foo", props)
    mock_coordinator.data = {"MBF_PAR_FILT_MODE": 0}
    assert ent.available is True
    # All non-manual modes must be unavailable
    for mode in (1, 2, 3, 4, 13):  # auto, heating, smart, intelligent, backwash
        mock_coordinator.data = {"MBF_PAR_FILT_MODE": mode}
        assert ent.available is False, f"Expected unavailable for mode={mode}"


def test_available_relay_timer_aux(mock_coordinator):
    props = make_props(switch_type="relay_timer")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "aux1", props)
    mock_coordinator.data = {"relay_aux1_enable": 3}
    assert ent.available is True
    mock_coordinator.data = {"relay_aux1_enable": 4}
    assert ent.available is True
    mock_coordinator.data = {"relay_aux1_enable": 1}
    assert ent.available is False
    mock_coordinator.data = {}
    assert ent.available is False


def test_available_relay_timer_light(mock_coordinator):
    props = make_props(switch_type="relay_timer")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "light", props)
    mock_coordinator.data = {"relay_light_enable": 3}
    assert ent.available is True
    mock_coordinator.data = {"relay_light_enable": 0}
    assert ent.available is False


def test_available_relay_timer_other(mock_coordinator):
    props = make_props(switch_type="relay_timer")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "somethingelse", props)
    mock_coordinator.data = {}
    assert ent.available is True


def test_available_unknown_type(mock_coordinator):
    props = make_props(switch_type="unknown")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "foo", props)
    assert ent.available is True


def test_icon_on_off(mock_coordinator):
    props = make_props(
        switch_type="aux", icon_on="mdi:lightbulb-on", icon_off="mdi:lightbulb-off"
    )
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "aux1", props)
    mock_coordinator.data = {"aux1": True}
    assert ent.icon == "mdi:lightbulb-on"
    mock_coordinator.data = {"aux1": False}
    assert ent.icon == "mdi:lightbulb-off"


@pytest.mark.asyncio
async def test_switch_async_setup_entry_adds_entities(monkeypatch):
    class DummyEntry:
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data = {"MBF_PAR_FILT_MODE": 0, "relay_aux1_enable": 3}
        config_entry = DummyEntry()
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    from custom_components.vistapool import switch as switch_module

    monkeypatch.setitem(
        switch_module.SWITCH_DEFINITIONS, "manual", {"switch_type": "manual_filtration"}
    )
    monkeypatch.setitem(
        switch_module.SWITCH_DEFINITIONS, "aux1", {"switch_type": "relay_timer"}
    )
    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    entities = async_add_entities.call_args[0][0]
    keys = [e._key for e in entities]
    assert "manual" in keys
    assert "aux1" in keys


@pytest.mark.asyncio
async def test_switch_setup_skips_smart_antifreeze_when_no_temp(monkeypatch):
    class DummyEntry:
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data = {"MBF_PAR_TEMPERATURE_ACTIVE": 0}
        config_entry = DummyEntry()
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    from custom_components.vistapool import switch as switch_module

    monkeypatch.setitem(
        switch_module.SWITCH_DEFINITIONS,
        "MBF_PAR_SMART_ANTI_FREEZE",
        {
            "switch_type": "smart_anti_freeze",
            "function_addr": 0x041A,
        },
    )

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    entities = async_add_entities.call_args[0][0]
    keys = [e._key for e in entities]
    assert "MBF_PAR_SMART_ANTI_FREEZE" not in keys


@pytest.mark.asyncio
async def test_switch_async_setup_entry_no_data(caplog):
    class DummyEntry:
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data = None
        config_entry = DummyEntry()
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()
    with caplog.at_level("WARNING"):
        await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
        assert "No data from Modbus" in caplog.text
    async_add_entities.assert_not_called()


@pytest.mark.asyncio
async def test_switch_async_setup_entry_option_disabled(monkeypatch):
    class DummyEntry:
        entry_id = "test_entry"
        options = {"test_option": False}

    class DummyCoordinator:
        data = {"MBF_PAR_FILT_MODE": 0, "relay_aux1_enable": 3}
        config_entry = DummyEntry()
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    from custom_components.vistapool import switch as switch_module

    monkeypatch.setitem(
        switch_module.SWITCH_DEFINITIONS,
        "Test Option Switch",
        {
            "switch_type": "relay_timer",
            "option": "test_option",
        },
    )

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    entities = async_add_entities.call_args[0][0]
    keys = [e._key for e in entities]
    assert "Test Option Switch" not in keys


def test_available_relay_timer(mock_coordinator):
    props = make_props(switch_type="relay_timer", relay_key="aux1")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "aux1", props)
    # relay_*_enable == 3 → available
    mock_coordinator.data = {"relay_aux1_enable": 3}
    assert ent.available is True
    # relay_*_enable != 3 → unavailable
    mock_coordinator.data = {"relay_aux1_enable": 0}
    assert ent.available is False
    # relay_*_enable missing → unavailable
    mock_coordinator.data = {}
    assert ent.available is False


def test_icon_fallback_none(mock_coordinator):
    props = make_props()
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "foo", props)
    assert ent.icon is None


def test_icon_fallback_attr_icon(mock_coordinator):
    props = make_props(icon="mdi:test")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "foo", props)
    assert ent.icon == "mdi:test"


@pytest.mark.asyncio
async def test_switch_setup_skips_hidro_cover_without_hydro_module():
    """MBF_PAR_HIDRO_COVER_ENABLE is skipped when hydrolysis module is absent."""

    class DummyEntry:
        entry_id = "test_entry"
        options = {"use_cover_sensor": True}  # cover sensor option enabled

    class DummyCoordinator:
        data = {"Hydrolysis module detected": False}  # hydro module absent
        config_entry = DummyEntry()
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    keys = [e._key for e in async_add_entities.call_args[0][0]]
    assert "MBF_PAR_HIDRO_COVER_ENABLE" not in keys
    assert "MBF_PAR_HIDRO_TEMP_SHUTDOWN" not in keys


@pytest.mark.asyncio
async def test_switch_setup_creates_hidro_cover_with_hydro_module():
    """MBF_PAR_HIDRO_COVER_ENABLE is created when hydrolysis module is present and cover sensor option is enabled."""

    class DummyEntry:
        entry_id = "test_entry"
        options = {"use_cover_sensor": True}  # cover sensor option enabled

    class DummyCoordinator:
        data = {
            "Hydrolysis module detected": True,
            "MBF_PAR_TEMPERATURE_ACTIVE": 1,
        }
        config_entry = DummyEntry()
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    keys = [e._key for e in async_add_entities.call_args[0][0]]
    assert "MBF_PAR_HIDRO_COVER_ENABLE" in keys
    assert "MBF_PAR_HIDRO_TEMP_SHUTDOWN" in keys


@pytest.mark.asyncio
async def test_switch_setup_skips_hidro_temp_shutdown_without_temp_sensor():
    """MBF_PAR_HIDRO_TEMP_SHUTDOWN is skipped when temperature sensor is inactive."""

    class DummyEntry:
        entry_id = "test_entry"
        options = {"use_cover_sensor": True}  # cover sensor option enabled

    class DummyCoordinator:
        data = {
            "Hydrolysis module detected": True,
            "MBF_PAR_TEMPERATURE_ACTIVE": 0,  # but temp sensor inactive
        }
        config_entry = DummyEntry()
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    keys = [e._key for e in async_add_entities.call_args[0][0]]
    assert "MBF_PAR_HIDRO_COVER_ENABLE" in keys  # cover switch is still shown
    assert (
        "MBF_PAR_HIDRO_TEMP_SHUTDOWN" not in keys
    )  # temp shutdown requires temp sensor


@pytest.mark.asyncio
async def test_switch_setup_skips_hidro_cover_without_cover_sensor():
    """Cover entities are skipped when cover sensor option is not enabled in integration settings."""

    class DummyEntry:
        entry_id = "test_entry"
        options = {}  # use_cover_sensor defaults to False

    class DummyCoordinator:
        data = {
            "Hydrolysis module detected": True,
            "MBF_PAR_TEMPERATURE_ACTIVE": 1,
        }
        config_entry = DummyEntry()
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    keys = [e._key for e in async_add_entities.call_args[0][0]]
    assert "MBF_PAR_HIDRO_COVER_ENABLE" not in keys
    assert "MBF_PAR_HIDRO_TEMP_SHUTDOWN" not in keys


# --- Bitmask switch tests ---


@pytest.mark.asyncio
async def test_turn_on_bitmask(mock_coordinator):
    """Turning ON a bitmask switch ORs the mask bit into the current register value."""
    props = make_props(
        switch_type="bitmask",
        function_addr=0x042C,
        mask_bit=0x0001,
        data_key="MBF_PAR_HIDRO_COVER_ENABLE",
    )
    ent = VistaPoolSwitch(
        mock_coordinator, "test_entry", "MBF_PAR_HIDRO_COVER_ENABLE", props
    )
    mock_coordinator.data = {"MBF_PAR_HIDRO_COVER_ENABLE": 0x0002}  # bit1 already set
    ent.coordinator.client = AsyncMock()
    ent.coordinator.async_request_refresh = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    await ent.async_turn_on()
    # Expected: 0x0002 | 0x0001 = 0x0003
    ent.coordinator.client.async_write_register.assert_awaited_with(
        0x042C, 0x0003, apply=True
    )


@pytest.mark.asyncio
async def test_turn_off_bitmask(mock_coordinator):
    """Turning OFF a bitmask switch AND-NOTs the mask bit from the current register value."""
    props = make_props(
        switch_type="bitmask",
        function_addr=0x042C,
        mask_bit=0x0001,
        data_key="MBF_PAR_HIDRO_COVER_ENABLE",
    )
    ent = VistaPoolSwitch(
        mock_coordinator, "test_entry", "MBF_PAR_HIDRO_COVER_ENABLE", props
    )
    mock_coordinator.data = {"MBF_PAR_HIDRO_COVER_ENABLE": 0x0003}  # both bits set
    ent.coordinator.client = AsyncMock()
    ent.coordinator.async_request_refresh = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    await ent.async_turn_off()
    # Expected: 0x0003 & ~0x0001 = 0x0002
    ent.coordinator.client.async_write_register.assert_awaited_with(
        0x042C, 0x0002, apply=True
    )


def test_is_on_bitmask(mock_coordinator):
    """is_on returns True when the mask bit is set in the register value."""
    props = make_props(
        switch_type="bitmask",
        mask_bit=0x0001,
        data_key="MBF_PAR_HIDRO_COVER_ENABLE",
    )
    ent = VistaPoolSwitch(
        mock_coordinator, "test_entry", "MBF_PAR_HIDRO_COVER_ENABLE", props
    )
    mock_coordinator.data = {"MBF_PAR_HIDRO_COVER_ENABLE": 0x0001}
    assert ent.is_on is True
    mock_coordinator.data = {"MBF_PAR_HIDRO_COVER_ENABLE": 0x0002}
    assert ent.is_on is False
    mock_coordinator.data = {}  # missing key -> defaults to 0
    assert ent.is_on is False


def test_is_on_bitmask_second_bit(mock_coordinator):
    """is_on works for bit 1 (temperature shutdown flag)."""
    props = make_props(
        switch_type="bitmask",
        mask_bit=0x0002,
        data_key="MBF_PAR_HIDRO_COVER_ENABLE",
    )
    ent = VistaPoolSwitch(
        mock_coordinator, "test_entry", "MBF_PAR_HIDRO_TEMP_SHUTDOWN", props
    )
    mock_coordinator.data = {"MBF_PAR_HIDRO_COVER_ENABLE": 0x0003}
    assert ent.is_on is True
    mock_coordinator.data = {"MBF_PAR_HIDRO_COVER_ENABLE": 0x0001}
    assert ent.is_on is False


# --- Winter mode switch tests ---


@pytest.mark.asyncio
async def test_turn_on_winter_mode(mock_coordinator):
    """Turning ON the winter_mode switch calls coordinator.set_winter_mode(True)."""
    props = make_props(switch_type="winter_mode")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "WINTER_MODE", props)
    ent.coordinator.set_winter_mode = AsyncMock()
    ent.coordinator.async_request_refresh = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    await ent.async_turn_on()
    mock_coordinator.set_winter_mode.assert_awaited_with(True)


@pytest.mark.asyncio
async def test_turn_off_winter_mode(mock_coordinator):
    """Turning OFF the winter_mode switch calls coordinator.set_winter_mode(False)."""
    props = make_props(switch_type="winter_mode")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "WINTER_MODE", props)
    ent.coordinator.set_winter_mode = AsyncMock()
    ent.coordinator.async_request_refresh = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    await ent.async_turn_off()
    mock_coordinator.set_winter_mode.assert_awaited_with(False)


def test_is_on_winter_mode(mock_coordinator):
    """is_on reflects coordinator.winter_mode attribute."""
    props = make_props(switch_type="winter_mode")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "WINTER_MODE", props)
    mock_coordinator.winter_mode = True
    assert ent.is_on is True
    mock_coordinator.winter_mode = False
    assert ent.is_on is False


@pytest.mark.asyncio
async def test_turn_on_blocked_during_winter_mode(mock_coordinator):
    """Non-exempt switch turn_on is ignored when winter mode is active."""
    mock_coordinator.winter_mode = True
    props = make_props(switch_type="manual_filtration")
    ent = VistaPoolSwitch(
        mock_coordinator, "test_entry", "MBF_PAR_FILT_MANUAL_STATE", props
    )
    mock_coordinator.client.async_write_register = AsyncMock()
    await ent.async_turn_on()
    mock_coordinator.client.async_write_register.assert_not_called()


@pytest.mark.asyncio
async def test_turn_off_blocked_during_winter_mode(mock_coordinator):
    """Non-exempt switch turn_off is ignored when winter mode is active."""
    mock_coordinator.winter_mode = True
    props = make_props(switch_type="manual_filtration")
    ent = VistaPoolSwitch(
        mock_coordinator, "test_entry", "MBF_PAR_FILT_MANUAL_STATE", props
    )
    mock_coordinator.client.async_write_register = AsyncMock()
    await ent.async_turn_off()
    mock_coordinator.client.async_write_register.assert_not_called()


@pytest.mark.asyncio
async def test_auto_time_sync_turn_on_not_blocked_during_winter_mode(mock_coordinator):
    """auto_time_sync switch is not blocked by winter mode — it only updates HA options."""
    mock_coordinator.winter_mode = True
    mock_coordinator.set_auto_time_sync = AsyncMock()
    mock_coordinator.async_request_refresh = AsyncMock()
    props = make_props(switch_type="auto_time_sync")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "auto_time_sync", props)
    ent.async_write_ha_state = MagicMock()
    await ent.async_turn_on()
    mock_coordinator.set_auto_time_sync.assert_awaited_once_with(True)


@pytest.mark.asyncio
async def test_auto_time_sync_turn_off_not_blocked_during_winter_mode(mock_coordinator):
    """auto_time_sync switch turn_off is not blocked by winter mode."""
    mock_coordinator.winter_mode = True
    mock_coordinator.set_auto_time_sync = AsyncMock()
    mock_coordinator.async_request_refresh = AsyncMock()
    props = make_props(switch_type="auto_time_sync")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "auto_time_sync", props)
    ent.async_write_ha_state = MagicMock()
    await ent.async_turn_off()
    mock_coordinator.set_auto_time_sync.assert_awaited_once_with(False)


def test_available_returns_false_during_winter_mode(mock_coordinator):
    """available returns False for non-winter_mode switch when winter mode is active."""
    mock_coordinator.winter_mode = True
    props = make_props(switch_type="manual_filtration")
    ent = VistaPoolSwitch(
        mock_coordinator, "test_entry", "MBF_PAR_FILT_MANUAL_STATE", props
    )
    assert ent.available is False


def test_available_false_on_coordinator_failure(mock_coordinator):
    """available returns False when coordinator update fails (winter mode off)."""
    mock_coordinator.winter_mode = False
    mock_coordinator.last_update_success = False
    props = make_props(switch_type="manual_filtration")
    ent = VistaPoolSwitch(
        mock_coordinator, "test_entry", "MBF_PAR_FILT_MANUAL_STATE", props
    )
    assert ent.available is False


def test_available_winter_mode_switch_during_winter_mode(mock_coordinator):
    """The winter_mode switch itself stays available while winter mode is active."""
    mock_coordinator.winter_mode = True
    props = make_props(switch_type="winter_mode")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "WINTER_MODE", props)
    assert ent.available is True


def test_available_winter_mode_switch_during_coordinator_failure(mock_coordinator):
    """The winter_mode switch stays available even when coordinator.last_update_success is False.

    A Modbus gateway disconnection is exactly the scenario the user needs winter mode for,
    so the switch must remain operable regardless of coordinator health.
    """
    mock_coordinator.winter_mode = False
    mock_coordinator.last_update_success = False
    props = make_props(switch_type="winter_mode")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "WINTER_MODE", props)
    assert ent.available is True


# --- UV Mode switch tests ---


@pytest.mark.asyncio
async def test_turn_on_uv_mode(mock_coordinator):
    props = make_props(switch_type="uv_mode", function_addr=0x0427)
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "MBF_PAR_UV_MODE", props)
    ent.coordinator.client = AsyncMock()
    ent.coordinator.async_request_refresh = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    await ent.async_turn_on()
    ent.coordinator.client.async_write_register.assert_awaited_with(0x0427, 1)


@pytest.mark.asyncio
async def test_turn_off_uv_mode(mock_coordinator):
    props = make_props(switch_type="uv_mode", function_addr=0x0427)
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "MBF_PAR_UV_MODE", props)
    ent.coordinator.client = AsyncMock()
    ent.coordinator.async_request_refresh = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    await ent.async_turn_off()
    ent.coordinator.client.async_write_register.assert_awaited_with(0x0427, 0)


def test_is_on_uv_mode(mock_coordinator):
    props = make_props(switch_type="uv_mode")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "MBF_PAR_UV_MODE", props)
    mock_coordinator.data = {"MBF_PAR_UV_MODE": 1}
    assert ent.is_on is True
    mock_coordinator.data = {"MBF_PAR_UV_MODE": 0}
    assert ent.is_on is False
    mock_coordinator.data = {}
    assert ent.is_on is False


@pytest.mark.asyncio
async def test_switch_setup_includes_uv_mode_when_relay_assigned(monkeypatch):
    class DummyEntry:
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data = {"MBF_PAR_UV_RELAY_GPIO": 3}
        config_entry = DummyEntry()
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    from custom_components.vistapool import switch as switch_module

    monkeypatch.setitem(
        switch_module.SWITCH_DEFINITIONS,
        "MBF_PAR_UV_MODE",
        {
            "switch_type": "uv_mode",
            "function_addr": 0x0427,
        },
    )

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    entities = async_add_entities.call_args[0][0]
    keys = [e._key for e in entities]
    assert "MBF_PAR_UV_MODE" in keys


@pytest.mark.asyncio
async def test_switch_setup_skips_uv_mode_when_no_relay(monkeypatch):
    class DummyEntry:
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data = {"MBF_PAR_UV_RELAY_GPIO": 0}
        config_entry = DummyEntry()
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    from custom_components.vistapool import switch as switch_module

    monkeypatch.setitem(
        switch_module.SWITCH_DEFINITIONS,
        "MBF_PAR_UV_MODE",
        {
            "switch_type": "uv_mode",
            "function_addr": 0x0427,
        },
    )

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    entities = async_add_entities.call_args[0][0]
    keys = [e._key for e in entities]
    assert "MBF_PAR_UV_MODE" not in keys


@pytest.mark.asyncio
async def test_switch_setup_skips_uv_mode_when_key_missing(monkeypatch):
    class DummyEntry:
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data = {}  # no MBF_PAR_UV_RELAY_GPIO at all
        config_entry = DummyEntry()
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    from custom_components.vistapool import switch as switch_module

    monkeypatch.setitem(
        switch_module.SWITCH_DEFINITIONS,
        "MBF_PAR_UV_MODE",
        {
            "switch_type": "uv_mode",
            "function_addr": 0x0427,
        },
    )

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    entities = async_add_entities.call_args[0][0]
    keys = [e._key for e in entities]
    assert "MBF_PAR_UV_MODE" not in keys


@pytest.mark.asyncio
async def test_switch_setup_skips_uv_mode_when_gpio_out_of_range(monkeypatch):
    class DummyEntry:
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data = {"MBF_PAR_UV_RELAY_GPIO": 255}
        config_entry = DummyEntry()
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    from custom_components.vistapool import switch as switch_module

    monkeypatch.setitem(
        switch_module.SWITCH_DEFINITIONS,
        "MBF_PAR_UV_MODE",
        {
            "switch_type": "uv_mode",
            "function_addr": 0x0427,
        },
    )

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    entities = async_add_entities.call_args[0][0]
    keys = [e._key for e in entities]
    assert "MBF_PAR_UV_MODE" not in keys


@pytest.mark.asyncio
async def test_follow_up_refresh_called_on_turn_on(mock_coordinator):
    """Follow-up refresh is used after turn_on for IO switch types."""
    props = make_props(switch_type="manual_filtration")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "manual", props)
    ent.coordinator.client = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    await ent.async_turn_on()
    mock_coordinator.request_refresh_with_followup.assert_called_once()


@pytest.mark.asyncio
async def test_follow_up_refresh_called_on_turn_off(mock_coordinator):
    """Follow-up refresh is used after turn_off for IO switch types."""
    props = make_props(switch_type="aux", relay_index=1)
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "aux1", props)
    ent.coordinator.client = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    await ent.async_turn_off()
    mock_coordinator.request_refresh_with_followup.assert_called_once()


@pytest.mark.asyncio
async def test_no_follow_up_refresh_for_non_io_switch(mock_coordinator):
    """Non-IO switches use plain refresh without follow-up."""
    props = make_props(switch_type="auto_time_sync")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "sync", props)
    ent.coordinator.set_auto_time_sync = AsyncMock()
    ent.coordinator.async_request_refresh = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    await ent.async_turn_on()
    mock_coordinator.async_request_refresh.assert_awaited_once()
    mock_coordinator.request_refresh_with_followup.assert_not_called()


@pytest.mark.asyncio
async def test_optimistic_update_manual_filtration(mock_coordinator):
    """Optimistic update sets MBF_PAR_FILT_MANUAL_STATE correctly."""
    mock_coordinator.data = {"MBF_PAR_FILT_MANUAL_STATE": 0}
    props = make_props(switch_type="manual_filtration")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "manual", props)
    ent._optimistic_update(True)
    assert mock_coordinator.data["MBF_PAR_FILT_MANUAL_STATE"] == 1
    ent._optimistic_update(False)
    assert mock_coordinator.data["MBF_PAR_FILT_MANUAL_STATE"] == 0


@pytest.mark.asyncio
async def test_optimistic_update_aux(mock_coordinator):
    """Optimistic update sets data[key] for aux switches."""
    mock_coordinator.data = {"aux1": False}
    props = make_props(switch_type="aux", relay_index=1)
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "aux1", props)
    ent._optimistic_update(True)
    assert mock_coordinator.data["aux1"] is True
    ent._optimistic_update(False)
    assert mock_coordinator.data["aux1"] is False


@pytest.mark.asyncio
async def test_optimistic_update_relay_timer(mock_coordinator):
    """Optimistic update sets relay enable value for relay_timer switches."""
    mock_coordinator.data = {"relay_aux1_enable": 4}
    props = make_props(
        switch_type="relay_timer",
        timer_block_addr=0x04AC,
        function_addr=0x04B7,
        function_code=0x0800,
    )
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "aux1", props)
    ent._optimistic_update(True)
    assert mock_coordinator.data["relay_aux1_enable"] == 3
    ent._optimistic_update(False)
    assert mock_coordinator.data["relay_aux1_enable"] == 4


@pytest.mark.asyncio
async def test_optimistic_update_bitmask(mock_coordinator):
    """Optimistic update sets bitmask values correctly."""
    mock_coordinator.data = {"MBF_PAR_HIDRO_COVER_ENABLE": 0}
    props = make_props(
        switch_type="bitmask",
        function_addr=0x042C,
        mask_bit=0x0001,
        data_key="MBF_PAR_HIDRO_COVER_ENABLE",
    )
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "cover", props)
    ent._optimistic_update(True)
    assert mock_coordinator.data["MBF_PAR_HIDRO_COVER_ENABLE"] == 1
    ent._optimistic_update(False)
    assert mock_coordinator.data["MBF_PAR_HIDRO_COVER_ENABLE"] == 0


def test_optimistic_update_noop_when_data_is_none(mock_coordinator):
    """Optimistic update is a no-op when coordinator data is None."""
    mock_coordinator.data = None
    props = make_props(switch_type="manual_filtration")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "manual", props)
    ent._optimistic_update(True)  # Should not raise


@pytest.mark.asyncio
async def test_turn_on_relay_timer_missing_config(mock_coordinator, caplog):
    """relay_timer turn_on logs error and returns when config is missing."""
    props = make_props(switch_type="relay_timer")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "aux1", props)
    ent.coordinator.client = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    await ent.async_turn_on()
    ent.coordinator.client.async_write_register.assert_not_awaited()
    assert "Missing relay_timer config for aux1" in caplog.text


@pytest.mark.asyncio
async def test_turn_off_relay_timer_missing_config(mock_coordinator, caplog):
    """relay_timer turn_off logs error and returns when timer_block_addr is missing."""
    props = make_props(switch_type="relay_timer")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "aux1", props)
    ent.coordinator.client = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    await ent.async_turn_off()
    ent.coordinator.client.async_write_register.assert_not_awaited()
    assert "Missing timer_block_addr for aux1" in caplog.text


@pytest.mark.asyncio
async def test_turn_on_climate_mode_missing_function_addr(mock_coordinator, caplog):
    """climate_mode turn_on logs error when function_addr is missing."""
    props = make_props(switch_type="climate_mode")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "clima", props)
    ent.coordinator.client = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    await ent.async_turn_on()
    ent.coordinator.client.async_write_register.assert_not_awaited()
    assert "Missing function_addr for clima" in caplog.text


@pytest.mark.asyncio
async def test_turn_off_climate_mode_missing_function_addr(mock_coordinator, caplog):
    """climate_mode turn_off logs error when function_addr is missing."""
    props = make_props(switch_type="climate_mode")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "clima", props)
    ent.coordinator.client = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    await ent.async_turn_off()
    ent.coordinator.client.async_write_register.assert_not_awaited()
    assert "Missing function_addr for clima" in caplog.text


@pytest.mark.asyncio
async def test_turn_on_bitmask_missing_config(mock_coordinator, caplog):
    """bitmask turn_on logs error when function_addr/mask_bit is missing."""
    props = make_props(switch_type="bitmask")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "bit", props)
    ent.coordinator.client = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    await ent.async_turn_on()
    ent.coordinator.client.async_write_register.assert_not_awaited()
    assert "Missing bitmask config for bit" in caplog.text


@pytest.mark.asyncio
async def test_turn_off_bitmask_missing_config(mock_coordinator, caplog):
    """bitmask turn_off logs error when function_addr/mask_bit is missing."""
    props = make_props(switch_type="bitmask")
    ent = VistaPoolSwitch(mock_coordinator, "test_entry", "bit", props)
    ent.coordinator.client = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    await ent.async_turn_off()
    ent.coordinator.client.async_write_register.assert_not_awaited()
    assert "Missing bitmask config for bit" in caplog.text
