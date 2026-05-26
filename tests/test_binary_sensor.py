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

from custom_components.vistapool.binary_sensor import (
    VistaPoolBinarySensor,
    async_setup_entry,
)


@pytest.fixture
def mock_coordinator():
    mock = MagicMock()
    mock.data = {}
    mock.device_slug = "vistapool"
    mock.config_entry.entry_id = "test_entry"
    return mock


def make_props(**kwargs):
    d = {}
    d.update(kwargs)
    return d


@pytest.mark.asyncio
async def test_async_setup_entry_adds_entities(monkeypatch):
    """Test async_setup_entry adds the correct entities."""

    # Prepare a fake coordinator with sample data
    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data = {
            "MBF_PAR_MODEL": 0x000F,  # All bits set (should allow all modules)
            "MBF_PAR_PH_BASE_RELAY_GPIO": 1,
            "MBF_PAR_PH_ACID_RELAY_GPIO": 1,
            "MBF_PAR_RX_RELAY_GPIO": 2,
            "MBF_PAR_CL_RELAY_GPIO": 3,
            "MBF_PAR_CD_RELAY_GPIO": 4,
            "Hydrolysis module detected": True,
            "Chlorine measurement module detected": True,
            "Redox measurement module detected": True,
            "pH measurement module detected": True,
            "Conductivity measurement module detected": True,
        }
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]

    # Entities should be created and passed to async_add_entities
    # The number depends on your BINARY_SENSOR_DEFINITIONS (at least 1 expected)
    assert async_add_entities.call_count == 1
    entities = async_add_entities.call_args[0][0]
    assert isinstance(entities, list)
    # At least one entity, all must be instances of VistaPoolBinarySensor
    from custom_components.vistapool.binary_sensor import VistaPoolBinarySensor

    assert all(isinstance(e, VistaPoolBinarySensor) for e in entities)
    # (Optional) Check that entities have correct keys
    entity_keys = [e._key for e in entities]
    # Should contain at least one expected sensor (by key from BINARY_SENSOR_DEFINITIONS)
    # For example, "pH control module"
    assert any("control module" in k for k in entity_keys)
    # HIDRO entities created when Hydrolysis module detected
    hidro_keys = [k for k in entity_keys if k.startswith("HIDRO ")]
    assert len(hidro_keys) > 0, "HIDRO entities should be created"
    # pH Acid Pump created when relay is assigned
    assert "pH Acid Pump" in entity_keys


@pytest.mark.asyncio
async def test_async_setup_entry_skips_hidro_without_hydrolysis(monkeypatch):
    """Test that HIDRO binary sensors are skipped when Hydrolysis module detected is False."""

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data = {
            "MBF_PAR_MODEL": 0x000F,
            "MBF_PAR_PH_ACID_RELAY_GPIO": 1,
            "Hydrolysis module detected": False,  # No hydrolysis module
        }
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]

    entities = async_add_entities.call_args[0][0]
    entity_keys = [e._key for e in entities]
    hidro_keys = [k for k in entity_keys if k.startswith("HIDRO ")]
    assert hidro_keys == [], f"HIDRO entities should be skipped: {hidro_keys}"


@pytest.mark.asyncio
async def test_async_setup_entry_skips_ph_acid_pump_without_relay(monkeypatch):
    """Test that pH Acid Pump binary sensor is skipped when relay is not assigned."""

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data = {
            "MBF_PAR_MODEL": 0x000F,
            "MBF_PAR_PH_ACID_RELAY_GPIO": 0,  # No acid relay
        }
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]

    entities = async_add_entities.call_args[0][0]
    entity_keys = [e._key for e in entities]
    assert "pH Acid Pump" not in entity_keys


