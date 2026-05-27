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

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from custom_components.vistapool.const import (
    HEATING_SETPOINT_REGISTER,
    INTELLIGENT_SETPOINT_REGISTER,
)
from custom_components.vistapool.number import VistaPoolNumber, async_setup_entry


@pytest.fixture
def mock_coordinator():
    mock = MagicMock()
    mock.data = {}
    mock.device_slug = "vistapool"
    mock.winter_mode = False
    mock.config_entry.entry_id = "test_entry"
    return mock


def make_props(**kwargs):
    d = {}
    d.update(kwargs)
    return d


def test_native_value_default(mock_coordinator):
    props = make_props(register=0x0200, scale=1.0)
    ent = VistaPoolNumber(mock_coordinator, "test_entry", "MBF_PAR_PH1", props)
    mock_coordinator.data = {"MBF_PAR_PH1": 7.22}
    assert ent.native_value == 7.22


def test_native_value_none(mock_coordinator):
    props = make_props(register=0x0200, scale=1.0)
    ent = VistaPoolNumber(mock_coordinator, "test_entry", "MBF_PAR_PH1", props)
    mock_coordinator.data = {}
    ent._attr_native_value = 7.01
    assert ent.native_value == 7.01


def test_suggested_display_precision(mock_coordinator):
    props = make_props()
    ent = VistaPoolNumber(mock_coordinator, "test_entry", "MBF_PAR_HIDRO", props)

    # Percent mode -> precision 0
    mock_coordinator.data = {
        "MBF_PAR_UICFG_MACH_VISUAL_STYLE": 0x4000,  # force percentage bit
        "MBF_PAR_UICFG_MACHINE": 0,
    }
    assert ent.suggested_display_precision == 0

    # g/h mode -> precision 1
    mock_coordinator.data = {
        "MBF_PAR_UICFG_MACH_VISUAL_STYLE": 0x2000,  # force g/h bit
        "MBF_PAR_UICFG_MACHINE": 0,
    }
    assert ent.suggested_display_precision == 1

    ent = VistaPoolNumber(mock_coordinator, "test_entry", "MBF_PAR_HEATING_TEMP", props)
    assert ent.suggested_display_precision == 0
    ent = VistaPoolNumber(mock_coordinator, "test_entry", "MBF_PAR_PH1", props)
    assert ent.suggested_display_precision is None


def test_native_unit_of_measurement_dynamic(mock_coordinator):
    props = make_props(unit="g/h")
    ent = VistaPoolNumber(mock_coordinator, "test_entry", "MBF_PAR_HIDRO", props)

    # Test percent mode with force percentage bit
    mock_coordinator.data = {
        "MBF_PAR_HIDRO_NOM": 100.0,
        "MBF_PAR_UICFG_MACH_VISUAL_STYLE": 0x4000,  # Force percentage
        "MBF_PAR_UICFG_MACHINE": 0,
    }
    assert ent.native_unit_of_measurement == "%"

    # Test g/h mode with force g/h bit
    mock_coordinator.data = {
        "MBF_PAR_HIDRO_NOM": 80.0,
        "MBF_PAR_UICFG_MACH_VISUAL_STYLE": 0x2000,  # Force g/h
        "MBF_PAR_UICFG_MACHINE": 0,
    }
    assert ent.native_unit_of_measurement == "g/h"

    # Test HIDROLIFE machine (should be g/h)
    mock_coordinator.data = {
        "MBF_PAR_HIDRO_NOM": 100.0,
        "MBF_PAR_UICFG_MACH_VISUAL_STYLE": 0x0000,
        "MBF_PAR_UICFG_MACHINE": 1,  # HIDROLIFE
    }
    assert ent.native_unit_of_measurement == "g/h"

    # Test default case (should be %)
    mock_coordinator.data = {
        "MBF_PAR_HIDRO_NOM": 100.0,
        "MBF_PAR_UICFG_MACH_VISUAL_STYLE": 0x0000,
        "MBF_PAR_UICFG_MACHINE": 2,  # AQUASCENIC
    }
    assert ent.native_unit_of_measurement == "%"

    # Test other number entities return their default unit
    ent = VistaPoolNumber(mock_coordinator, "test_entry", "MBF_PAR_PH1", props)
    assert ent.native_unit_of_measurement == "g/h"


