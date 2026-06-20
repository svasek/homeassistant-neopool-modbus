"""Tests for the NeoPool time platform."""

import asyncio
from datetime import time as dt_time
from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.time import DOMAIN as TIME_DOMAIN, SERVICE_SET_VALUE
from homeassistant.const import ATTR_TIME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform as ep, entity_registry as er

from . import setup_integration


def _time_entity_id(
    hass: HomeAssistant, entry: MockConfigEntry, key_lower_suffix: str
) -> str:
    """Resolve a time entity by its trailing unique_id segment."""
    registry = er.async_get(hass)
    entries = [
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "time" and e.unique_id.endswith(f"_{key_lower_suffix}")
    ]
    assert entries, (
        f"no time entity ending in _{key_lower_suffix} - found: "
        + ", ".join(
            e.unique_id
            for e in er.async_entries_for_config_entry(registry, entry.entry_id)
            if e.domain == "time"
        )
    )
    return entries[0].entity_id


async def _set_time(hass: HomeAssistant, entity_id: str, value: dt_time) -> None:
    await hass.services.async_call(
        TIME_DOMAIN,
        SERVICE_SET_VALUE,
        {"entity_id": entity_id, ATTR_TIME: value},
        blocking=True,
    )


def _time_entity(hass: HomeAssistant, entity_id: str):
    """Resolve the live entity object for a time.* entity_id."""
    for platforms in ep.async_get_platforms(hass, "neopool"):
        for ent in platforms.entities.values():
            if ent.entity_id == entity_id:
                return ent
    return None  # pragma: no cover


def _disable_debounce(hass: HomeAssistant) -> None:
    """Set _debounce_delay = 0 on every time entity."""
    for platforms in ep.async_get_platforms(hass, "neopool"):
        for ent in platforms.entities.values():
            if ent.entity_id.startswith("time."):
                ent._debounce_delay = 0


async def _flush_debounce(hass: HomeAssistant, entity_obj) -> None:
    """Wait for the entity's pending debounced write task."""
    task = getattr(entity_obj, "_pending_write_task", None)
    if task is None:
        return
    await asyncio.wait_for(task, timeout=1)
    await hass.async_block_till_done()


# ---------------------------------------------------------------------------
# native_value
# ---------------------------------------------------------------------------