@pytest.mark.asyncio
async def test_async_setup_entry_skips_cl_module_sensor_without_chlorine(monkeypatch):
    """Test that CL module binary sensor is skipped when chlorine module is not detected."""

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data = {
            "MBF_PAR_MODEL": 0x000F,
            "Hydrolysis module detected": True,
            "Chlorine measurement module detected": False,
        }
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]

    entities = async_add_entities.call_args[0][0]
    entity_keys = [e._key for e in entities]
    cl_keys = [k for k in entity_keys if k.endswith("Activated by the CL module")]
    assert cl_keys == [], f"CL module entities should be skipped: {cl_keys}"


@pytest.mark.asyncio
async def test_async_setup_entry_skips_rx_module_sensor_without_redox(monkeypatch):
    """Test that RX module binary sensor is skipped when redox module is not detected."""

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data = {
            "MBF_PAR_MODEL": 0x000F,
            "Hydrolysis module detected": True,
            "Redox measurement module detected": False,
        }
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]

    entities = async_add_entities.call_args[0][0]
    entity_keys = [e._key for e in entities]
    rx_keys = [k for k in entity_keys if k.endswith("Activated by the RX module")]
    assert rx_keys == [], f"RX module entities should be skipped: {rx_keys}"


@pytest.mark.asyncio
async def test_async_setup_entry_no_data(monkeypatch, caplog):
    """Test async_setup_entry returns early if coordinator.data is None."""

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data = None
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    with caplog.at_level("WARNING"):
        await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
        # Should log warning
        assert "No data from Modbus" in caplog.text
    # No entities should be added
    async_add_entities.assert_not_called()


@pytest.mark.asyncio
async def test_async_setup_entry_option_disables_sensor(monkeypatch):
    """Test that sensors with options=False are skipped."""

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {"sensor_option": False}

    class DummyCoordinator:
        data = {"MBF_PAR_MODEL": 0x0001}
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    # Patch BINARY_SENSOR_DEFINITIONS for this test
    from custom_components.vistapool import binary_sensor as bs_module

    monkeypatch.setitem(
        bs_module.BINARY_SENSOR_DEFINITIONS,
        "Some Option Sensor",
        {"option": "sensor_option"},
    )

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    # Should only add sensors without "option" or with option True
    entities = async_add_entities.call_args[0][0]
    assert not any(e._key == "Some Option Sensor" for e in entities)


@pytest.mark.asyncio
async def test_async_setup_entry_skips_pool_cover_when_not_enabled(monkeypatch):
    """Test that Pool Cover sensor is skipped when cover sensor option is not enabled."""

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {}  # use_cover_sensor defaults to False

    class DummyCoordinator:
        data = {
            "MBF_PAR_MODEL": 0x0002,  # Hidro module present
        }
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    entities = async_add_entities.call_args[0][0]
    # Pool Cover should NOT be in entities
    assert not any(e._key == "Pool Cover" for e in entities)


@pytest.mark.asyncio
async def test_async_setup_entry_includes_pool_cover_when_enabled(monkeypatch):
    """Test that Pool Cover sensor is included when cover sensor option is enabled."""

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {"use_cover_sensor": True}  # cover sensor option enabled

    class DummyCoordinator:
        data = {
            "MBF_PAR_MODEL": 0x0002,  # Hidro module present
        }
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    entities = async_add_entities.call_args[0][0]
    # Pool Cover SHOULD be in entities
    assert any(e._key == "Pool Cover" for e in entities)


def test_is_on_direct_key(mock_coordinator):
    props = make_props()
    ent = VistaPoolBinarySensor(
        mock_coordinator, "test_entry", "pH acid pump active", props
    )
    mock_coordinator.data = {"pH acid pump active": True}
    assert ent.is_on is True
    mock_coordinator.data = {"pH acid pump active": False}
    assert ent.is_on is False
    mock_coordinator.data = {}  # key absent → missing data → unknown
    assert ent.is_on is None