def test_native_max_value_dynamic(mock_coordinator):
    props = make_props(max=120.0)
    ent = VistaPoolNumber(mock_coordinator, "test_entry", "MBF_PAR_HIDRO", props)
    mock_coordinator.data = {"MBF_PAR_HIDRO_NOM": 77.0}
    assert ent.native_max_value == 77.0
    ent = VistaPoolNumber(mock_coordinator, "test_entry", "MBF_PAR_PH1", props)
    assert ent.native_max_value == 120.0


def test_native_step_dynamic(mock_coordinator):
    """Test native_step for MBF_PAR_HIDRO is dynamic: 1.0 in % mode, 0.1 in g/h mode."""
    props = make_props(step=1.0)
    ent = VistaPoolNumber(mock_coordinator, "test_entry", "MBF_PAR_HIDRO", props)

    # Percent mode -> step 1.0
    mock_coordinator.data = {
        "MBF_PAR_UICFG_MACH_VISUAL_STYLE": 0x4000,  # force percentage bit
        "MBF_PAR_UICFG_MACHINE": 0,
    }
    assert ent.native_step == 1.0

    # g/h mode -> step 0.1 (matches 1-decimal precision and scale=10.0)
    mock_coordinator.data = {
        "MBF_PAR_UICFG_MACH_VISUAL_STYLE": 0x2000,  # force g/h bit
        "MBF_PAR_UICFG_MACHINE": 0,
    }
    assert ent.native_step == 0.1

    # Other keys return their static step from props
    ent_ph = VistaPoolNumber(
        mock_coordinator, "test_entry", "MBF_PAR_PH1", make_props(step=0.1)
    )
    assert ent_ph.native_step == 0.1


@pytest.mark.asyncio
async def test_async_set_native_value_and_debounce(mock_coordinator):
    props = make_props(register=0x0210, scale=2.0)
    ent = VistaPoolNumber(mock_coordinator, "test_entry", "MBF_PAR_PH1", props)
    ent.coordinator.client = AsyncMock()
    ent.coordinator.async_request_refresh = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    # Patch asyncio.sleep to run immediately
    with patch("custom_components.vistapool.number.asyncio.sleep", AsyncMock()):
        await ent.async_set_native_value(6.5)
        assert ent._pending_write_task is not None
        await ent._pending_write_task
    # Should have written 13 (6.5*2)
    ent.coordinator.client.async_write_register.assert_awaited_with(
        0x0210, 13, apply=True
    )
    ent.coordinator.async_request_refresh.assert_awaited()


@pytest.mark.asyncio
async def test_debounced_write_mirrors_setpoints_from_heating_register(
    mock_coordinator,
):
    """When editing heating setpoint, both HEATING and INTELLIGENT registers must be written."""
    props = make_props(register=HEATING_SETPOINT_REGISTER, scale=1.0)
    ent = VistaPoolNumber(mock_coordinator, "test_entry", "MBF_PAR_HEATING_TEMP", props)
    ent.coordinator.client = AsyncMock()
    ent.coordinator.async_request_refresh = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    with patch("custom_components.vistapool.number.asyncio.sleep", AsyncMock()):
        await ent.async_set_native_value(28)
        assert ent._pending_write_task is not None
        await ent._pending_write_task
    # Expect two ordered writes: first to HEATING, then to INTELLIGENT with apply=True
    ent.coordinator.client.async_write_register.assert_has_awaits(
        [
            call(HEATING_SETPOINT_REGISTER, 28),
            call(INTELLIGENT_SETPOINT_REGISTER, 28, apply=True),
        ]
    )
    ent.coordinator.async_request_refresh.assert_awaited()


@pytest.mark.asyncio
async def test_debounced_write_mirrors_setpoints_from_intelligent_register(
    mock_coordinator,
):
    """When editing intelligent setpoint, both HEATING and INTELLIGENT registers must be written."""
    props = make_props(register=INTELLIGENT_SETPOINT_REGISTER, scale=1.0)
    ent = VistaPoolNumber(
        mock_coordinator, "test_entry", "MBF_PAR_INTELLIGENT_TEMP", props
    )
    ent.coordinator.client = AsyncMock()
    ent.coordinator.async_request_refresh = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    with patch("custom_components.vistapool.number.asyncio.sleep", AsyncMock()):
        await ent.async_set_native_value(26)
        assert ent._pending_write_task is not None
        await ent._pending_write_task
    ent.coordinator.client.async_write_register.assert_has_awaits(
        [
            call(HEATING_SETPOINT_REGISTER, 26),
            call(INTELLIGENT_SETPOINT_REGISTER, 26, apply=True),
        ]
    )
    ent.coordinator.async_request_refresh.assert_awaited()


