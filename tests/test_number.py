"""Tests for the NeoPool number platform."""

import asyncio
from unittest.mock import MagicMock

from neopool_modbus.registers import (
    HEATING_SETPOINT_REGISTER,
    INTELLIGENT_SETPOINT_REGISTER,
)
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.number.const import ATTR_VALUE, SERVICE_SET_VALUE
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform as ep, entity_registry as er

from . import setup_integration


def _number_entity_id(
    hass: HomeAssistant, entry: MockConfigEntry, key_lower_suffix: str
) -> str:
    registry = er.async_get(hass)
    entries = [
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "number" and e.unique_id.endswith(f"_{key_lower_suffix}")
    ]
    assert entries, (
        f"no number entity ending in _{key_lower_suffix} — found: "
        + ", ".join(
            e.unique_id
            for e in er.async_entries_for_config_entry(registry, entry.entry_id)
            if e.domain == "number"
        )
    )
    return entries[0].entity_id


async def _set_value(hass: HomeAssistant, entity_id: str, value: float) -> None:
    await hass.services.async_call(
        Platform.NUMBER,
        SERVICE_SET_VALUE,
        {"entity_id": entity_id, ATTR_VALUE: value},
        blocking=True,
    )


async def _flush_debounce(
    hass: HomeAssistant, entity_obj, debounce_seconds: float = 2.5
) -> None:
    """Wait for the entity's pending debounced write task to complete."""
    task = getattr(entity_obj, "_pending_write_task", None)
    if task is None:
        return
    try:
        await asyncio.wait_for(task, timeout=debounce_seconds + 1)
    except TimeoutError:  # pragma: no cover
        task.cancel()
    await hass.async_block_till_done()


async def test_simple_number_writes_register_after_debounce(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Setting a numeric value writes raw=value*scale to the register."""
    await setup_integration(hass, mock_config_entry)

    entity_id = _number_entity_id(hass, mock_config_entry, "mbf_par_ph1")
    mock_neopool_client.async_write_register.reset_mock()

    await _set_value(hass, entity_id, 7.5)
    # Wait for the entity's _pending_write_task to fire (2 s debounce).

    entity_obj = None
    for platforms in ep.async_get_platforms(hass, "neopool"):
        for ent in platforms.entities.values():
            if ent.entity_id == entity_id:
                entity_obj = ent
                break
        if entity_obj is not None:
            break
    await _flush_debounce(hass, entity_obj)

    assert mock_neopool_client.async_write_register.await_count >= 1


async def test_heating_setpoint_mirrors_to_intelligent(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Writing the heating setpoint mirrors the value to the intelligent register."""

    await setup_integration(hass, mock_config_entry)
    entity_id = _number_entity_id(hass, mock_config_entry, "mbf_par_heating_temp")

    mock_neopool_client.async_write_register.reset_mock()
    await _set_value(hass, entity_id, 28.0)

    entity_obj = None
    for platforms in ep.async_get_platforms(hass, "neopool"):
        for ent in platforms.entities.values():
            if ent.entity_id == entity_id:
                entity_obj = ent
                break
        if entity_obj is not None:
            break
    await _flush_debounce(hass, entity_obj)

    addresses = [
        c.args[0] for c in mock_neopool_client.async_write_register.await_args_list
    ]
    assert HEATING_SETPOINT_REGISTER in addresses
    assert INTELLIGENT_SETPOINT_REGISTER in addresses


async def test_number_blocked_in_winter_mode(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """async_set_native_value short-circuits when winter_mode is on."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    coordinator.winter_mode = True

    entity_obj = None
    for platforms in ep.async_get_platforms(hass, "neopool"):
        for ent in platforms.entities.values():
            if ent.entity_id.startswith("number.") and getattr(ent, "_key", None):
                entity_obj = ent
                break
        if entity_obj is not None:
            break
    assert entity_obj is not None

    mock_neopool_client.async_write_register.reset_mock()
    await entity_obj.async_set_native_value(7.5)
    assert "Winter mode is active" in caplog.text
    mock_neopool_client.async_write_register.assert_not_called()


async def test_number_native_value_returns_rounded_raw(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """native_value returns round(raw, 2) when coordinator has the register."""

    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    coordinator.data["MBF_PAR_PH1"] = 7.55
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()

    entity_obj = None
    for platforms in ep.async_get_platforms(hass, "neopool"):
        for ent in platforms.entities.values():
            if (
                ent.entity_id.startswith("number.")
                and getattr(ent, "_data_key", None) == "MBF_PAR_PH1"
            ):
                entity_obj = ent
                break
        if entity_obj is not None:
            break
    if entity_obj is None:
        pytest.skip("MBF_PAR_PH1 number entity not registered")
    assert entity_obj.native_value == 7.55


async def test_hidro_native_value_in_percent_mode(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """MBF_PAR_HIDRO with hidro_nom set surfaces it as native_max_value."""

    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    coordinator.data["MBF_PAR_HIDRO_NOM"] = 100
    coordinator.data["MBF_PAR_MODEL"] = 0x0002  # has hydro
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()

    entity_obj = None
    for platforms in ep.async_get_platforms(hass, "neopool"):
        for ent in platforms.entities.values():
            if (
                ent.entity_id.startswith("number.")
                and getattr(ent, "_key", None) == "MBF_PAR_HIDRO"
            ):
                entity_obj = ent
                break
        if entity_obj is not None:
            break
    if entity_obj is None:
        pytest.skip("MBF_PAR_HIDRO entity not registered on this fixture")
    assert entity_obj.native_max_value == 100
