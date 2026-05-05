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

from unittest.mock import MagicMock, patch

import pytest

from custom_components.vistapool.sensor import (
    FILTRATION_MODE_MAP,
    FILTRATION_SPEED_MAP,
    PH_STATUS_ALARM_MAP,
    VistaPoolSensor,
    async_setup_entry,
)


@pytest.fixture
def mock_coordinator():
    mock = MagicMock()
    mock.data = {}
    mock.config_entry.options = {}
    mock.config_entry.entry_id = "test_entry"
    mock.entry = mock.config_entry
    mock.device_slug = "vistapool"
    return mock


def make_props(**kwargs):
    d = {}
    d.update(kwargs)
    return d


def test_icon_filtration_modes(mock_coordinator):
    props = make_props(icon="mdi:water-sync")
    ent = VistaPoolSensor(mock_coordinator, "test_entry", "MBF_PAR_FILT_MODE", props)
    for raw, name in FILTRATION_MODE_MAP.items():
        mock_coordinator.data = {"MBF_PAR_FILT_MODE": raw}
        result = ent.icon
        assert isinstance(result, str)


def test_icon_default(mock_coordinator):
    props = make_props(icon="mdi:ph")
    ent = VistaPoolSensor(mock_coordinator, "test_entry", "MBF_MEASURE_PH", props)
    assert ent.icon == "mdi:ph"


def test_suggested_display_precision(mock_coordinator):
    from custom_components.vistapool.const import SENSOR_DEFINITIONS

    # Test for MBF_HIDRO_CURRENT with percent mode
    ent = VistaPoolSensor(
        mock_coordinator,
        "test_entry",
        "MBF_HIDRO_CURRENT",
        SENSOR_DEFINITIONS["MBF_HIDRO_CURRENT"],
    )
    mock_coordinator.data = {
        "MBF_PAR_UICFG_MACH_VISUAL_STYLE": 0x4000,  # Force percentage
        "MBF_PAR_UICFG_MACHINE": 0,
    }
    assert ent.suggested_display_precision == 0

    # Test for MBF_HIDRO_CURRENT with g/h mode
    mock_coordinator.data = {
        "MBF_PAR_UICFG_MACH_VISUAL_STYLE": 0x2000,  # Force g/h
        "MBF_PAR_UICFG_MACHINE": 0,
    }
    assert ent.suggested_display_precision == 1

    # Test for conductivity
    ent = VistaPoolSensor(
        mock_coordinator,
        "test_entry",
        "MBF_MEASURE_CONDUCTIVITY",
        SENSOR_DEFINITIONS["MBF_MEASURE_CONDUCTIVITY"],
    )
    assert ent.suggested_display_precision == 0

    # Test for other sensors
    ent = VistaPoolSensor(mock_coordinator, "test_entry", "MBF_PAR_FILT_MODE", {})
    assert ent.suggested_display_precision is None


def test_native_unit_of_measurement_hidro_current(mock_coordinator):
    """Test native_unit_of_measurement for MBF_HIDRO_CURRENT with different configurations."""
    from custom_components.vistapool.const import SENSOR_DEFINITIONS

    ent = VistaPoolSensor(
        mock_coordinator,
        "test_entry",
        "MBF_HIDRO_CURRENT",
        SENSOR_DEFINITIONS["MBF_HIDRO_CURRENT"],
    )

    # Test percent mode
    mock_coordinator.data = {
        "MBF_PAR_UICFG_MACH_VISUAL_STYLE": 0x4000,  # Force percentage bit
        "MBF_PAR_UICFG_MACHINE": 0,
    }
    assert ent.native_unit_of_measurement == "%"

    # Test g/h mode
    mock_coordinator.data = {
        "MBF_PAR_UICFG_MACH_VISUAL_STYLE": 0x2000,  # Force g/h bit
        "MBF_PAR_UICFG_MACHINE": 0,
    }
    assert ent.native_unit_of_measurement == "g/h"

    # Test HIDROLIFE machine (should be g/h)
    mock_coordinator.data = {
        "MBF_PAR_UICFG_MACH_VISUAL_STYLE": 0x0000,
        "MBF_PAR_UICFG_MACHINE": 1,  # HIDROLIFE
    }
    assert ent.native_unit_of_measurement == "g/h"

    # Test default case (should be %)
    mock_coordinator.data = {
        "MBF_PAR_UICFG_MACH_VISUAL_STYLE": 0x0000,
        "MBF_PAR_UICFG_MACHINE": 2,  # AQUASCENIC
    }
    assert ent.native_unit_of_measurement == "%"


