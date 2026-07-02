"""Tests for the NeoPool sensor platform."""

from datetime import timedelta as _td
from unittest.mock import AsyncMock, MagicMock, patch

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache_with_extra_data,
)
from syrupy.assertion import SnapshotAssertion

from custom_components.neopool.const import CURRENT_VERSION, DOMAIN
from custom_components.neopool.sensor import SENSOR_DESCRIPTIONS
from homeassistant.components.sensor import ATTR_OPTIONS
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, STATE_UNKNOWN, Platform
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er

from . import setup_integration
from .conftest import MOCK_POOL_DATA, MOCK_SERIAL

# Map internal sensor keys (used by SENSOR_DESCRIPTIONS) to their public
# entity_ids. Keeping the mapping in one place avoids hard-coding the same
# translation-key-derived slugs at every call site.
_ENTITY_ID_BY_KEY = {
    "MBF_MEASURE_TEMPERATURE": "sensor.neopool_water_temperature",
    "MBF_MEASURE_PH": "sensor.neopool_ph_level",
    "MBF_MEASURE_RX": "sensor.neopool_redox_potential",
    "MBF_MEASURE_CL": "sensor.neopool_salt_level",
    "MBF_MEASURE_CONDUCTIVITY": "sensor.neopool_conductivity_level",
    "MBF_HIDRO_CURRENT": "sensor.neopool_hydrolysis_intensity",
    "MBF_HIDRO_VOLTAGE": "sensor.neopool_hydrolysis_voltage",
    "MBF_ION_CURRENT": "sensor.neopool_ionization_level",
    "MBF_PAR_FILT_MODE": "sensor.neopool_filtration_mode",
    "PH_PUMP_STATUS": "sensor.neopool_ph_pump_status",
    "CELL_RUNTIME_TOTAL": "sensor.neopool_cell_runtime_total",
    "CELL_RUNTIME_PART": "sensor.neopool_cell_runtime_since_reset",
    "CELL_RUNTIME_POLA": "sensor.neopool_cell_runtime_in_polarity_1",
    "CELL_RUNTIME_POLB": "sensor.neopool_cell_runtime_in_polarity_2",
    "CELL_RUNTIME_POL_CHANGES": "sensor.neopool_cell_polarity_changes",
}


# ---------------------------------------------------------------------------
# Measurement suppressed when filtration is off
# ---------------------------------------------------------------------------


