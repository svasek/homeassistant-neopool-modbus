"""Tests for the NeoPool sensor platform value decoders."""

from datetime import timedelta as _td
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.neopool.const import CURRENT_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform as ep, entity_registry as er

from . import setup_integration
from .conftest import MOCK_POOL_DATA


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
    """Drive _compute_ph_pump_status through every relay_ph branch."""
    await setup_integration(hass, mock_config_entry)
    entity = _sensor_by_key(hass, "PH_PUMP_STATUS")
    if entity is None:
        pytest.skip("PH_PUMP_STATUS entity not registered on this fixture")
    coordinator = mock_config_entry.runtime_data
    coordinator.data.update(data)
    assert entity._compute_ph_pump_status() == expected


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
    """Drive _compute_hidro_polarity through every polarity / flow branch."""
    await setup_integration(hass, mock_config_entry)
    entity = _sensor_by_key(hass, "HIDRO_POLARITY")
    if entity is None:
        pytest.skip("HIDRO_POLARITY entity not registered")
    coordinator = mock_config_entry.runtime_data
    # Reset polarity-related keys before each parametrization so prior
    # state doesn't leak.
    for k in (
        "HIDRO in Pol1",
        "HIDRO in Pol2",
        "HIDRO in dead time",
        "Filtration Pump",
        "HIDRO Cell Flow FL1",
    ):
        coordinator.data.pop(k, None)
    coordinator.data.update(data)
    assert entity._compute_hidro_polarity() == expected


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
    """Drive _compute_ion_polarity through every branch."""
    await setup_integration(hass, mock_config_entry)
    entity = _sensor_by_key(hass, "ION_POLARITY")
    if entity is None:
        pytest.skip("ION_POLARITY entity not registered")
    coordinator = mock_config_entry.runtime_data
    for k in ("ION in Pol1", "ION in Pol2", "ION in dead time"):
        coordinator.data.pop(k, None)
    coordinator.data.update(data)
    assert entity._compute_ion_polarity() == expected


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
    """Filt mode native value resolves the int through FILTRATION_MODE_MAP."""
    await setup_integration(hass, mock_config_entry)
    entity = _sensor_by_key(hass, "MBF_PAR_FILT_MODE")
    assert entity is not None
    coordinator = mock_config_entry.runtime_data
    coordinator.data["MBF_PAR_FILT_MODE"] = filt_mode
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
            "slave_id": 1,
            "modbus_framer": "tcp",
        },
        options={
            "scan_interval": 30,
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
    freezer,
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
            "slave_id": 1,
            "modbus_framer": "tcp",
        },
        options={
            "scan_interval": 30,
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