@pytest.mark.asyncio
async def test_debounced_write_no_client(mock_coordinator):
    props = make_props(register=0x0210, scale=2.0)
    ent = VistaPoolNumber(mock_coordinator, "test_entry", "MBF_PAR_PH1", props)
    ent.coordinator.client = None
    with patch("custom_components.vistapool.number.asyncio.sleep", AsyncMock()):
        await ent._debounced_write()  # Should do nothing, but not crash


@pytest.mark.asyncio
async def test_debounced_write_cancelled_when_winter_mode_enabled_during_delay(
    mock_coordinator, caplog
):
    """_debounced_write is aborted if winter mode is enabled during the debounce delay."""
    props = make_props(register=0x0260, scale=100.0)
    ent = VistaPoolNumber(mock_coordinator, "test_entry", "MBF_PAR_PH1", props)
    ent._pending_value = 7.2
    ent.coordinator.client = AsyncMock()
    ent.coordinator.async_request_refresh = AsyncMock()

    async def enable_winter_mode_during_sleep(_delay):
        """Simulate winter mode being enabled while the debounce timer is running."""
        mock_coordinator.winter_mode = True

    with patch(
        "custom_components.vistapool.number.asyncio.sleep",
        side_effect=enable_winter_mode_during_sleep,
    ):
        with caplog.at_level("WARNING"):
            await ent._debounced_write()

    ent.coordinator.client.async_write_register.assert_not_called()
    assert "debounced write cancelled" in caplog.text


@pytest.mark.asyncio
async def test_async_added_to_hass_sets_value(mock_coordinator):
    props = make_props(register=0x0210, scale=1.0)
    ent = VistaPoolNumber(mock_coordinator, "test_entry", "MBF_PAR_PH1", props)
    client = AsyncMock()
    ent.coordinator.client = client
    client.async_read_all = AsyncMock(return_value={"MBF_PAR_PH1": 7.7})
    ent.async_write_ha_state = MagicMock()
    with patch("custom_components.vistapool.number.asyncio.sleep", AsyncMock()):
        await ent.async_added_to_hass()
    ent.coordinator.data = {
        "MBF_PAR_PH1": 7.7
    }  # Simulate HA assigning coordinator.data
    assert ent.native_value == 7.7


@pytest.mark.asyncio
async def test_async_added_to_hass_no_client(mock_coordinator):
    props = make_props(register=0x0210, scale=1.0)
    ent = VistaPoolNumber(mock_coordinator, "test_entry", "MBF_PAR_PH1", props)
    ent.coordinator.client = None
    ent.async_write_ha_state = MagicMock()
    # Should log error but not crash
    await ent.async_added_to_hass()


@pytest.mark.asyncio
async def test_async_added_to_hass_sets_value_none(mock_coordinator):
    """Test async_added_to_hass sets native_value to None if key not present."""
    props = make_props(register=0x0210, scale=1.0)
    ent = VistaPoolNumber(mock_coordinator, "test_entry", "MBF_PAR_PH1", props)
    client = AsyncMock()
    ent.coordinator.client = client
    # async_read_all returns a dict, but missing the key
    client.async_read_all = AsyncMock(return_value={"OTHER_KEY": 42.0})
    ent.async_write_ha_state = MagicMock()
    with patch("custom_components.vistapool.number.asyncio.sleep", AsyncMock()):
        await ent.async_added_to_hass()
    # _attr_native_value should be None
    assert ent._attr_native_value is None