async def test_temperature_sensor_suppressed_when_filtration_off(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Temperature sensor is unknown while the filtration pump is off."""
    await setup_integration(hass, mock_config_entry)
    entity_id = _ENTITY_ID_BY_KEY["MBF_MEASURE_TEMPERATURE"]
    mock_neopool_client.async_read_all.return_value = {
        **MOCK_POOL_DATA,
        "Filtration Pump": False,
    }
    freezer.tick(_td(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_UNKNOWN

    # measure_when_filtration_off=True flips the gate.
    new_options = dict(mock_config_entry.options)
    new_options["measure_when_filtration_off"] = True
    hass.config_entries.async_update_entry(mock_config_entry, options=new_options)
    freezer.tick(_td(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == str(
        MOCK_POOL_DATA["MBF_MEASURE_TEMPERATURE"]
    )


@pytest.mark.parametrize(
    "key",
    [
        "MBF_MEASURE_PH",
        "MBF_MEASURE_RX",
        "MBF_MEASURE_CL",
        "MBF_MEASURE_CONDUCTIVITY",
    ],
)
async def test_measurement_sensors_suppressed_when_filtration_off(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    freezer: FrozenDateTimeFactory,
    key: str,
) -> None:
    """Probe sensors are unknown while filtration pump is off (stale reading)."""
    await setup_integration(hass, mock_config_entry)
    entity_id = _ENTITY_ID_BY_KEY[key]
    mock_neopool_client.async_read_all.return_value = {
        **MOCK_POOL_DATA,
        "Filtration Pump": False,
    }
    freezer.tick(_td(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_UNKNOWN

    new_options = dict(mock_config_entry.options)
    new_options["measure_when_filtration_off"] = True
    hass.config_entries.async_update_entry(mock_config_entry, options=new_options)
    freezer.tick(_td(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == str(MOCK_POOL_DATA[key])


@pytest.mark.parametrize(
    "key",
    [
        "MBF_HIDRO_CURRENT",
        "MBF_HIDRO_VOLTAGE",
        "MBF_ION_CURRENT",
    ],
)
async def test_production_sensors_zero_when_filtration_off(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    freezer: FrozenDateTimeFactory,
    key: str,
) -> None:
    """Production sensors report 0 while filtration pump is off (cell idle)."""
    # MBF_HIDRO_VOLTAGE is entity_registry_enabled_default=False; pre-register
    # it as enabled so the platform constructs the entity and drives its state.
    mock_config_entry.add_to_hass(hass)
    registry = er.async_get(hass)
    if not SENSOR_DESCRIPTIONS[key].entity_registry_enabled_default:
        entry = registry.async_get_or_create(
            "sensor",
            DOMAIN,
            f"{MOCK_SERIAL}_{key.lower()}",
            config_entry=mock_config_entry,
            disabled_by=None,
        )
        entity_id = entry.entity_id
    else:
        entity_id = _ENTITY_ID_BY_KEY[key]
    await setup_integration(hass, mock_config_entry)
    mock_neopool_client.async_read_all.return_value = {
        **MOCK_POOL_DATA,
        "Filtration Pump": False,
    }
    freezer.tick(_td(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "0"

    new_options = dict(mock_config_entry.options)
    new_options["measure_when_filtration_off"] = True
    hass.config_entries.async_update_entry(mock_config_entry, options=new_options)
    freezer.tick(_td(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == str(MOCK_POOL_DATA[key])


# ---------------------------------------------------------------------------
# Filt mode / filtration speed / pH status alarm options
# ---------------------------------------------------------------------------


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
    freezer.tick(_td(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(_ENTITY_ID_BY_KEY["MBF_PAR_FILT_MODE"]).state == expected


async def test_filtration_pump_energy_sensor_registers_when_power_set(
    hass: HomeAssistant,
    mock_neopool_client: MagicMock,
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
            "unit_id": 1,
            "modbus_framer": "tcp",
        },
        options={
            "modbus_framer": "tcp",
            "filtration_pump_power": 800,  # 800 W → energy sensor enabled
        },
    )
    await setup_integration(hass, entry)
    registry = er.async_get(hass)
    entries = [
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "sensor" and e.unique_id.endswith("_filtration_pump_energy")
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
            "unit_id": 1,
            "modbus_framer": "tcp",
        },
        options={
            "modbus_framer": "tcp",
            "filtration_pump_power": 1000,
        },
    )
    await setup_integration(hass, entry)

    entity_id = "sensor.neopool_filtration_pump_energy"
    assert hass.states.get(entity_id) is not None

    # Prime _last_update to "now"; the previous state carries 0 Wh so this is
    # the reference point for the elapsed-time integration.
    coordinator = entry.runtime_data
    coordinator._last_pump_on = True  # simulate prior on-state
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()
    initial_wh = float(hass.states.get(entity_id).state)

    # Advance wall clock by an hour and let another coordinator update roll
    # through; the sensor should integrate 1 kW x 1 h = ~1 kWh.
    freezer.tick(_td(hours=1))
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()
    later_wh = float(hass.states.get(entity_id).state)
    # State is in kWh (unit conversion Wh -> kWh); expect at least 0.9 kWh.
    assert later_wh - initial_wh >= 0.9


async def test_filtration_pump_energy_restores_native_value_after_restart(
    hass: HomeAssistant,
    mock_neopool_client: MagicMock,
) -> None:
    """RestoreSensor recovers the previous Wh counter after a HA restart."""
    fake_state = State(
        "sensor.neopool_filtration_pump_energy",
        STATE_UNKNOWN,
    )
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
            "unit_id": 1,
            "modbus_framer": "tcp",
        },
        options={
            "modbus_framer": "tcp",
            "filtration_pump_power": 1000,
        },
    )
    await setup_integration(hass, entry)

    entity_id = "sensor.neopool_filtration_pump_energy"
    state = hass.states.get(entity_id)
    assert state is not None
    # The persisted Wh counter is the starting point for further accumulation.
    # HA converts Wh -> kWh via _attr_suggested_unit_of_measurement, so the
    # exposed state value is 12345.6 Wh / 1000 = 12.3456 kWh.
    assert float(state.state) == pytest.approx(12.3456)


async def test_filtration_pump_energy_ignores_non_numeric_restore(
    hass: HomeAssistant,
    mock_neopool_client: MagicMock,
) -> None:
    """A non-numeric restored native_value does not corrupt the counter."""
    fake_state = State(
        "sensor.neopool_filtration_pump_energy",
        STATE_UNKNOWN,
    )
    # `native_value` typed as Decimal/datetime/date isn't valid for an energy
    # counter, the entity must reject it and start at 0 instead of crashing
    # the float() conversion.
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
            "unit_id": 1,
            "modbus_framer": "tcp",
        },
        options={
            "modbus_framer": "tcp",
            "filtration_pump_power": 1000,
        },
    )
    await setup_integration(hass, entry)

    entity_id = "sensor.neopool_filtration_pump_energy"
    state = hass.states.get(entity_id)
    assert state is not None
    # Restore was rejected, counter starts at 0.
    assert float(state.state) == 0


async def test_ph_pump_status_options_per_relay_config(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The pH pump status options list shrinks based on the relay configuration."""
    await setup_integration(hass, mock_config_entry)
    entity_id = _ENTITY_ID_BY_KEY["PH_PUMP_STATUS"]

    for relay, expected_options in (
        (1, ["off", "idle", "acid"]),
        (2, ["off", "idle", "base"]),
        (0, ["off", "idle", "acid", "base", "both"]),
    ):
        mock_neopool_client.async_read_all.return_value = {
            **MOCK_POOL_DATA,
            "MBF_PAR_RELAY_PH": relay,
        }
        freezer.tick(_td(seconds=60))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).attributes[ATTR_OPTIONS] == expected_options