def test_is_on_device_time_out_of_sync(mock_coordinator):
    props = make_props()
    ent = VistaPoolBinarySensor(
        mock_coordinator, "test_entry", "Device Time Out Of Sync", props
    )
    with patch(
        "custom_components.vistapool.binary_sensor.is_device_time_out_of_sync",
        return_value=True,
    ):
        mock_coordinator.data = {"MBF_PAR_TIME_LOW": 1}
        assert ent.is_on is True
    with patch(
        "custom_components.vistapool.binary_sensor.is_device_time_out_of_sync",
        return_value=False,
    ):
        mock_coordinator.data = {"MBF_PAR_TIME_LOW": 1}
        assert ent.is_on is False
    # No time data in snapshot → unknown, not False
    mock_coordinator.data = {}
    assert ent.is_on is None


def test_is_on_pool_cover_inverted(mock_coordinator):
    """Test Pool Cover has inverted logic for OPENING device class."""
    props = make_props()
    ent = VistaPoolBinarySensor(mock_coordinator, "test_entry", "Pool Cover", props)
    # Hardware: 1 = cover active (pool covered) -> HA: OFF (closed)
    mock_coordinator.data = {"Pool Cover": True}
    assert ent.is_on is False
    # Hardware: 0 = cover inactive (pool uncovered) -> HA: ON (open)
    mock_coordinator.data = {"Pool Cover": False}
    assert ent.is_on is True


def test_is_on_pool_cover_none_value(mock_coordinator):
    """Test Pool Cover returns None when value is missing (unknown state, not True)."""
    props = make_props()
    ent = VistaPoolBinarySensor(mock_coordinator, "test_entry", "Pool Cover", props)
    mock_coordinator.data = {}  # key absent -> value is None
    assert ent.is_on is None
    mock_coordinator.data = {"Pool Cover": None}  # key present but explicitly None
    assert ent.is_on is None


def test_is_on_measurement_module_filtration_pump_off(mock_coordinator):
    props = make_props()
    ent = VistaPoolBinarySensor(
        mock_coordinator, "test_entry", "pH measurement active", props
    )
    mock_coordinator.data = {"Filtration Pump": False, "pH measurement active": True}
    # Filtration off disables sensor
    assert ent.is_on is False
    # If pump is on, returns True
    mock_coordinator.data = {"Filtration Pump": True, "pH measurement active": True}
    assert ent.is_on is True


def test_is_on_status_dict(mock_coordinator):
    props = make_props()
    ent = VistaPoolBinarySensor(
        mock_coordinator, "test_entry", "MBF_STATUS_pump_on", props
    )
    mock_coordinator.data = {"MBF_STATUS": {"pump_on": True, "other": False}}
    assert ent.is_on is True
    mock_coordinator.data = {"MBF_STATUS": {"pump_on": False}}
    assert ent.is_on is False
    # Flag absent from dict → unknown
    mock_coordinator.data = {"MBF_STATUS": {}}
    assert ent.is_on is None
    # Status not a dict → unknown
    mock_coordinator.data = {"MBF_STATUS": None}
    assert ent.is_on is None


def test_icon_on_off(mock_coordinator):
    props = make_props(icon_on="mdi:pump", icon_off="mdi:pump-off")
    ent = VistaPoolBinarySensor(
        mock_coordinator, "test_entry", "pH acid pump active", props
    )
    mock_coordinator.data = {"pH acid pump active": True}
    assert ent.icon == "mdi:pump"
    mock_coordinator.data = {"pH acid pump active": False}
    assert ent.icon == "mdi:pump-off"


def test_native_value(mock_coordinator):
    props = make_props()
    ent = VistaPoolBinarySensor(
        mock_coordinator, "test_entry", "pH acid pump active", props
    )
    mock_coordinator.data = {"pH acid pump active": True}
    assert ent.native_value is True
    mock_coordinator.data = {}
    assert ent.native_value is None


@pytest.mark.asyncio
async def test_async_added_to_hass_calls_super(mock_coordinator):
    props = make_props()
    ent = VistaPoolBinarySensor(
        mock_coordinator, "test_entry", "pH acid pump active", props
    )
    with patch(
        "custom_components.vistapool.binary_sensor.VistaPoolEntity.async_added_to_hass",
        return_value=None,
    ) as parent:
        await ent.async_added_to_hass()
        parent.assert_called_once()