@pytest.mark.asyncio
async def test_number_async_setup_entry_adds_entities(monkeypatch):
    """Test async_setup_entry adds number entities for valid data."""

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        # Simulate all relays assigned and temperature active
        data = {
            "MBF_PAR_HEATING_GPIO": True,
            "MBF_PAR_TEMPERATURE_ACTIVE": 1,
            "MBF_PAR_PH_ACID_RELAY_GPIO": True,
            "MBF_PAR_PH_BASE_RELAY_GPIO": True,
            "Redox measurement module detected": True,
            "Chlorine measurement module detected": True,
        }
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "vistapool"

    hass = MagicMock()
    entry = DummyEntry()
    entry.runtime_data = DummyCoordinator()
    async_add_entities = MagicMock()

    # Patch NUMBER_DEFINITIONS for this test
    from custom_components.vistapool import number as num_module

    monkeypatch.setitem(
        num_module.NUMBER_DEFINITIONS, "MBF_PAR_HEATING_TEMP", {"register": 0x0201}
    )
    monkeypatch.setitem(
        num_module.NUMBER_DEFINITIONS, "MBF_PAR_PH1", {"register": 0x0202}
    )
    monkeypatch.setitem(
        num_module.NUMBER_DEFINITIONS, "MBF_PAR_PH2", {"register": 0x0203}
    )
    monkeypatch.setitem(
        num_module.NUMBER_DEFINITIONS, "MBF_PAR_RX1", {"register": 0x0204}
    )
    monkeypatch.setitem(
        num_module.NUMBER_DEFINITIONS, "MBF_PAR_CL1", {"register": 0x0205}
    )
    monkeypatch.setitem(num_module.NUMBER_DEFINITIONS, "DUMMY", {"register": 0x0206})

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    entities = async_add_entities.call_args[0][0]
    assert any(isinstance(e, VistaPoolNumber) for e in entities)
    # Should include all keys above
    keys = [e._key for e in entities]
    for k in (
        "MBF_PAR_HEATING_TEMP",
        "MBF_PAR_PH1",
        "MBF_PAR_PH2",
        "MBF_PAR_RX1",
        "MBF_PAR_CL1",
        "DUMMY",
    ):
        assert k in keys


@pytest.mark.asyncio
async def test_number_setup_skips_smart_when_no_temp(monkeypatch):
    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data = {
            "MBF_PAR_TEMPERATURE_ACTIVE": 0,
            "MBF_PAR_HEATING_GPIO": True,
        }
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "vistapool"

    hass = MagicMock()
    entry = DummyEntry()
    entry.runtime_data = DummyCoordinator()
    async_add_entities = MagicMock()

    from custom_components.vistapool import number as num_module

    monkeypatch.setitem(
        num_module.NUMBER_DEFINITIONS, "MBF_PAR_SMART_TEMP_HIGH", {"register": 0x0418}
    )
    monkeypatch.setitem(
        num_module.NUMBER_DEFINITIONS, "MBF_PAR_SMART_TEMP_LOW", {"register": 0x0419}
    )

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    entities = async_add_entities.call_args[0][0]
    keys = [e._key for e in entities]
    assert "MBF_PAR_SMART_TEMP_HIGH" not in keys
    assert "MBF_PAR_SMART_TEMP_LOW" not in keys


@pytest.mark.asyncio
async def test_number_async_setup_entry_skips_unassigned(monkeypatch):
    """Test async_setup_entry skips number entities if required relay is missing."""

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data = {
            "MBF_PAR_HEATING_GPIO": False,
            "MBF_PAR_PH_ACID_RELAY_GPIO": False,
            "MBF_PAR_PH_BASE_RELAY_GPIO": False,
            "Redox measurement module detected": False,
            "Chlorine measurement module detected": False,
        }
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "vistapool"

    hass = MagicMock()
    entry = DummyEntry()
    entry.runtime_data = DummyCoordinator()
    async_add_entities = MagicMock()

    from custom_components.vistapool import number as num_module

    monkeypatch.setitem(
        num_module.NUMBER_DEFINITIONS, "MBF_PAR_HEATING_TEMP", {"register": 0x0201}
    )
    monkeypatch.setitem(
        num_module.NUMBER_DEFINITIONS, "MBF_PAR_PH1", {"register": 0x0202}
    )
    monkeypatch.setitem(
        num_module.NUMBER_DEFINITIONS, "MBF_PAR_PH2", {"register": 0x0203}
    )
    monkeypatch.setitem(
        num_module.NUMBER_DEFINITIONS, "MBF_PAR_RX1", {"register": 0x0204}
    )
    monkeypatch.setitem(
        num_module.NUMBER_DEFINITIONS, "MBF_PAR_CL1", {"register": 0x0205}
    )

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    entities = async_add_entities.call_args[0][0]
    keys = [e._key for e in entities]
    # Should not include any filtered-out keys
    assert "MBF_PAR_HEATING_TEMP" not in keys
    assert "MBF_PAR_PH1" not in keys
    assert "MBF_PAR_PH2" not in keys
    assert "MBF_PAR_RX1" not in keys
    assert "MBF_PAR_CL1" not in keys