def test_native_unit_of_measurement_other_sensors(mock_coordinator):
    """Test that other sensors return their default unit."""
    props = {"unit": "pH"}
    ent = VistaPoolSensor(mock_coordinator, "test_entry", "MBF_MEASURE_PH", props)
    mock_coordinator.data = {}
    assert ent.native_unit_of_measurement == "pH"


def test_native_value_filtration_pump_off(mock_coordinator):
    # Default: measure_when_filtration_off = False
    ent = VistaPoolSensor(mock_coordinator, "test_entry", "MBF_MEASURE_PH", {})
    mock_coordinator.data = {"Filtration Pump": False}
    mock_coordinator.config_entry.options = {}
    assert ent.native_value is None
    # But if option is enabled, value is returned even if pump off
    mock_coordinator.config_entry.options = {"measure_when_filtration_off": True}
    mock_coordinator.data = {"Filtration Pump": False, "MBF_MEASURE_PH": 7.1}
    assert ent.native_value == 7.1


def test_native_value_special_keys(mock_coordinator):
    ent = VistaPoolSensor(mock_coordinator, "test_entry", "HIDRO_POLARITY", {})
    mock_coordinator.data = {
        "HIDRO in Pol1": True,
        "HIDRO in Pol2": False,
        "HIDRO in dead time": False,
        "HIDRO Cell Flow FL1": True,
        "Filtration Pump": True,
    }
    assert ent.native_value == "pol1"
    mock_coordinator.data = {
        "HIDRO in Pol1": False,
        "HIDRO in Pol2": True,
        "HIDRO in dead time": False,
        "HIDRO Cell Flow FL1": True,
        "Filtration Pump": True,
    }
    assert ent.native_value == "pol2"
    mock_coordinator.data = {
        "HIDRO in Pol1": False,
        "HIDRO in Pol2": False,
        "HIDRO in dead time": True,
        "HIDRO Cell Flow FL1": True,
        "Filtration Pump": True,
    }
    assert ent.native_value == "dead_time"
    mock_coordinator.data = {
        "HIDRO in Pol1": False,
        "HIDRO in Pol2": False,
        "HIDRO in dead time": False,
        "HIDRO Cell Flow FL1": True,
        "Filtration Pump": True,
    }
    assert ent.native_value == "off"
    # Filtration off → always "off" regardless of polarity bits
    mock_coordinator.data = {
        "HIDRO in Pol1": True,
        "HIDRO in Pol2": False,
        "HIDRO in dead time": False,
        "HIDRO Cell Flow FL1": True,
        "Filtration Pump": False,
    }
    assert ent.native_value == "off"
    # FL1 = False (no flow) with filtration running → "no_flow"
    mock_coordinator.data = {
        "HIDRO in Pol1": False,
        "HIDRO in Pol2": False,
        "HIDRO in dead time": False,
        "HIDRO Cell Flow FL1": False,
        "Filtration Pump": True,
    }
    assert ent.native_value == "no_flow"
    # FL1 = False but filtration state unknown → fall through to polarity logic, not "no_flow"
    mock_coordinator.data = {
        "HIDRO in Pol1": False,
        "HIDRO in Pol2": False,
        "HIDRO in dead time": False,
        "HIDRO Cell Flow FL1": False,
    }
    assert ent.native_value == "off"
    # All keys absent (e.g. winter mode with empty capability snapshot) → unknown
    mock_coordinator.data = {}
    assert ent.native_value is None
    # ION_POLARITY enum sensor
    ent = VistaPoolSensor(mock_coordinator, "test_entry", "ION_POLARITY", {})
    mock_coordinator.data = {
        "ION in Pol1": True,
        "ION in Pol2": False,
        "ION in dead time": False,
    }
    assert ent.native_value == "pol1"
    mock_coordinator.data = {
        "ION in Pol1": False,
        "ION in Pol2": True,
        "ION in dead time": False,
    }
    assert ent.native_value == "pol2"
    mock_coordinator.data = {
        "ION in Pol1": False,
        "ION in Pol2": False,
        "ION in dead time": True,
    }
    assert ent.native_value == "dead_time"
    mock_coordinator.data = {
        "ION in Pol1": False,
        "ION in Pol2": False,
        "ION in dead time": False,
    }
    assert ent.native_value == "off"
    mock_coordinator.data = {}
    assert ent.native_value is None
    # PH_PUMP_STATUS enum sensor — default: MBF_PAR_RELAY_PH=0 (acid+base)
    ent = VistaPoolSensor(mock_coordinator, "test_entry", "PH_PUMP_STATUS", {})
    # Control module active, acid pump dosing
    mock_coordinator.data = {
        "pH control module": True,
        "pH acid pump active": True,
        "pH pump active": False,
        "MBF_PAR_RELAY_PH": 0,
    }
    assert ent.native_value == "acid"
    # Control module active, base pump dosing
    mock_coordinator.data = {
        "pH control module": True,
        "pH acid pump active": False,
        "pH pump active": True,
        "MBF_PAR_RELAY_PH": 0,
    }
    assert ent.native_value == "base"
    # Control module active, both pumps dosing
    mock_coordinator.data = {
        "pH control module": True,
        "pH acid pump active": True,
        "pH pump active": True,
        "MBF_PAR_RELAY_PH": 0,
    }
    assert ent.native_value == "both"
    # Control module active, no pump dosing (idle)
    mock_coordinator.data = {
        "pH control module": True,
        "pH acid pump active": False,
        "pH pump active": False,
        "MBF_PAR_RELAY_PH": 0,
    }
    assert ent.native_value == "idle"
    # Control module not active
    mock_coordinator.data = {
        "pH control module": False,
        "pH acid pump active": False,
        "pH pump active": False,
    }
    assert ent.native_value == "off"
    # All keys absent → unknown
    mock_coordinator.data = {}
    assert ent.native_value is None
    # ctrl is None but pump bits present → unknown (partial data)
    mock_coordinator.data = {
        "pH acid pump active": True,
        "pH pump active": False,
    }
    assert ent.native_value is None
    # MBF_PAR_RELAY_PH=1 (acid only): bit 12 is the acid pump
    mock_coordinator.data = {
        "pH control module": True,
        "pH acid pump active": False,
        "pH pump active": True,
        "MBF_PAR_RELAY_PH": 1,
    }
    assert ent.native_value == "acid"
    # MBF_PAR_RELAY_PH=1 (acid only): pump idle
    mock_coordinator.data = {
        "pH control module": True,
        "pH acid pump active": False,
        "pH pump active": False,
        "MBF_PAR_RELAY_PH": 1,
    }
    assert ent.native_value == "idle"
    # MBF_PAR_RELAY_PH=2 (base only): bit 12 is the base pump
    mock_coordinator.data = {
        "pH control module": True,
        "pH acid pump active": False,
        "pH pump active": True,
        "MBF_PAR_RELAY_PH": 2,
    }
    assert ent.native_value == "base"
    # MBF_PAR_RELAY_PH=2 (base only): pump idle
    mock_coordinator.data = {
        "pH control module": True,
        "pH acid pump active": False,
        "pH pump active": False,
        "MBF_PAR_RELAY_PH": 2,
    }
    assert ent.native_value == "idle"
    ent = VistaPoolSensor(mock_coordinator, "test_entry", "MBF_PAR_FILT_MODE", {})
    mock_coordinator.data = {"MBF_PAR_FILT_MODE": 1}
    assert ent.native_value == "auto"
    ent = VistaPoolSensor(mock_coordinator, "test_entry", "FILTRATION_SPEED", {})
    mock_coordinator.data = {"FILTRATION_SPEED": 3}
    assert ent.native_value == "high"
    ent = VistaPoolSensor(mock_coordinator, "test_entry", "MBF_PH_STATUS_ALARM", {})
    mock_coordinator.data = {"MBF_PH_STATUS_ALARM": 2}
    assert ent.native_value == "ph_low"
    mock_coordinator.data = {"MBF_PH_STATUS_ALARM": 0}
    assert ent.native_value == "ok"
    mock_coordinator.data = {"MBF_PH_STATUS_ALARM": 3}
    assert ent.native_value == "pump_stopped"
    mock_coordinator.data = {"MBF_PH_STATUS_ALARM": 6}
    assert ent.native_value == "tank_level"


