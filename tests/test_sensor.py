"""Tests for the NeoPool sensor platform value decoders."""

from datetime import timedelta as _td
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from freezegun.api import FrozenDateTimeFactory
from neopool_modbus.decoders import (
    decode_hidro_polarity,
    decode_ion_polarity,
    decode_ph_pump_status,
)
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache_with_extra_data,
)
from syrupy.assertion import SnapshotAssertion

from custom_components.neopool.const import CURRENT_VERSION, DOMAIN
from custom_components.neopool.sensor import SENSOR_DESCRIPTIONS
from homeassistant.const import STATE_UNKNOWN, Platform
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_platform as ep, entity_registry as er

from . import setup_integration
from .conftest import MOCK_POOL_DATA, MOCK_SERIAL


def _sensor_by_key(hass: HomeAssistant, key: str):
    """Return the live sensor entity object for a given _key, or None."""
    for platforms in ep.async_get_platforms(hass, "neopool"):
        for ent in platforms.entities.values():
            if (
                ent.entity_id.startswith("sensor.")
                and getattr(ent, "_key", None) == key
            ):
                return ent
    return None


def _minimum_pool_data() -> dict[str, Any]:
    """Return a copy of the default fixture's pool data for ad-hoc test entries."""

    return dict(MOCK_POOL_DATA)


# ---------------------------------------------------------------------------
# pH pump status
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        # All bits None → unknown
        ({}, None),
        # ctrl None but other bits present → still unknown (partial data)
        ({"pH acid pump active": True}, None),
        # ctrl off → "off"
        (
            {
                "pH control module": False,
                "pH acid pump active": False,
                "pH pump active": False,
            },
            "off",
        ),
        # acid-only relay (1): pump_bit drives acid
        (
            {
                "pH control module": True,
                "MBF_PAR_RELAY_PH": 1,
                "pH pump active": True,
                "pH acid pump active": False,
            },
            "acid",
        ),
        (
            {
                "pH control module": True,
                "MBF_PAR_RELAY_PH": 1,
                "pH pump active": False,
                "pH acid pump active": False,
            },
            "idle",
        ),
        # base-only relay (2)
        (
            {
                "pH control module": True,
                "MBF_PAR_RELAY_PH": 2,
                "pH pump active": True,
                "pH acid pump active": False,
            },
            "base",
        ),
        (
            {
                "pH control module": True,
                "MBF_PAR_RELAY_PH": 2,
                "pH pump active": False,
                "pH acid pump active": False,
            },
            "idle",
        ),
        # both pumps (0): individual bits
        (
            {
                "pH control module": True,
                "MBF_PAR_RELAY_PH": 0,
                "pH pump active": True,
                "pH acid pump active": True,
            },
            "both",
        ),
        (
            {
                "pH control module": True,
                "MBF_PAR_RELAY_PH": 0,
                "pH pump active": False,
                "pH acid pump active": True,
            },
            "acid",
        ),
        (
            {
                "pH control module": True,
                "MBF_PAR_RELAY_PH": 0,
                "pH pump active": True,
                "pH acid pump active": False,
            },
            "base",
        ),
        (
            {
                "pH control module": True,
                "MBF_PAR_RELAY_PH": 0,
                "pH pump active": False,
                "pH acid pump active": False,
            },
            "idle",
        ),
    ],
)
async def test_ph_pump_status_decoder(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    data: dict[str, Any],
    expected: str | None,
) -> None:
    """decode_ph_pump_status covers every relay_ph branch."""
    assert decode_ph_pump_status(data) == expected


# ---------------------------------------------------------------------------
# Hydrolysis polarity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({}, None),  # no polarity bits
        # filtration off → off
        (
            {
                "HIDRO in Pol1": False,
                "HIDRO in Pol2": False,
                "HIDRO in dead time": False,
                "Filtration Pump": False,
            },
            "off",
        ),
        # filtration on but no flow → no_flow
        (
            {
                "HIDRO in Pol1": False,
                "HIDRO in Pol2": False,
                "HIDRO in dead time": False,
                "Filtration Pump": True,
                "HIDRO Cell Flow FL1": False,
            },
            "no_flow",
        ),
        # filtration on, flow ok, no polarity / dead bits → final 'off' fallback
        (
            {
                "HIDRO in Pol1": False,
                "HIDRO in Pol2": False,
                "HIDRO in dead time": False,
                "Filtration Pump": True,
                "HIDRO Cell Flow FL1": True,
            },
            "off",
        ),
        # dead time wins
        (
            {"HIDRO in Pol1": True, "HIDRO in Pol2": False, "HIDRO in dead time": True},
            "dead_time",
        ),
        # pol1
        (
            {
                "HIDRO in Pol1": True,
                "HIDRO in Pol2": False,
                "HIDRO in dead time": False,
            },
            "pol1",
        ),
        # pol2
        (
            {
                "HIDRO in Pol1": False,
                "HIDRO in Pol2": True,
                "HIDRO in dead time": False,
            },
            "pol2",
        ),
    ],
)
async def test_hidro_polarity_decoder(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    data: dict[str, Any],
    expected: str | None,
) -> None:
    """decode_hidro_polarity covers every polarity / flow branch."""
    assert decode_hidro_polarity(data) == expected