def test_available_during_winter_mode(mock_coordinator):
    """Binary sensors stay available during winter mode (they show unknown values)."""
    mock_coordinator.winter_mode = True
    mock_coordinator.last_update_success = True
    props = make_props()
    ent = VistaPoolBinarySensor(
        mock_coordinator, "test_entry", "pH acid pump active", props
    )
    assert ent.available is True


# --- UV Lamp binary sensor tests ---


@pytest.mark.asyncio
async def test_async_setup_entry_includes_uv_lamp_when_relay_assigned():
    """UV Lamp binary sensor is included when MBF_PAR_UV_RELAY_GPIO is set."""

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data = {
            "MBF_PAR_MODEL": 0x0001,
            "MBF_PAR_UV_RELAY_GPIO": 3,
        }
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    entities = async_add_entities.call_args[0][0]
    assert any(e._key == "UV Lamp" for e in entities)


@pytest.mark.asyncio
async def test_async_setup_entry_skips_uv_lamp_when_no_relay():
    """UV Lamp binary sensor is skipped when MBF_PAR_UV_RELAY_GPIO is 0."""

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data = {
            "MBF_PAR_MODEL": 0x0001,
            "MBF_PAR_UV_RELAY_GPIO": 0,
        }
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    entities = async_add_entities.call_args[0][0]
    assert not any(e._key == "UV Lamp" for e in entities)


@pytest.mark.asyncio
async def test_async_setup_entry_creates_uv_lamp_when_key_missing():
    """UV Lamp binary sensor is created when MBF_PAR_UV_RELAY_GPIO is absent (old snapshot)."""

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data = {
            "MBF_PAR_MODEL": 0x0001,
        }
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    entities = async_add_entities.call_args[0][0]
    assert any(e._key == "UV Lamp" for e in entities)


@pytest.mark.asyncio
async def test_async_setup_entry_skips_uv_lamp_when_gpio_out_of_range():
    """UV Lamp binary sensor is skipped when MBF_PAR_UV_RELAY_GPIO is out of range."""

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data = {
            "MBF_PAR_MODEL": 0x0001,
            "MBF_PAR_UV_RELAY_GPIO": 255,
        }
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    entities = async_add_entities.call_args[0][0]
    assert not any(e._key == "UV Lamp" for e in entities)


def test_uv_lamp_is_on(mock_coordinator):
    """UV Lamp binary sensor reads state from coordinator data."""
    props = make_props()
    ent = VistaPoolBinarySensor(mock_coordinator, "test_entry", "UV Lamp", props)
    mock_coordinator.data = {"UV Lamp": True}
    assert ent.is_on is True
    mock_coordinator.data = {"UV Lamp": False}
    assert ent.is_on is False
    mock_coordinator.data = {}
    assert ent.is_on is None


@pytest.mark.asyncio
async def test_async_setup_entry_skips_pool_light_without_relay():
    """Test that Pool Light binary sensor is skipped when lighting relay is not assigned."""

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {"use_light": True}

    class DummyCoordinator:
        data = {
            "MBF_PAR_MODEL": 0x000F,
            "MBF_PAR_LIGHTING_GPIO": 0,  # No lighting relay
        }
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]

    entities = async_add_entities.call_args[0][0]
    entity_keys = [e._key for e in entities]
    assert "Pool Light" not in entity_keys


@pytest.mark.asyncio
async def test_async_setup_entry_skips_filtration_pump_without_relay():
    """Test that Filtration Pump binary sensor is skipped when filtration relay is not assigned."""

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data = {
            "MBF_PAR_MODEL": 0x000F,
            "MBF_PAR_FILT_GPIO": 0,  # No filtration relay
        }
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]

    entities = async_add_entities.call_args[0][0]
    entity_keys = [e._key for e in entities]
    assert "Filtration Pump" not in entity_keys


