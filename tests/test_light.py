"""Tests for the NeoPool light platform."""

from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.neopool.const import LIGHT_DEFINITIONS
from homeassistant.const import (
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform as ep, entity_registry as er

from . import setup_integration


def _light_entity_id(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    registry = er.async_get(hass)
    entries = [
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "light"
    ]
    assert entries, "expected exactly one neopool light entity"
    return entries[0].entity_id


async def _turn_on(hass: HomeAssistant, entity_id: str) -> None:
    await hass.services.async_call(
        Platform.LIGHT,
        SERVICE_TURN_ON,
        {"entity_id": entity_id},
        blocking=True,
    )


async def _turn_off(hass: HomeAssistant, entity_id: str) -> None:
    await hass.services.async_call(
        Platform.LIGHT,
        SERVICE_TURN_OFF,
        {"entity_id": entity_id},
        blocking=True,
    )


async def test_light_turn_on_off_writes_to_relay_timer(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Light on/off writes to the configured timer block plus the EXEC commit."""

    await setup_integration(hass, mock_config_entry)
    entity_id = _light_entity_id(hass, mock_config_entry)

    light_props = LIGHT_DEFINITIONS["light"]
    timer_block = light_props["timer_block_addr"]
    function_addr = light_props["function_addr"]

    mock_neopool_client.async_write_register.reset_mock()
    await _turn_on(hass, entity_id)

    # Three writes for ON: function_addr, timer_block (3 = always ON), EXEC
    addresses_on = [
        c.args[0] for c in mock_neopool_client.async_write_register.await_args_list
    ]
    assert function_addr in addresses_on
    assert timer_block in addresses_on
    # EXEC_REGISTER write at the end
    write_calls = mock_neopool_client.async_write_register.await_args_list
    assert any(c.args[0] == timer_block and c.args[1] == 3 for c in write_calls), (
        f"expected timer_block write with value 3, got {write_calls}"
    )

    mock_neopool_client.async_write_register.reset_mock()
    await _turn_off(hass, entity_id)
    write_calls_off = mock_neopool_client.async_write_register.await_args_list
    assert any(c.args[0] == timer_block and c.args[1] == 4 for c in write_calls_off), (
        f"expected timer_block write with value 4, got {write_calls_off}"
    )


async def test_light_is_on_reflects_relay_enable(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """is_on tracks coordinator.data['relay_light_enable']."""
    await setup_integration(hass, mock_config_entry)
    entity_id = _light_entity_id(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data

    coordinator.data["relay_light_enable"] = 3  # always ON
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_ON

    coordinator.data["relay_light_enable"] = 4  # always OFF
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_OFF


async def test_light_unavailable_when_relay_in_auto_mode(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """When the relay is set to auto (1), the light entity goes UNAVAILABLE."""
    await setup_integration(hass, mock_config_entry)
    entity_id = _light_entity_id(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data

    coordinator.data["relay_light_enable"] = 1  # auto
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE


async def test_light_winter_mode_guard_when_called_directly(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """async_turn_on/off short-circuits when winter_mode is on.

    Service-call layer would normally refuse to dispatch to an unavailable
    entity; we drive the entity method directly to cover the early-exit
    branch in the platform code.
    """
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    coordinator.winter_mode = True

    entity_id = _light_entity_id(hass, mock_config_entry)
    # Reach the entity object via hass.data
    entity_obj = None
    for platform in hass.data.get("entity_components", {}).values():
        if hasattr(platform, "get_entity"):
            entity_obj = platform.get_entity(entity_id)
            if entity_obj is not None:
                break
    if entity_obj is None:
        # Fallback via entity_platform's domain-keyed registry

        for platforms in ep.async_get_platforms(hass, "neopool"):
            for ent in platforms.entities.values():
                if ent.entity_id == entity_id:
                    entity_obj = ent
                    break
            if entity_obj is not None:
                break

    assert entity_obj is not None
    mock_neopool_client.async_write_register.reset_mock()
    await entity_obj.async_turn_on()
    await entity_obj.async_turn_off()
    assert "Winter mode is active" in caplog.text
    mock_neopool_client.async_write_register.assert_not_called()