async def test_hidro_current_g_per_hour_mode(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """In g/h mode HIDRO_CURRENT swaps unit and bumps display precision.

    HIDROLIFE machines (MBF_PAR_UICFG_MACHINE=1) display hydrolysis as g/h
    rather than %; the sensor adapts unit + precision accordingly.
    """
    await setup_integration(hass, mock_config_entry)
    # HIDROLIFE machine type → is_hydrolysis_in_percent returns False.
    mock_neopool_client.async_read_all.return_value = {
        **MOCK_POOL_DATA,
        "MBF_PAR_UICFG_MACHINE": 1,
    }
    freezer.tick(_td(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    state = hass.states.get(_ENTITY_ID_BY_KEY["MBF_HIDRO_CURRENT"])
    assert state is not None
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == "g/h"


# ---------------------------------------------------------------------------
# Cell runtime 32-bit counters (issue #177)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "expected_seconds"),
    [
        # Total = (0x0001 << 16) | 0x0000 = 65 536 s (~18.2 h)
        ("CELL_RUNTIME_TOTAL", 65536),
        # Partial = (0x0000 << 16) | 0x0E10 = 3600 s (1 h)
        ("CELL_RUNTIME_PART", 3600),
        # Polarity 1 = (0x0000 << 16) | 0x0708 = 1800 s
        ("CELL_RUNTIME_POLA", 1800),
        # Polarity 2 = (0x0000 << 16) | 0x0708 = 1800 s
        ("CELL_RUNTIME_POLB", 1800),
        # Polarity changes = 7
        ("CELL_RUNTIME_POL_CHANGES", 7),
    ],
)
async def test_cell_runtime_sensor_reads_combined_register(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    key: str,
    expected_seconds: int,
) -> None:
    """Each CELL_RUNTIME_* sensor reads the combined u32 key from coordinator data.

    All five sensors have ``entity_registry_enabled_default=False`` (CELL_RUNTIME_TOTAL
    and CELL_RUNTIME_PART because the user opted into the diagnostic level
    consciously, POLA/POLB/POL_CHANGES because they're advanced internals);
    HA skips constructing entity objects for disabled-by-default keys, so we
    pre-register them as enabled in the entity_registry and let the platform
    setup pick that up.
    """
    mock_config_entry.add_to_hass(hass)
    registry = er.async_get(hass)
    entry = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{MOCK_SERIAL}_{key.lower()}",
        config_entry=mock_config_entry,
        disabled_by=None,
    )

    await setup_integration(hass, mock_config_entry)
    # Pre-registration locks the entity_id to the unique_id-derived slug rather
    # than the translation_key one, so look up the live entity_id via the
    # registry instead of using the _ENTITY_ID_BY_KEY mapping.
    assert hass.states.get(entry.entity_id).state == str(expected_seconds)


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
            "unit_id": 1,
            "modbus_framer": "tcp",
        },
        options={"modbus_framer": "tcp"},
    )
    await setup_integration(hass, entry)

    registry = er.async_get(hass)
    cell_entities = [
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "sensor" and "cell_runtime" in e.unique_id
    ]
    assert cell_entities == []