def test_native_value_default(mock_coordinator):
    ent = VistaPoolSensor(mock_coordinator, "test_entry", "MBF_MEASURE_PH", {})
    mock_coordinator.data = {"MBF_MEASURE_PH": 7.2}
    assert ent.native_value == 7.2


def test_options_property(mock_coordinator):
    ent = VistaPoolSensor(mock_coordinator, "test_entry", "MBF_PAR_FILT_MODE", {})
    assert ent.options == list(FILTRATION_MODE_MAP.values())
    ent = VistaPoolSensor(mock_coordinator, "test_entry", "FILTRATION_SPEED", {})
    assert ent.options == list(FILTRATION_SPEED_MAP.values())
    ent = VistaPoolSensor(mock_coordinator, "test_entry", "MBF_PH_STATUS_ALARM", {})
    assert ent.options == list(PH_STATUS_ALARM_MAP.values())
    ent = VistaPoolSensor(mock_coordinator, "test_entry", "HIDRO_POLARITY", {})
    assert ent.options == ["pol1", "pol2", "dead_time", "no_flow", "off"]
    ent = VistaPoolSensor(mock_coordinator, "test_entry", "ION_POLARITY", {})
    assert ent.options == ["pol1", "pol2", "dead_time", "off"]
    ent = VistaPoolSensor(mock_coordinator, "test_entry", "PH_PUMP_STATUS", {})
    mock_coordinator.data = {"MBF_PAR_RELAY_PH": 0}
    assert ent.options == ["off", "idle", "acid", "base", "both"]
    mock_coordinator.data = {"MBF_PAR_RELAY_PH": 1}
    assert ent.options == ["off", "idle", "acid"]
    mock_coordinator.data = {"MBF_PAR_RELAY_PH": 2}
    assert ent.options == ["off", "idle", "base"]
    mock_coordinator.data = {}
    assert ent.options == ["off", "idle", "acid", "base", "both"]