async def test_native_value_decodes_seconds_since_midnight(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Coordinator seconds become HH:MM:SS state."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    coordinator.data["filtration1_start"] = 6 * 3600 + 30 * 60  # 06:30
    coordinator.async_set_updated_data(coordinator.data)

    entity_id = _time_entity_id(hass, mock_config_entry, "filtration1_start")
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "06:30:00"


async def test_native_value_returns_none_when_data_missing(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Missing coordinator key surfaces as 'unknown'."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    coordinator.data.pop("filtration1_start", None)
    coordinator.async_set_updated_data(coordinator.data)

    entity_id = _time_entity_id(hass, mock_config_entry, "filtration1_start")
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "unknown"


async def test_native_value_handles_out_of_range_seconds(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Values >= 86400 wrap modulo 86400."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    coordinator.data["filtration1_start"] = 86400 + 3600  # 25:00 -> 01:00
    coordinator.async_set_updated_data(coordinator.data)

    entity_id = _time_entity_id(hass, mock_config_entry, "filtration1_start")
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "01:00:00"


# ---------------------------------------------------------------------------
# async_set_value -> set_timer service
# ---------------------------------------------------------------------------


async def test_set_value_on_start_calls_set_timer(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Setting *_start preserves the existing stop."""
    await setup_integration(hass, mock_config_entry)
    _disable_debounce(hass)
    coordinator = mock_config_entry.runtime_data
    coordinator.data["filtration1_stop"] = 10 * 3600
    coordinator.async_set_updated_data(coordinator.data)

    entity_id = _time_entity_id(hass, mock_config_entry, "filtration1_start")
    mock_neopool_client.write_timer.reset_mock()
    await _set_time(hass, entity_id, dt_time(6, 0))
    await _flush_debounce(hass, _time_entity(hass, entity_id))

    assert mock_neopool_client.write_timer.await_count == 1
    timer_name, payload = mock_neopool_client.write_timer.await_args.args
    assert timer_name == "filtration1"
    assert payload["on"] == 6 * 3600
    assert payload["interval"] == 4 * 3600


async def test_set_value_on_stop_calls_set_timer(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Setting *_stop preserves the existing start."""
    await setup_integration(hass, mock_config_entry)
    _disable_debounce(hass)
    coordinator = mock_config_entry.runtime_data
    coordinator.data["filtration1_start"] = 6 * 3600
    coordinator.async_set_updated_data(coordinator.data)

    entity_id = _time_entity_id(hass, mock_config_entry, "filtration1_stop")
    mock_neopool_client.write_timer.reset_mock()
    await _set_time(hass, entity_id, dt_time(10, 0))
    await _flush_debounce(hass, _time_entity(hass, entity_id))

    assert mock_neopool_client.write_timer.await_count == 1
    timer_name, payload = mock_neopool_client.write_timer.await_args.args
    assert timer_name == "filtration1"
    assert payload["on"] == 6 * 3600
    assert payload["interval"] == 4 * 3600


async def test_rapid_set_value_coalesces_via_debounce(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Sibling start/stop writes both reach the device with the latest pair."""
    await setup_integration(hass, mock_config_entry)
    _disable_debounce(hass)
    coordinator = mock_config_entry.runtime_data
    coordinator.data["filtration1_start"] = 0
    coordinator.data["filtration1_stop"] = 0
    coordinator.async_set_updated_data(coordinator.data)

    start_id = _time_entity_id(hass, mock_config_entry, "filtration1_start")
    stop_id = _time_entity_id(hass, mock_config_entry, "filtration1_stop")
    start_obj = _time_entity(hass, start_id)
    stop_obj = _time_entity(hass, stop_id)

    mock_neopool_client.write_timer.reset_mock()
    await start_obj.async_set_value(dt_time(6, 0))
    await stop_obj.async_set_value(dt_time(10, 0))
    await _flush_debounce(hass, start_obj)
    await _flush_debounce(hass, stop_obj)

    timer_name, payload = mock_neopool_client.write_timer.await_args.args
    assert timer_name == "filtration1"
    assert payload["on"] == 6 * 3600
    assert payload["interval"] == 4 * 3600


async def test_repeated_set_value_on_same_entity_coalesces(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """A second set_value cancels the first pending task; only the latest writes."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    coordinator.data["filtration1_stop"] = 12 * 3600
    coordinator.async_set_updated_data(coordinator.data)

    entity_id = _time_entity_id(hass, mock_config_entry, "filtration1_start")
    entity_obj = _time_entity(hass, entity_id)
    entity_obj._debounce_delay = 0.05

    mock_neopool_client.write_timer.reset_mock()
    await entity_obj.async_set_value(dt_time(5, 0))
    await entity_obj.async_set_value(dt_time(6, 0))
    await _flush_debounce(hass, entity_obj)

    assert mock_neopool_client.write_timer.await_count == 1
    _timer_name, payload = mock_neopool_client.write_timer.await_args.args
    assert payload["on"] == 6 * 3600


# ---------------------------------------------------------------------------
# Winter mode guard
# ---------------------------------------------------------------------------


async def test_set_value_blocked_in_winter_mode(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """async_set_value short-circuits when winter_mode is on."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    coordinator.winter_mode = True

    entity_obj = None
    for platforms in ep.async_get_platforms(hass, "neopool"):
        for ent in platforms.entities.values():
            if (
                ent.entity_id.startswith("time.")
                and getattr(ent, "_key", None) == "filtration1_start"
            ):
                entity_obj = ent
                break
        if entity_obj is not None:
            break
    assert entity_obj is not None

    mock_neopool_client.write_timer.reset_mock()
    await entity_obj.async_set_value(dt_time(6, 0))
    assert "Winter mode is active" in caplog.text
    mock_neopool_client.write_timer.assert_not_called()
