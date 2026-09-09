"""Tests for the NeoPool sensor platform."""

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache_with_extra_data,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from custom_components.neopool.const import (
    CONF_CAPABILITIES,
    CONF_MEASURE_WHEN_FILTRATION_OFF,
    CONF_MODBUS_FRAMER,
    CONF_UNIT_ID,
    CURRENT_VERSION,
    DOMAIN,
)
from homeassistant.components.sensor import ATTR_OPTIONS, DOMAIN as SENSOR_DOMAIN
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    Platform,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er

from . import setup_integration
from .conftest import MOCK_POOL_DATA


async def test_measurement_sensors_suppressed_when_filtration_off(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Probe sensors report unknown while filtration pump is off (stale reading)."""
    await setup_integration(hass, mock_config_entry)
    mock_neopool_client.async_read_all.return_value = {
        **MOCK_POOL_DATA,
        "Filtration Pump": False,
    }
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    for entity_id in (
        "sensor.neopool_ph",
        "sensor.neopool_redox_potential",
        "sensor.neopool_water_temperature",
    ):
        state = hass.states.get(entity_id)
        assert state is not None, f"{entity_id} not registered"
        assert state.state == "unknown"


async def test_production_sensors_zero_when_filtration_off(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Production sensors report 0 while filtration pump is off (cell idle)."""
    await setup_integration(hass, mock_config_entry)
    mock_neopool_client.async_read_all.return_value = {
        **MOCK_POOL_DATA,
        "Filtration Pump": False,
    }
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    for entity_id in (
        "sensor.neopool_hydrolysis_intensity",
        "sensor.neopool_ionization_level",
    ):
        state = hass.states.get(entity_id)
        assert state is not None, f"{entity_id} not registered"
        assert state.state == "0"


@pytest.mark.parametrize(
    ("filt_mode", "expected"),
    [
        (0, "manual"),
        (1, "auto"),
        (2, "heating"),
        (3, "smart"),
        (4, "intelligent"),
        (13, "backwash"),
    ],
)
async def test_filt_mode_native_value(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    freezer: FrozenDateTimeFactory,
    filt_mode: int,
    expected: str,
) -> None:
    """Filt mode native value reads the lib's decoded filtration_mode key."""
    await setup_integration(hass, mock_config_entry)
    mock_neopool_client.async_read_all.return_value = {
        **MOCK_POOL_DATA,
        "MBF_PAR_FILT_MODE": filt_mode,
        "filtration_mode": expected,
    }
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.neopool_filtration_mode")
    assert state is not None
    assert state.state == expected


@pytest.mark.parametrize(
    ("relay", "expected_options"),
    [
        pytest.param(1, ["off", "idle", "acid"], id="acid_only"),
        pytest.param(2, ["off", "idle", "base"], id="base_only"),
        pytest.param(0, ["off", "idle", "acid", "base", "both"], id="both_relays"),
    ],
)
async def test_ph_pump_status_options_per_relay_config(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    freezer: FrozenDateTimeFactory,
    relay: int,
    expected_options: list[str],
) -> None:
    """The pH pump status options list shrinks based on the relay configuration."""
    await setup_integration(hass, mock_config_entry)
    mock_neopool_client.async_read_all.return_value = {
        **MOCK_POOL_DATA,
        "MBF_PAR_RELAY_PH": relay,
    }
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.neopool_ph_pump_status")
    assert state is not None
    assert state.attributes[ATTR_OPTIONS] == expected_options


async def test_hidro_current_g_per_hour_mode(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """In g/h mode HIDRO_CURRENT swaps unit and bumps display precision."""
    await setup_integration(hass, mock_config_entry)
    mock_neopool_client.async_read_all.return_value = {
        **MOCK_POOL_DATA,
        "MBF_PAR_UICFG_MACHINE": 1,
    }
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.neopool_hydrolysis_intensity")
    assert state is not None
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == "g/h"


_CELL_RUNTIME_ENTITY_IDS: dict[str, str] = {
    "CELL_RUNTIME_TOTAL": "sensor.neopool_cell_runtime_total",
    "CELL_RUNTIME_PART": "sensor.neopool_cell_runtime_since_reset",
    "CELL_RUNTIME_POLA": "sensor.neopool_cell_runtime_in_polarity_1",
    "CELL_RUNTIME_POLB": "sensor.neopool_cell_runtime_in_polarity_2",
    "CELL_RUNTIME_POL_CHANGES": "sensor.neopool_cell_polarity_changes",
}


@pytest.mark.parametrize(
    ("key", "expected_seconds"),
    [
        ("CELL_RUNTIME_TOTAL", 65536),
        ("CELL_RUNTIME_PART", 3600),
        ("CELL_RUNTIME_POLA", 1800),
        ("CELL_RUNTIME_POLB", 1800),
    ],
)
@pytest.mark.usefixtures("entity_registry_enabled_by_default", "mock_neopool_client")
async def test_cell_runtime_duration_sensor_reads_combined_register(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    key: str,
    expected_seconds: int,
) -> None:
    """Each duration CELL_RUNTIME_* sensor reads the combined u32 key from coordinator data.

    Sensors have ``entity_registry_enabled_default=False``; enabling every
    disabled-by-default entity via the fixture avoids the reload dance. The
    sensors declare seconds but suggest hours, so ``state.state`` is expressed
    in hours (converted by the frontend layer).
    """
    await setup_integration(hass, mock_config_entry)

    entity_id = _CELL_RUNTIME_ENTITY_IDS[key]
    state = hass.states.get(entity_id)
    assert state is not None, f"{entity_id} not registered"
    assert float(state.state) == pytest.approx(expected_seconds / 3600, abs=1e-4)


@pytest.mark.usefixtures("entity_registry_enabled_by_default", "mock_neopool_client")
async def test_cell_runtime_pol_changes_sensor_reads_combined_register(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """CELL_RUNTIME_POL_CHANGES reads the combined u32 key as a raw counter.

    Unlike the duration sensors, this one has no unit and no unit conversion,
    so ``state.state`` is the raw integer from coordinator data.
    """
    await setup_integration(hass, mock_config_entry)

    entity_id = _CELL_RUNTIME_ENTITY_IDS["CELL_RUNTIME_POL_CHANGES"]
    state = hass.states.get(entity_id)
    assert state is not None, f"{entity_id} not registered"
    assert state.state == "7"


@pytest.mark.freeze_time("2026-07-03T12:00:00Z")
@pytest.mark.usefixtures("entity_registry_enabled_by_default", "mock_neopool_client")
async def test_all_entities(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Snapshot every entity registered by the sensor platform."""
    with patch("custom_components.neopool.PLATFORMS", [Platform.SENSOR]):
        await setup_integration(hass, mock_config_entry)
    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


@pytest.mark.freeze_time("2026-07-03T12:00:00Z")
@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_setup_when_modules_absent(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    minimal_pool_data: dict[str, Any],
) -> None:
    """Snapshot the sensor entities registered when no modules are present."""
    mock_neopool_client.async_read_all.return_value = minimal_pool_data
    with patch("custom_components.neopool.PLATFORMS", [Platform.SENSOR]):
        await setup_integration(hass, mock_config_entry)
    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


# CUSTOM-ONLY START
# ---------------------------------------------------------------------------
# measure_when_filtration_off gate (HACS-only option) and filtration-pump
# energy sensor (HACS-only derived sensor) - stripped from the core sync.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        "MBF_MEASURE_TEMPERATURE",
        "MBF_MEASURE_PH",
        "MBF_MEASURE_RX",
        "MBF_MEASURE_CL",
        "MBF_MEASURE_CONDUCTIVITY",
    ],
)
async def test_measure_when_filtration_off_option_flips_gate(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    freezer: FrozenDateTimeFactory,
    key: str,
) -> None:
    """The measure_when_filtration_off option exposes readings while pump is off."""
    _ENTITY_ID_BY_KEY = {
        "MBF_MEASURE_TEMPERATURE": "sensor.neopool_water_temperature",
        "MBF_MEASURE_PH": "sensor.neopool_ph",
        "MBF_MEASURE_RX": "sensor.neopool_redox_potential",
        "MBF_MEASURE_CL": "sensor.neopool_salt_level",
        "MBF_MEASURE_CONDUCTIVITY": "sensor.neopool_conductivity_level",
    }
    await setup_integration(hass, mock_config_entry)
    entity_id = _ENTITY_ID_BY_KEY[key]
    mock_neopool_client.async_read_all.return_value = {
        **MOCK_POOL_DATA,
        "Filtration Pump": False,
    }
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_UNKNOWN

    new_options = dict(mock_config_entry.options)
    new_options[CONF_MEASURE_WHEN_FILTRATION_OFF] = True
    hass.config_entries.async_update_entry(mock_config_entry, options=new_options)
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == str(MOCK_POOL_DATA[key])


async def test_filtvalve_remaining_unknown_when_idle(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Backwash time remaining is unknown while idle (0), matching filtration."""
    registry = er.async_get(hass)
    await setup_integration(hass, mock_config_entry)
    entries = [
        e
        for e in er.async_entries_for_config_entry(registry, mock_config_entry.entry_id)
        if e.domain == "sensor" and e.unique_id.endswith("_mbf_par_filtvalve_remaining")
    ]
    assert entries, "backwash time remaining sensor not registered"
    entity_id = entries[0].entity_id

    assert hass.states.get(entity_id).state == STATE_UNKNOWN

    mock_neopool_client.async_read_all.return_value = {
        **MOCK_POOL_DATA,
        "MBF_PAR_FILTVALVE_REMAINING": 90,
    }
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "90"


@pytest.mark.usefixtures("mock_neopool_client")
async def test_filtration_pump_energy_sensor_registers_when_power_set(
    hass: HomeAssistant,
) -> None:
    """A non-zero filtration_pump_power option creates the energy sensor."""
    entry = MockConfigEntry(
        domain="neopool",
        title="Pool",
        unique_id="neopool_pump_power",
        version=CURRENT_VERSION,
        data={
            "host": "192.0.2.30",
            "port": 502,
            "name": "Pool",
            CONF_UNIT_ID: 1,
            CONF_MODBUS_FRAMER: "tcp",
        },
        options={
            CONF_MODBUS_FRAMER: "tcp",
            "filtration_pump_power": 800,
        },
    )
    await setup_integration(hass, entry)
    registry = er.async_get(hass)
    entries = [
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == SENSOR_DOMAIN and e.unique_id.endswith("_filtration_pump_energy")
    ]
    assert entries, "expected filtration_pump_energy sensor when pump_power > 0"


async def test_filtration_pump_energy_accumulates_while_pump_runs(
    hass: HomeAssistant,
    mock_neopool_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Energy accumulates power x elapsed-hours when the pump is running."""
    pump_data = dict(MOCK_POOL_DATA)
    pump_data["Filtration Pump"] = True
    mock_neopool_client.async_read_all = AsyncMock(return_value=pump_data)

    entry = MockConfigEntry(
        domain="neopool",
        title="Pool",
        unique_id="neopool_pump_acc",
        version=CURRENT_VERSION,
        data={
            "host": "192.0.2.31",
            "port": 502,
            "name": "Pool",
            CONF_UNIT_ID: 1,
            CONF_MODBUS_FRAMER: "tcp",
        },
        options={
            CONF_MODBUS_FRAMER: "tcp",
            "filtration_pump_power": 1000,
        },
    )
    await setup_integration(hass, entry)

    entity_id = "sensor.neopool_filtration_pump_energy"
    assert hass.states.get(entity_id) is not None

    # First poll primes the accumulator (records the pump-on baseline);
    # accumulation only starts once a prior on-state and timestamp exist.
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    initial_wh = float(hass.states.get(entity_id).state)

    # Second poll an interval later: with the pump on the whole time, the
    # sensor accrues power x elapsed-hours between the two polls.
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    later_wh = float(hass.states.get(entity_id).state)
    assert later_wh > initial_wh


@pytest.mark.usefixtures("mock_neopool_client")
async def test_filtration_pump_energy_restores_native_value_after_restart(
    hass: HomeAssistant,
) -> None:
    """RestoreSensor recovers the previous Wh counter after a HA restart."""
    fake_state = State("sensor.neopool_filtration_pump_energy", STATE_UNKNOWN)
    fake_extra_data = {
        "native_value": 12345.6,
        "native_unit_of_measurement": "Wh",
    }
    mock_restore_cache_with_extra_data(hass, ((fake_state, fake_extra_data),))

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Pool",
        unique_id="neopool_pump_restore",
        version=CURRENT_VERSION,
        data={
            "host": "192.0.2.32",
            "port": 502,
            "name": "Pool",
            CONF_UNIT_ID: 1,
            CONF_MODBUS_FRAMER: "tcp",
        },
        options={
            CONF_MODBUS_FRAMER: "tcp",
            "filtration_pump_power": 1000,
        },
    )
    await setup_integration(hass, entry)

    entity_id = "sensor.neopool_filtration_pump_energy"
    state = hass.states.get(entity_id)
    assert state is not None
    assert float(state.state) == pytest.approx(12.3456)


@pytest.mark.usefixtures("mock_neopool_client")
async def test_filtration_pump_energy_ignores_non_numeric_restore(
    hass: HomeAssistant,
) -> None:
    """A non-numeric restored native_value does not corrupt the counter."""
    fake_state = State("sensor.neopool_filtration_pump_energy", STATE_UNKNOWN)
    fake_extra_data = {
        "native_value": {"__type": "<class 'datetime.datetime'>", "isoformat": "..."},
        "native_unit_of_measurement": "Wh",
    }
    mock_restore_cache_with_extra_data(hass, ((fake_state, fake_extra_data),))

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Pool",
        unique_id="neopool_pump_bad_restore",
        version=CURRENT_VERSION,
        data={
            "host": "192.0.2.33",
            "port": 502,
            "name": "Pool",
            CONF_UNIT_ID: 1,
            CONF_MODBUS_FRAMER: "tcp",
        },
        options={
            CONF_MODBUS_FRAMER: "tcp",
            "filtration_pump_power": 1000,
        },
    )
    await setup_integration(hass, entry)

    entity_id = "sensor.neopool_filtration_pump_energy"
    state = hass.states.get(entity_id)
    assert state is not None
    assert float(state.state) == 0


async def test_cell_runtime_sensors_skipped_without_hydrolysis(
    hass: HomeAssistant,
    mock_neopool_client: MagicMock,
) -> None:
    """No CELL_RUNTIME_* entity is registered on a unit without hydrolysis."""
    no_hidro = dict(MOCK_POOL_DATA)
    no_hidro["Hydrolysis module detected"] = False
    mock_neopool_client.async_read_all.return_value = no_hidro

    entry = MockConfigEntry(
        domain="neopool",
        title="Test Pool",
        unique_id="neopool_no_hidro",
        version=CURRENT_VERSION,
        data={
            "host": "192.0.2.1",
            "port": 502,
            "name": "Test Pool",
            CONF_UNIT_ID: 1,
            CONF_MODBUS_FRAMER: "tcp",
        },
        options={CONF_MODBUS_FRAMER: "tcp"},
    )
    await setup_integration(hass, entry)

    registry = er.async_get(hass)
    cell_entities = [
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == SENSOR_DOMAIN and "cell_runtime" in e.unique_id
    ]
    assert cell_entities == []


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_cell_runtime_sensor_returns_none_when_key_missing(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Sensor returns None when the combined key is absent from coordinator data."""
    await setup_integration(hass, mock_config_entry)
    reduced = {k: v for k, v in MOCK_POOL_DATA.items() if k != "CELL_RUNTIME_PART"}
    mock_neopool_client.async_read_all.return_value = reduced
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert (
        hass.states.get("sensor.neopool_cell_runtime_since_reset").state
        == STATE_UNKNOWN
    )


# CUSTOM-ONLY END


async def test_sensor_unavailable_in_winter_mode(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    """Sensors are unavailable while winter mode is active.

    The device is offline, so read-only entities report unavailable rather
    than unknown, matching the control entities.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Winter Pool",
        unique_id="neopool_winter_sensor",
        version=CURRENT_VERSION,
        pref_disable_polling=True,
        data={
            "host": "192.0.2.9",
            "port": 502,
            "name": "Winter Pool",
            CONF_UNIT_ID: 1,
            CONF_MODBUS_FRAMER: "tcp",
        },
        options={
            CONF_MODBUS_FRAMER: "tcp",
            CONF_CAPABILITIES: {"MBF_PAR_FILT_GPIO": 1},
        },
    )
    await setup_integration(hass, entry)

    entries = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    sensors = [
        e for e in entries if e.domain == SENSOR_DOMAIN and e.disabled_by is None
    ]
    assert sensors
    for sensor in sensors:
        state = hass.states.get(sensor.entity_id)
        assert state is not None
        assert state.state == STATE_UNAVAILABLE