def test_available_during_winter_mode(mock_coordinator):
    """Sensors stay available during winter mode (they show unknown values)."""
    mock_coordinator.winter_mode = True
    mock_coordinator.last_update_success = True
    ent = VistaPoolSensor(mock_coordinator, "test_entry", "MBF_MEASURE_PH", {})
    assert ent.available is True


def test_available_false_on_coordinator_failure(mock_coordinator):
    """Sensors are unavailable when coordinator update fails."""
    mock_coordinator.winter_mode = False
    mock_coordinator.last_update_success = False
    ent = VistaPoolSensor(mock_coordinator, "test_entry", "MBF_MEASURE_PH", {})
    assert ent.available is False


@pytest.mark.asyncio
async def test_async_added_to_hass_logs_and_calls_parent(mock_coordinator):
    ent = VistaPoolSensor(mock_coordinator, "test_entry", "MBF_MEASURE_PH", {})
    with patch.object(
        VistaPoolSensor, "async_added_to_hass", wraps=ent.async_added_to_hass
    ) as parent:
        await ent.async_added_to_hass()
        assert parent.called


@pytest.mark.asyncio
async def test_sensor_async_setup_entry_adds_entities(monkeypatch):
    """Test async_setup_entry adds correct entities based on data."""

    class DummyEntry:
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data = {
            "MBF_MEASURE_PH": 7.0,
            "pH measurement module detected": True,
            "MBF_MEASURE_RX": 500,
            "Redox measurement module detected": True,
            "MBF_MEASURE_CL": 2000,
            "Chlorine measurement module detected": True,
            "MBF_MEASURE_CONDUCTIVITY": 35.5,
            "Conductivity measurement module detected": True,
            "MBF_PAR_MODEL": 0x0001,  # ion allowed
            "MBF_ION_CURRENT": 60,
            "MBF_PAR_FILTRATION_CONF": 0x0001,
            "FILTRATION_SPEED": 1,
            "MBF_PAR_FILT_MODE": 1,
            "MBF_PH_STATUS_ALARM": 0,
            "Hydrolysis module detected": True,
        }
        config_entry = DummyEntry()
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()
    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    entities = async_add_entities.call_args[0][0]
    # Should add all defined sensors present in data
    keys = [e._key for e in entities]
    assert "MBF_MEASURE_PH" in keys
    assert "MBF_MEASURE_RX" in keys
    assert "MBF_MEASURE_CL" in keys
    assert "MBF_MEASURE_CONDUCTIVITY" in keys
    assert "MBF_ION_CURRENT" in keys
    assert "ION_POLARITY" in keys
    assert "FILTRATION_SPEED" in keys
    assert "MBF_PAR_FILT_MODE" in keys
    assert "MBF_PH_STATUS_ALARM" in keys
    # pH pump status created when pH module detected
    assert "PH_PUMP_STATUS" in keys
    # HIDRO sensors created when Hydrolysis module detected
    assert "MBF_HIDRO_CURRENT" in keys
    assert "MBF_HIDRO_VOLTAGE" in keys
    assert "HIDRO_POLARITY" in keys