@pytest.mark.asyncio
async def test_number_setup_skips_cover_without_cover_sensor(monkeypatch):
    """Cover reduction numbers are skipped when cover sensor option is not enabled."""

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {}  # use_cover_sensor defaults to False

    class DummyCoordinator:
        data = {
            "Hydrolysis module detected": True,
        }
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "vistapool"

    hass = MagicMock()
    entry = DummyEntry()
    entry.runtime_data = DummyCoordinator()
    async_add_entities = MagicMock()

    from custom_components.vistapool import number as num_module

    monkeypatch.setitem(
        num_module.NUMBER_DEFINITIONS,
        "MBF_PAR_HIDRO_COVER_REDUCTION",
        {"register": 0x042D, "option": "use_cover_sensor"},
    )
    monkeypatch.setitem(
        num_module.NUMBER_DEFINITIONS,
        "MBF_PAR_HIDRO_SHUTDOWN_TEMPERATURE",
        {"register": 0x042D, "option": "use_cover_sensor"},
    )

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    keys = [e._key for e in async_add_entities.call_args[0][0]]
    assert "MBF_PAR_HIDRO_COVER_REDUCTION" not in keys
    assert "MBF_PAR_HIDRO_SHUTDOWN_TEMPERATURE" not in keys


@pytest.mark.asyncio
async def test_number_setup_creates_cover_with_cover_sensor(monkeypatch):
    """Cover reduction numbers are created when cover sensor option is enabled."""

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {"use_cover_sensor": True}  # cover sensor option enabled

    class DummyCoordinator:
        data = {
            "Hydrolysis module detected": True,
            "MBF_PAR_TEMPERATURE_ACTIVE": 1,
        }
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "vistapool"

    hass = MagicMock()
    entry = DummyEntry()
    entry.runtime_data = DummyCoordinator()
    async_add_entities = MagicMock()

    from custom_components.vistapool import number as num_module

    monkeypatch.setitem(
        num_module.NUMBER_DEFINITIONS,
        "MBF_PAR_HIDRO_COVER_REDUCTION",
        {"register": 0x042D, "option": "use_cover_sensor"},
    )
    monkeypatch.setitem(
        num_module.NUMBER_DEFINITIONS,
        "MBF_PAR_HIDRO_SHUTDOWN_TEMPERATURE",
        {"register": 0x042D, "option": "use_cover_sensor"},
    )

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    keys = [e._key for e in async_add_entities.call_args[0][0]]
    assert "MBF_PAR_HIDRO_COVER_REDUCTION" in keys
    assert "MBF_PAR_HIDRO_SHUTDOWN_TEMPERATURE" in keys


@pytest.mark.asyncio
async def test_number_setup_skips_cover_without_hydro_module(monkeypatch):
    """Cover reduction numbers are skipped when hydrolysis module is not present."""

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {"use_cover_sensor": True}

    class DummyCoordinator:
        data = {"MBF_PAR_TEMPERATURE_ACTIVE": 1}  # Hydrolysis module not detected
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "vistapool"

    hass = MagicMock()
    entry = DummyEntry()
    entry.runtime_data = DummyCoordinator()
    async_add_entities = MagicMock()

    from custom_components.vistapool import number as num_module

    monkeypatch.setitem(
        num_module.NUMBER_DEFINITIONS,
        "MBF_PAR_HIDRO_COVER_REDUCTION",
        {"register": 0x042D, "option": "use_cover_sensor"},
    )
    monkeypatch.setitem(
        num_module.NUMBER_DEFINITIONS,
        "MBF_PAR_HIDRO_SHUTDOWN_TEMPERATURE",
        {"register": 0x042D, "option": "use_cover_sensor"},
    )

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    keys = [e._key for e in async_add_entities.call_args[0][0]]
    assert "MBF_PAR_HIDRO_COVER_REDUCTION" not in keys
    assert "MBF_PAR_HIDRO_SHUTDOWN_TEMPERATURE" not in keys