# ---------------------------------------------------------------------------
# Ion polarity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({}, None),
        (
            {"ION in Pol1": True, "ION in Pol2": False, "ION in dead time": True},
            "dead_time",
        ),
        (
            {"ION in Pol1": True, "ION in Pol2": False, "ION in dead time": False},
            "pol1",
        ),
        (
            {"ION in Pol1": False, "ION in Pol2": True, "ION in dead time": False},
            "pol2",
        ),
        (
            {"ION in Pol1": False, "ION in Pol2": False, "ION in dead time": False},
            "off",
        ),
    ],
)
async def test_ion_polarity_decoder(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    data: dict[str, Any],
    expected: str | None,
) -> None:
    """decode_ion_polarity covers every branch."""
    assert decode_ion_polarity(data) == expected


# ---------------------------------------------------------------------------
# Measurement suppressed when filtration is off
# ---------------------------------------------------------------------------


async def test_temperature_sensor_suppressed_when_filtration_off(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Temperature sensor returns None while the filtration pump is off."""
    await setup_integration(hass, mock_config_entry)
    entity = _sensor_by_key(hass, "MBF_MEASURE_TEMPERATURE")
    if entity is None:
        pytest.skip("temperature entity not registered")
    coordinator = mock_config_entry.runtime_data
    coordinator.data["Filtration Pump"] = False
    assert entity.native_value is None

    # measure_when_filtration_off=True flips the gate.
    new_options = dict(mock_config_entry.options)
    new_options["measure_when_filtration_off"] = True
    hass.config_entries.async_update_entry(mock_config_entry, options=new_options)
    await hass.async_block_till_done()
    assert entity.native_value == coordinator.data.get("MBF_MEASURE_TEMPERATURE")


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
    filt_mode: int,
    expected: str,
) -> None:
    """Filt mode native value reads the lib's decoded filtration_mode key."""
    await setup_integration(hass, mock_config_entry)
    entity = _sensor_by_key(hass, "MBF_PAR_FILT_MODE")
    assert entity is not None
    coordinator = mock_config_entry.runtime_data
    coordinator.data["MBF_PAR_FILT_MODE"] = filt_mode
    coordinator.data["filtration_mode"] = expected
    assert entity.native_value == expected


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

    pump_data = dict(_minimum_pool_data())
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

    entity_obj = None
    for platforms in ep.async_get_platforms(hass, "neopool"):
        for ent in platforms.entities.values():
            if ent.entity_id.startswith("sensor.") and "filtration_pump_energy" in (
                getattr(ent, "_attr_unique_id", "") or ""
            ):
                entity_obj = ent
                break
        if entity_obj is not None:
            break
    assert entity_obj is not None

    # Drive the coordinator update with a 1-hour gap between two ticks.
    coordinator = entry.runtime_data
    coordinator._last_pump_on = True  # simulate prior on-state
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()

    initial_wh = entity_obj.native_value
    freezer.tick(_td(hours=1))
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()
    later_wh = entity_obj.native_value
    # 1 kW for 1 h → ~1000 Wh delta (allow rounding slack).
    assert later_wh - initial_wh >= 900


async def test_filtration_pump_energy_restores_native_value_after_restart(
    hass: HomeAssistant,
    mock_neopool_client: MagicMock,
) -> None:
    """RestoreSensor recovers the previous Wh counter after a HA restart."""
    fake_state = State(
        "sensor.pool_filtration_pump_energy",
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

    entity_obj = None
    for platforms in ep.async_get_platforms(hass, "neopool"):
        for ent in platforms.entities.values():
            if ent.entity_id.startswith("sensor.") and "filtration_pump_energy" in (
                getattr(ent, "_attr_unique_id", "") or ""
            ):
                entity_obj = ent
                break
        if entity_obj is not None:
            break
    assert entity_obj is not None
    # The persisted Wh counter is the starting point for further accumulation.
    assert entity_obj.native_value == pytest.approx(12345.6)


async def test_filtration_pump_energy_ignores_non_numeric_restore(
    hass: HomeAssistant,
    mock_neopool_client: MagicMock,
) -> None:
    """A non-numeric restored native_value does not corrupt the counter."""
    fake_state = State(
        "sensor.pool_filtration_pump_energy",
        STATE_UNKNOWN,
    )
    # `native_value` typed as Decimal/datetime/date isn't valid for an energy
    # counter — the entity must reject it and start at 0 instead of crashing
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

    entity_obj = None
    for platforms in ep.async_get_platforms(hass, "neopool"):
        for ent in platforms.entities.values():
            if ent.entity_id.startswith("sensor.") and "filtration_pump_energy" in (
                getattr(ent, "_attr_unique_id", "") or ""
            ):
                entity_obj = ent
                break
        if entity_obj is not None:
            break
    assert entity_obj is not None
    # Restore was rejected — counter starts at 0.
    assert entity_obj.native_value == 0


async def test_ph_pump_status_options_per_relay_config(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """The pH pump status options list shrinks based on the relay configuration."""
    await setup_integration(hass, mock_config_entry)
    entity = _sensor_by_key(hass, "PH_PUMP_STATUS")
    if entity is None:
        pytest.skip("PH_PUMP_STATUS entity not registered")
    coordinator = mock_config_entry.runtime_data
    coordinator.data["MBF_PAR_RELAY_PH"] = 1
    assert entity.options == ["off", "idle", "acid"]
    coordinator.data["MBF_PAR_RELAY_PH"] = 2
    assert entity.options == ["off", "idle", "base"]
    coordinator.data["MBF_PAR_RELAY_PH"] = 0
    assert entity.options == ["off", "idle", "acid", "base", "both"]


async def test_hidro_current_g_per_hour_mode(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """In g/h mode HIDRO_CURRENT swaps unit and bumps display precision.

    HIDROLIFE machines (MBF_PAR_UICFG_MACHINE=1) display hydrolysis as g/h
    rather than %; the sensor adapts unit + precision accordingly.
    """
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    # HIDROLIFE machine type → is_hydrolysis_in_percent returns False.
    coordinator.data["MBF_PAR_UICFG_MACHINE"] = 1
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()

    entity = _sensor_by_key(hass, "MBF_HIDRO_CURRENT")
    if entity is None:
        pytest.skip("MBF_HIDRO_CURRENT entity not registered on this fixture")
    assert entity.suggested_display_precision == 1
    assert entity.native_unit_of_measurement == "g/h"


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
    registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"neopool_{MOCK_SERIAL}_{key.lower()}",
        config_entry=mock_config_entry,
        disabled_by=None,
    )

    await setup_integration(hass, mock_config_entry)
    entity = _sensor_by_key(hass, key)
    assert entity is not None, f"{key} sensor was not registered"
    assert entity.native_value == expected_seconds


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
) -> None:
    """Sensor returns None when the combined key is absent from coordinator data."""
    # CELL_RUNTIME_PART is disabled-by-default; pre-enable it so the platform
    # constructs the entity object whose native_value we can inspect.
    mock_config_entry.add_to_hass(hass)
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"neopool_{MOCK_SERIAL}_cell_runtime_part",
        config_entry=mock_config_entry,
        disabled_by=None,
    )
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    # Remove the combined key entirely -- coordinator.data.get() returns None.
    coordinator.data.pop("CELL_RUNTIME_PART", None)
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()

    entity = _sensor_by_key(hass, "CELL_RUNTIME_PART")
    assert entity is not None
    assert entity.native_value is None


async def test_cell_runtime_default_enabled_state(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """All five cell-runtime sensors default to disabled.

    Cell-life metrics are diagnostic information rather than headline state;
    surfacing them silently in every install would clutter dashboards. Users
    who care about cell-life can enable the sensors explicitly in the entity
    registry.
    """

    for key in (
        "CELL_RUNTIME_TOTAL",
        "CELL_RUNTIME_PART",
        "CELL_RUNTIME_POLA",
        "CELL_RUNTIME_POLB",
        "CELL_RUNTIME_POL_CHANGES",
    ):
        assert SENSOR_DESCRIPTIONS[key].entity_registry_enabled_default is False


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