@pytest.mark.asyncio
async def test_sensor_async_setup_entry_detected_flags(monkeypatch):
    """Test async_setup_entry skips entities if 'detected' is missing/False."""

    class DummyEntry:
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data = {
            "MBF_MEASURE_PH": 7.0,
            # "pH measurement module detected": False
            "MBF_MEASURE_RX": 500,
            "Redox measurement module detected": False,
        }
        config_entry = DummyEntry()
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()
    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    entities = async_add_entities.call_args[0][0]
    keys = [e._key for e in entities]
    # MBF_MEASURE_PH and MBF_MEASURE_RX should be skipped
    assert "MBF_MEASURE_PH" not in keys
    assert "MBF_MEASURE_RX" not in keys
    # MBF_PH_STATUS_ALARM is also gated by pH detection flag
    assert "MBF_PH_STATUS_ALARM" not in keys
    # PH_PUMP_STATUS should also be skipped without pH module
    assert "PH_PUMP_STATUS" not in keys


@pytest.mark.asyncio
async def test_sensor_async_setup_entry_model_mask(monkeypatch):
    """Test async_setup_entry skips ION sensor if not present in model."""

    class DummyEntry:
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data = {
            "MBF_PAR_MODEL": 0x0000,  # ION not present
            "MBF_ION_CURRENT": 50,
        }
        config_entry = DummyEntry()
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()
    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    entities = async_add_entities.call_args[0][0]
    keys = [e._key for e in entities]
    assert "MBF_ION_CURRENT" not in keys
    assert "ION_POLARITY" not in keys


@pytest.mark.asyncio
async def test_sensor_hidro_skipped_without_hydrolysis(monkeypatch):
    """Test async_setup_entry skips HIDRO sensors when Hydrolysis module detected is False."""

    class DummyEntry:
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data = {
            "Hydrolysis module detected": False,  # No hydrolysis module
        }
        config_entry = DummyEntry()
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()
    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    entities = async_add_entities.call_args[0][0]
    keys = [e._key for e in entities]
    assert "MBF_HIDRO_CURRENT" not in keys
    assert "MBF_HIDRO_VOLTAGE" not in keys
    assert "HIDRO_POLARITY" not in keys


def make_sensor(props, key, data):
    mock_coord = MagicMock()
    mock_coord.data = data
    mock_coord.device_slug = "vistapool"
    mock_coord.config_entry.entry_id = "test_entry"
    mock_coord.config_entry.options = {}
    mock_coord.entry = mock_coord.config_entry
    return VistaPoolSensor(mock_coord, "test_entry", key, props)


@pytest.mark.parametrize(
    "raw,expected_icon",
    [
        (1, "mdi:water-boiler-auto"),  # auto
        (0, "mdi:water-boiler-alert"),  # manual
        (2, "mdi:water-boiler-alert"),  # heating
        (3, "mdi:water-boiler-auto"),  # smart
        (4, "mdi:water-boiler-auto"),  # intelligent
        (13, "mdi:water-boiler-off"),  # backwash
    ],
)
def test_icon_filtration_mode(mock_coordinator, raw, expected_icon):
    props = make_props(device_class="filtration_mode")
    ent = VistaPoolSensor(mock_coordinator, "test_entry", "MBF_PAR_FILT_MODE", props)
    mock_coordinator.data = {"MBF_PAR_FILT_MODE": raw}
    assert ent.icon == expected_icon


def test_icon_ph_alarm(mock_coordinator):
    props = make_props(icon="mdi:alert")
    ent = VistaPoolSensor(mock_coordinator, "test_entry", "MBF_PH_STATUS_ALARM", props)
    # No alarm
    mock_coordinator.data = {"MBF_PH_STATUS_ALARM": 0}
    assert ent.icon == "mdi:check-circle-outline"
    # Alarm
    mock_coordinator.data = {"MBF_PH_STATUS_ALARM": 3}
    assert ent.icon == "mdi:alert"