@pytest.mark.asyncio
async def test_async_setup_entry_skips_pump_sensors_without_relay():
    """Pump status sensors are skipped when their relay GPIO is not assigned."""

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data = {
            "MBF_PAR_MODEL": 0x000F,
            "Hydrolysis module detected": True,
            "pH measurement module detected": True,
            "Redox measurement module detected": True,
            "Chlorine measurement module detected": True,
            "Conductivity measurement module detected": True,
            # pH acid relay assigned, base not assigned
            "MBF_PAR_PH_ACID_RELAY_GPIO": 3,
            "MBF_PAR_PH_BASE_RELAY_GPIO": 0,
            # Redox relay assigned, Chlorine not
            "MBF_PAR_RX_RELAY_GPIO": 4,
            "MBF_PAR_CL_RELAY_GPIO": 0,
            "MBF_PAR_CD_RELAY_GPIO": 0,
        }
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    entities = async_add_entities.call_args[0][0]
    keys = [e._key for e in entities]

    # pH acid/base pump active are now the PH_PUMP_STATUS enum sensor, not binary sensors
    assert "pH acid pump active" not in keys
    assert "pH pump active" not in keys
    # Redox pump has relay → included
    assert "Redox pump active" in keys
    # Chlorine pump has no relay → skipped
    assert "Chlorine pump active" not in keys
    # Conductivity pump has no relay → skipped
    assert "Conductivity pump active" not in keys


@pytest.mark.asyncio
async def test_async_setup_entry_pump_sensors_with_capability_snapshot():
    """Pump sensors survive HA restart in winter mode when GPIO keys are in capability snapshot."""

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        # Simulates capability snapshot (winter mode restart) — only CAPABILITY_KEYS present
        data = {
            "MBF_PAR_MODEL": 0x000F,
            "Hydrolysis module detected": True,
            "pH measurement module detected": True,
            "Redox measurement module detected": True,
            "Chlorine measurement module detected": True,
            "Conductivity measurement module detected": True,
            # GPIO keys — must be in CAPABILITY_KEYS to survive winter mode
            "MBF_PAR_PH_ACID_RELAY_GPIO": 3,
            "MBF_PAR_RX_RELAY_GPIO": 4,
            "MBF_PAR_CL_RELAY_GPIO": 5,
            "MBF_PAR_CD_RELAY_GPIO": 0,
        }
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    entities = async_add_entities.call_args[0][0]
    keys = [e._key for e in entities]

    # Pump sensors with assigned relay must be created even from capability snapshot
    assert "Redox pump active" in keys
    assert "Chlorine pump active" in keys
    # Conductivity has no relay → still skipped
    assert "Conductivity pump active" not in keys


@pytest.mark.asyncio
async def test_enabled_default_for_pump_and_problem_sensors():
    """Sensors like pH Acid Pump, HIDRO Low Flow, and shock mode are enabled by default."""

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"
        options = {}

    class DummyCoordinator:
        data = {
            "MBF_PAR_MODEL": 0x000F,
            "MBF_PAR_PH_ACID_RELAY_GPIO": 1,
            "Hydrolysis module detected": True,
            "pH measurement module detected": True,
            "Redox measurement module detected": True,
            "Chlorine measurement module detected": True,
            "Conductivity measurement module detected": True,
        }
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "vistapool"

    hass = MagicMock()
    hass.data = {"vistapool": {"test_entry": DummyCoordinator()}}
    entry = DummyEntry()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    entities = async_add_entities.call_args[0][0]
    by_key = {e._key: e for e in entities}

    # These sensors should be enabled by default (not in DISABLED_SUFFIXES)
    assert by_key["pH Acid Pump"]._attr_entity_registry_enabled_default is True
    assert by_key["HIDRO Low Flow"]._attr_entity_registry_enabled_default is True
    assert (
        by_key["HIDRO Chlorine shock mode"]._attr_entity_registry_enabled_default
        is True
    )
