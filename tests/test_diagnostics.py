"""Test the NeoPool diagnostics."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator
from syrupy.assertion import SnapshotAssertion
from syrupy.filters import props

from custom_components.neopool.diagnostics import async_get_config_entry_diagnostics
from homeassistant.core import HomeAssistant

from . import setup_integration


@pytest.mark.usefixtures("mock_neopool_client")
async def test_entry_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    snapshot: SnapshotAssertion,
    mock_config_entry_timers: MockConfigEntry,
) -> None:
    """Test config entry diagnostics output is stable and redacts host/port."""
    await setup_integration(hass, mock_config_entry_timers)

    result = await get_diagnostics_for_config_entry(
        hass, hass_client, mock_config_entry_timers
    )

    # Properties that legitimately vary between test runs (generated
    # entry IDs, mock object identity) are excluded from the snapshot,
    # what we care about is the stable shape of the payload plus the
    # host/port/serial redaction.
    assert result == snapshot(
        exclude=props(
            "created_at",
            "modified_at",
            "entry_id",
        )
    )


@pytest.mark.usefixtures("mock_neopool_client")
async def test_entry_diagnostics_exposes_only_exception_type(
    hass: HomeAssistant,
    mock_config_entry_timers: MockConfigEntry,
) -> None:
    """last_exception exposes the type only, never the raw message.

    The client embeds host:port in connection error messages, so the raw
    text must never be serialized into diagnostics.
    """
    await setup_integration(hass, mock_config_entry_timers)
    coordinator = mock_config_entry_timers.runtime_data
    coordinator.last_exception = ConnectionError(
        "Modbus client connection failed to 192.0.2.15:502"
    )
    result = await async_get_config_entry_diagnostics(hass, mock_config_entry_timers)
    assert result["coordinator"]["last_exception"] == "ConnectionError"
    assert "192.0.2.15" not in str(result)