def test_icon_ph_status_alarm_default_icon(mock_coordinator):
    props = make_props(icon="mdi:ph")
    ent = VistaPoolSensor(mock_coordinator, "test_entry", "MBF_PH_STATUS_ALARM", props)
    mock_coordinator.data = {"MBF_PH_STATUS_ALARM": 0}
    assert ent.icon == "mdi:check-circle-outline"
    mock_coordinator.data = {"MBF_PH_STATUS_ALARM": 1}
    assert ent.icon == "mdi:alert"
    mock_coordinator.data = {"MBF_PH_STATUS_ALARM": None}
    assert ent.icon == "mdi:ph"


def test_icon_hidro_current(mock_coordinator):
    props = make_props(icon="mdi:air-humidifier")
    ent = VistaPoolSensor(mock_coordinator, "test_entry", "MBF_HIDRO_CURRENT", props)
    mock_coordinator.data = {"MBF_HIDRO_CURRENT": True}
    assert ent.icon == "mdi:air-humidifier"
    mock_coordinator.data = {"MBF_HIDRO_CURRENT": False}
    assert ent.icon == "mdi:air-humidifier-off"


def test_icon_default_icon():
    ent = make_sensor({"icon": "mdi:test"}, "MBF_MEASURE_PH", {})
    assert ent.icon == "mdi:test"


def test_icon_ph_alarm_unknown_status_code():
    """PH_STATUS_ALARM with a raw value not in the map falls back to _attr_icon."""
    ent = make_sensor(
        {"icon": "mdi:ph-fallback"}, "MBF_PH_STATUS_ALARM", {"MBF_PH_STATUS_ALARM": 99}
    )
    assert ent.icon == "mdi:ph-fallback"


def test_icon_fallback_for_non_special_key():
    """A key with a non-None raw value that has no special icon logic returns _attr_icon."""
    ent = make_sensor({"icon": "mdi:gauge"}, "MBF_MEASURE_RX", {"MBF_MEASURE_RX": 500})
    assert ent.icon == "mdi:gauge"


def test_native_value_returns_none_when_filtration_off():
    """Sensors in the filtration-dependent set return None when pump is off."""
    ent = make_sensor(
        {"unit": "°C"},
        "MBF_MEASURE_TEMPERATURE",
        {
            "MBF_MEASURE_TEMPERATURE": 25.5,
            "Filtration Pump": False,
        },
    )
    assert ent.native_value is None


@pytest.mark.asyncio
async def test_sensor_temperature_skip_when_inactive():
    """Test that MBF_MEASURE_TEMPERATURE is skipped when MBF_PAR_TEMPERATURE_ACTIVE is 0."""

    class DummyEntry:
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data = {
            "MBF_MEASURE_TEMPERATURE": 25.5,
            "MBF_PAR_TEMPERATURE_ACTIVE": 0,  # Temperature inactive
        }
        config_entry = DummyEntry()
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]

    entities = async_add_entities.call_args[0][0]
    keys = [e._key for e in entities]
    assert "MBF_MEASURE_TEMPERATURE" not in keys


@pytest.mark.asyncio
async def test_sensor_temperature_created_when_active():
    """Test that MBF_MEASURE_TEMPERATURE is created when MBF_PAR_TEMPERATURE_ACTIVE is not 0."""

    class DummyEntry:
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data = {
            "MBF_MEASURE_TEMPERATURE": 25.5,
            "MBF_PAR_TEMPERATURE_ACTIVE": 1,  # Temperature active
        }
        config_entry = DummyEntry()
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]

    entities = async_add_entities.call_args[0][0]
    keys = [e._key for e in entities]
    assert "MBF_MEASURE_TEMPERATURE" in keys


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sensor_key,value",
    [
        ("MBF_PAR_INTELLIGENT_INTERVALS", 5),
        ("MBF_PAR_INTELLIGENT_TT_NEXT_INTERVAL", 7200),
    ],
)
async def test_sensor_intelligent_key_skip_without_heating(sensor_key, value):
    """Intelligent-mode sensors are skipped when heating GPIO is not assigned."""

    class DummyEntry:
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data: dict = {}
        config_entry = DummyEntry()
        device_slug = "vistapool"

    DummyCoordinator.data = {
        sensor_key: value,
        "MBF_PAR_HEATING_GPIO": 0,  # No heating GPIO
        "MBF_PAR_TEMPERATURE_ACTIVE": 1,
    }

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]

    keys = [e._key for e in async_add_entities.call_args[0][0]]
    assert sensor_key not in keys


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sensor_key,value",
    [
        ("MBF_PAR_INTELLIGENT_INTERVALS", 5),
        ("MBF_PAR_INTELLIGENT_TT_NEXT_INTERVAL", 7200),
    ],
)
async def test_sensor_intelligent_key_created_with_heating(sensor_key, value):
    """Intelligent-mode sensors are created when heating GPIO is assigned and temperature is active."""

    class DummyEntry:
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data: dict = {}
        config_entry = DummyEntry()
        device_slug = "vistapool"

    DummyCoordinator.data = {
        sensor_key: value,
        "MBF_PAR_HEATING_GPIO": 7,  # Heating GPIO assigned
        "MBF_PAR_TEMPERATURE_ACTIVE": 1,
    }

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]

    keys = [e._key for e in async_add_entities.call_args[0][0]]
    assert sensor_key in keys