@pytest.mark.asyncio
async def test_number_setup_skips_temp_shutdown_without_temp_sensor(monkeypatch):
    """Shutdown temperature number is skipped when temperature sensor is inactive."""

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {"use_cover_sensor": True}

    class DummyCoordinator:
        data = {"Hydrolysis module detected": True}  # hydro present, but no temp sensor
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "vistapool"

    hass = MagicMock()
    entry = DummyEntry()
    entry.runtime_data = DummyCoordinator()
    async_add_entities = MagicMock()

    from custom_components.vistapool import number as num_module

    monkeypatch.setitem(
        num_module.NUMBER_DEFINITIONS,
        "MBF_PAR_HIDRO_COVER_REDUCTION",
        {"register": 0x042D, "option": "use_cover_sensor"},
    )
    monkeypatch.setitem(
        num_module.NUMBER_DEFINITIONS,
        "MBF_PAR_HIDRO_SHUTDOWN_TEMPERATURE",
        {"register": 0x042D, "option": "use_cover_sensor"},
    )

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    keys = [e._key for e in async_add_entities.call_args[0][0]]
    assert "MBF_PAR_HIDRO_COVER_REDUCTION" in keys  # cover reduction still shown
    assert "MBF_PAR_HIDRO_SHUTDOWN_TEMPERATURE" not in keys


# --- Bitmask number tests ---


def test_native_value_bitmask_lsb(mock_coordinator):
    """native_value extracts the lower byte (cover reduction %) via mask=0x00FF, shift=0."""
    props = make_props(
        register=0x042D,
        data_key="MBF_PAR_HIDRO_COVER_REDUCTION",
        mask=0x00FF,
        shift=0,
        scale=1.0,
    )
    ent = VistaPoolNumber(
        mock_coordinator, "test_entry", "MBF_PAR_HIDRO_COVER_REDUCTION", props
    )
    # Register value: 0x1E28 = upper byte 0x1E (30°C), lower byte 0x28 (40%)
    mock_coordinator.data = {"MBF_PAR_HIDRO_COVER_REDUCTION": 0x1E28}
    assert ent.native_value == 40.0


def test_native_value_bitmask_msb(mock_coordinator):
    """native_value extracts the upper byte (shutdown temp) via mask=0xFF00, shift=8."""
    props = make_props(
        register=0x042D,
        data_key="MBF_PAR_HIDRO_COVER_REDUCTION",
        mask=0xFF00,
        shift=8,
        scale=1.0,
    )
    ent = VistaPoolNumber(
        mock_coordinator, "test_entry", "MBF_PAR_HIDRO_SHUTDOWN_TEMPERATURE", props
    )
    # Register value: 0x1E28 = upper byte 0x1E = 30
    mock_coordinator.data = {"MBF_PAR_HIDRO_COVER_REDUCTION": 0x1E28}
    assert ent.native_value == 30.0


@pytest.mark.asyncio
async def test_async_added_to_hass_bitmask(mock_coordinator):
    """async_added_to_hass correctly applies mask/shift to the cached coordinator value."""
    props = make_props(
        register=0x042D,
        data_key="MBF_PAR_HIDRO_COVER_REDUCTION",
        mask=0x00FF,
        shift=0,
        scale=1.0,
    )
    ent = VistaPoolNumber(
        mock_coordinator, "test_entry", "MBF_PAR_HIDRO_COVER_REDUCTION", props
    )
    mock_coordinator.data = {"MBF_PAR_HIDRO_COVER_REDUCTION": 0x1E28}
    mock_coordinator.client = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    with patch("custom_components.vistapool.number.asyncio.sleep", AsyncMock()):
        await ent.async_added_to_hass()
    assert ent._attr_native_value == 40