async def test_cell_runtime_sensor_returns_none_when_key_missing(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Sensor returns None when the combined key is absent from coordinator data."""
    # CELL_RUNTIME_PART is disabled-by-default; pre-enable it so the platform
    # constructs the entity object whose native_value we can inspect.
    mock_config_entry.add_to_hass(hass)
    registry = er.async_get(hass)
    entry = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{MOCK_SERIAL}_cell_runtime_part",
        config_entry=mock_config_entry,
        disabled_by=None,
    )
    await setup_integration(hass, mock_config_entry)
    # Drop the combined key from the next read entirely so the sensor sees None.
    reduced = {k: v for k, v in MOCK_POOL_DATA.items() if k != "CELL_RUNTIME_PART"}
    mock_neopool_client.async_read_all.return_value = reduced
    freezer.tick(_td(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get(entry.entity_id).state == STATE_UNKNOWN


# ---------------------------------------------------------------------------
# Platform-wide snapshots
# ---------------------------------------------------------------------------


async def test_all_entities(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Snapshot every entity registered by the sensor platform.

    Snapshot the registry entries directly rather than via
    `snapshot_platform`, which assumes every entity is enabled and has
    state. NeoPool ships several `entity_registry_enabled_default=False`
    entities; including them via state lookup would either fail or pull
    entire state machines into the snapshot. The registry entry alone
    (unique_id, name, disabled_by, ...) is the stable shape we care about.
    """
    with patch("custom_components.neopool.PLATFORMS", [Platform.SENSOR]):
        await setup_integration(hass, mock_config_entry)
    entries = sorted(
        er.async_entries_for_config_entry(entity_registry, mock_config_entry.entry_id),
        key=lambda e: e.entity_id,
    )
    assert entries == snapshot


async def test_setup_when_modules_absent(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client_minimal: MagicMock,
) -> None:
    """Snapshot the sensor entities registered when no modules are present.

    Drives setup with the lean `mock_neopool_client_minimal` fixture (no
    modules detected, no relay GPIOs assigned). Each platform's gating
    branches fire and entities depending on the missing hardware are
    skipped; the resulting registry shape is captured as a snapshot.
    """
    with patch("custom_components.neopool.PLATFORMS", [Platform.SENSOR]):
        await setup_integration(hass, mock_config_entry)
    entries = sorted(
        er.async_entries_for_config_entry(entity_registry, mock_config_entry.entry_id),
        key=lambda e: e.entity_id,
    )
    assert entries == snapshot