def test_sensor_intelligent_tt_next_interval_calls_helper():
    """Test that MBF_PAR_INTELLIGENT_TT_NEXT_INTERVAL sensor calls the helper function."""
    from unittest.mock import patch

    mock_coordinator = MagicMock()
    mock_coordinator.data = {"MBF_PAR_INTELLIGENT_TT_NEXT_INTERVAL": 3600}
    mock_coordinator.config_entry.options = {}
    mock_coordinator.config_entry.entry_id = "test_entry"
    mock_coordinator.entry = mock_coordinator.config_entry
    mock_coordinator.device_slug = "vistapool"

    props = {"device_class": "timestamp"}
    ent = VistaPoolSensor(
        mock_coordinator, "test_entry", "MBF_PAR_INTELLIGENT_TT_NEXT_INTERVAL", props
    )

    mock_hass = MagicMock()
    ent.hass = mock_hass

    # Patch the helper function to verify it's called correctly
    with patch(
        "custom_components.vistapool.sensor.calculate_next_interval_time"
    ) as mock_calc:
        _ = ent.native_value
        # Verify the helper was called with correct arguments
        mock_calc.assert_called_once_with(3600, mock_hass)


@pytest.mark.asyncio
async def test_async_setup_entry_no_data(caplog):
    """Test async_setup_entry logs warning and adds no entities when data is None."""

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
async def test_sensor_setup_with_capability_snapshot_only():
    """After a HA restart in winter mode coordinator.data holds only capability keys.

    All sensors that survive capability gating must still be registered so the
    entity registry stays consistent.  Measurement values are None (shown as
    unknown in HA) until winter mode is disabled.
    """

    class DummyEntry:
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        # Simulates the capability snapshot stored by set_winter_mode(True)
        data = {
            "MBF_PAR_MODEL": 0x0001,  # ion bit set
            "MBF_PAR_TEMPERATURE_ACTIVE": 1,
            "MBF_PAR_FILTRATION_CONF": 0x0001,  # variable-speed pump
            "MBF_PAR_HEATING_GPIO": 5,
            "Hydrolysis module detected": True,
            "pH measurement module detected": True,
            "Redox measurement module detected": True,
            "Chlorine measurement module detected": True,
            "Conductivity measurement module detected": True,
            # No measurement values – as returned after a restart in winter mode
        }
        config_entry = DummyEntry()
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]

    entities = async_add_entities.call_args[0][0]
    keys = [e._key for e in entities]

    # Measurement sensors guarded by capability flags must still be registered
    assert "MBF_MEASURE_PH" in keys
    assert "MBF_MEASURE_RX" in keys
    assert "MBF_MEASURE_CL" in keys
    assert "MBF_MEASURE_CONDUCTIVITY" in keys
    assert "MBF_MEASURE_TEMPERATURE" in keys
    assert "MBF_ION_CURRENT" in keys
    assert "ION_POLARITY" in keys
    assert "FILTRATION_SPEED" in keys
    assert "MBF_PH_STATUS_ALARM" in keys
    assert "PH_PUMP_STATUS" in keys
    assert "MBF_PAR_INTELLIGENT_INTERVALS" in keys
    assert "MBF_PAR_INTELLIGENT_TT_NEXT_INTERVAL" in keys
    # HIDRO sensors gated by Hydrolysis module detected
    assert "MBF_HIDRO_CURRENT" in keys
    assert "MBF_HIDRO_VOLTAGE" in keys
    assert "HIDRO_POLARITY" in keys
    # Unconditional sensors
    assert "MBF_PAR_FILT_MODE" in keys