@pytest.mark.asyncio
async def test_debounced_write_bitmask_lsb(mock_coordinator):
    """_debounced_write performs RMW correctly for the lower-byte mask."""
    props = make_props(
        register=0x042D,
        data_key="MBF_PAR_HIDRO_COVER_REDUCTION",
        mask=0x00FF,
        shift=0,
        scale=1.0,
    )
    ent = VistaPoolNumber(
        mock_coordinator, "test_entry", "MBF_PAR_HIDRO_COVER_REDUCTION", props
    )
    # Current register value has 0x1E in upper byte (30°C shutdown)
    mock_coordinator.data = {"MBF_PAR_HIDRO_COVER_REDUCTION": 0x1E28}
    ent.coordinator.client = AsyncMock()
    ent.coordinator.async_request_refresh = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    ent._pending_value = 50  # set cover reduction to 50%
    with patch("custom_components.vistapool.number.asyncio.sleep", AsyncMock()):
        await ent._debounced_write()
    # Expected: (0x1E28 & ~0x00FF) | (50 & 0x00FF) = 0x1E00 | 0x0032 = 0x1E32
    ent.coordinator.client.async_write_register.assert_awaited_with(
        0x042D, 0x1E32, apply=True
    )


@pytest.mark.asyncio
async def test_debounced_write_bitmask_msb(mock_coordinator):
    """_debounced_write performs RMW correctly for the upper-byte mask."""
    props = make_props(
        register=0x042D,
        data_key="MBF_PAR_HIDRO_COVER_REDUCTION",
        mask=0xFF00,
        shift=8,
        scale=1.0,
    )
    ent = VistaPoolNumber(
        mock_coordinator, "test_entry", "MBF_PAR_HIDRO_SHUTDOWN_TEMPERATURE", props
    )
    # Current register value has 0x28 = 40% in lower byte
    mock_coordinator.data = {"MBF_PAR_HIDRO_COVER_REDUCTION": 0x1E28}
    ent.coordinator.client = AsyncMock()
    ent.coordinator.async_request_refresh = AsyncMock()
    ent.async_write_ha_state = MagicMock()
    ent._pending_value = 25  # set shutdown temperature to 25°C
    with patch("custom_components.vistapool.number.asyncio.sleep", AsyncMock()):
        await ent._debounced_write()
    # Expected: (0x1E28 & ~0xFF00) | ((25 << 8) & 0xFF00) = 0x0028 | 0x1900 = 0x1928
    ent.coordinator.client.async_write_register.assert_awaited_with(
        0x042D, 0x1928, apply=True
    )


@pytest.mark.asyncio
async def test_set_native_value_blocked_during_winter_mode(mock_coordinator, caplog):
    """async_set_native_value is ignored when winter mode is active."""
    mock_coordinator.winter_mode = True
    props = make_props(register=0x0260, min_value=6.8, max_value=8.2, step=0.1)
    ent = VistaPoolNumber(mock_coordinator, "test_entry", "MBF_PAR_PH1", props)
    ent.async_write_ha_state = MagicMock()
    with caplog.at_level("WARNING"):
        await ent.async_set_native_value(7.2)
    assert "Winter mode is active" in caplog.text
    # No debounced write task should have been created
    assert ent._pending_value is None


def test_available_false_during_winter_mode(mock_coordinator):
    """VistaPoolNumber is unavailable when winter mode is active."""
    mock_coordinator.winter_mode = True
    props = make_props(register=0x0260, min_value=6.8, max_value=8.2, step=0.1)
    ent = VistaPoolNumber(mock_coordinator, "test_entry", "MBF_PAR_PH1", props)
    assert ent.available is False


@pytest.mark.asyncio
async def test_async_setup_entry_no_data(caplog):
    """Test async_setup_entry logs warning and adds no entities when data is None."""

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"

    class DummyCoordinator:
        data = None
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "vistapool"

    hass = MagicMock()
    entry = DummyEntry()
    entry.runtime_data = DummyCoordinator()
    async_add_entities = MagicMock()

    with caplog.at_level("WARNING"):
        await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
        assert "No data from Modbus" in caplog.text
    async_add_entities.assert_not_called()


@pytest.mark.asyncio
async def test_async_setup_entry_skips_hidro_without_hydrolysis(caplog):
    """Test that MBF_PAR_HIDRO number is skipped when Hydrolysis module detected is False."""
    from custom_components.vistapool.number import async_setup_entry

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data = {
            "Hydrolysis module detected": False,  # No hydrolysis module
        }
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "vistapool"

    hass = MagicMock()
    entry = DummyEntry()
    entry.runtime_data = DummyCoordinator()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]

    entities = async_add_entities.call_args[0][0]
    keys = [e._key for e in entities]
    assert "MBF_PAR_HIDRO" not in keys