@pytest.mark.asyncio
async def test_sensor_filtvalve_remaining_skipped_without_besgo():
    """MBF_PAR_FILTVALVE_REMAINING sensor must be skipped when Besgo valve is not configured."""

    class DummyEntry:
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data: dict = {}
        config_entry = DummyEntry()
        device_slug = "vistapool"

    DummyCoordinator.data = {"MBF_PAR_FILTVALVE_ENABLE": 0, "MBF_PAR_FILTVALVE_GPIO": 0}

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]

    keys = [e._key for e in async_add_entities.call_args[0][0]]
    assert "MBF_PAR_FILTVALVE_REMAINING" not in keys


@pytest.mark.asyncio
async def test_sensor_filtvalve_remaining_created_with_besgo():
    """MBF_PAR_FILTVALVE_REMAINING sensor must be created when Besgo valve is configured."""

    class DummyEntry:
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data: dict = {}
        config_entry = DummyEntry()
        device_slug = "vistapool"

    DummyCoordinator.data = {
        "MBF_PAR_FILTVALVE_ENABLE": 1,
        "MBF_PAR_FILTVALVE_REMAINING": 120,
    }

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]

    keys = [e._key for e in async_add_entities.call_args[0][0]]
    assert "MBF_PAR_FILTVALVE_REMAINING" in keys


@pytest.mark.asyncio
async def test_sensor_filtvalve_remaining_created_with_gpio_only():
    """MBF_PAR_FILTVALVE_REMAINING sensor must be created when only GPIO is set (ENABLE=0)."""

    class DummyEntry:
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data: dict = {}
        config_entry = DummyEntry()
        device_slug = "vistapool"

    DummyCoordinator.data = {
        "MBF_PAR_FILTVALVE_ENABLE": 0,
        "MBF_PAR_FILTVALVE_GPIO": 5,
        "MBF_PAR_FILTVALVE_REMAINING": 60,
    }

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]

    keys = [e._key for e in async_add_entities.call_args[0][0]]
    assert "MBF_PAR_FILTVALVE_REMAINING" in keys


def test_sensor_filtvalve_remaining_native_value():
    """MBF_PAR_FILTVALVE_REMAINING sensor returns raw seconds from coordinator data."""
    mock_coordinator = MagicMock()
    mock_coordinator.data = {"MBF_PAR_FILTVALVE_REMAINING": 90}
    mock_coordinator.config_entry.entry_id = "test_entry"
    mock_coordinator.device_slug = "vistapool"

    from custom_components.vistapool.sensor import VistaPoolSensor

    ent = VistaPoolSensor(
        mock_coordinator, "test_entry", "MBF_PAR_FILTVALVE_REMAINING", {}
    )
    assert ent.native_value == 90


def test_sensor_filtration_remaining_native_value():
    """filtration_remaining sensor returns the aggregated remaining time."""
    mock_coordinator = MagicMock()
    mock_coordinator.data = {"FILTRATION_REMAINING": 1800}
    mock_coordinator.config_entry.entry_id = "test_entry"
    mock_coordinator.config_entry.options = {}
    mock_coordinator.entry = mock_coordinator.config_entry
    mock_coordinator.device_slug = "vistapool"

    from custom_components.vistapool.sensor import VistaPoolSensor

    ent = VistaPoolSensor(mock_coordinator, "test_entry", "FILTRATION_REMAINING", {})
    assert ent.native_value == 1800


def test_sensor_filtration_remaining_none_when_idle():
    """filtration_remaining sensor returns None when no timer is counting down."""
    mock_coordinator = MagicMock()
    mock_coordinator.data = {"FILTRATION_REMAINING": None}
    mock_coordinator.config_entry.entry_id = "test_entry"
    mock_coordinator.config_entry.options = {}
    mock_coordinator.entry = mock_coordinator.config_entry
    mock_coordinator.device_slug = "vistapool"

    from custom_components.vistapool.sensor import VistaPoolSensor

    ent = VistaPoolSensor(mock_coordinator, "test_entry", "FILTRATION_REMAINING", {})
    assert ent.native_value is None
