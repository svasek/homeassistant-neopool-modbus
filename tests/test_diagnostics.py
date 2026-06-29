"""Test the NeoPool diagnostics."""

from unittest.mock import MagicMock

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


async def test_entry_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    snapshot: SnapshotAssertion,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Test config entry diagnostics output is stable and redacts host/port."""
    await setup_integration(hass, mock_config_entry)

    result = await get_diagnostics_for_config_entry(
        hass, hass_client, mock_config_entry
    )

    # Properties that legitimately vary between test runs (timestamps,
    # generated entry IDs, mock object identity) are excluded from the
    # snapshot, what we care about is the stable shape of the payload
    # plus the host/port redaction.
    assert result == snapshot(
        exclude=props(
            "created_at",
            "modified_at",
            "entry_id",
            "last_update_time",
            "update_interval",
        )
    )


async def test_entry_diagnostics_without_runtime_data(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Diagnostics returns 'not loaded' when the entry has no coordinator yet.

    This branch is reached if diagnostics is queried for an entry that has
    been added but never loaded (e.g. it failed setup and was retried).
    """
    mock_config_entry.add_to_hass(hass)
    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    assert result["coordinator"] == {"status": "not loaded"}
    # Host is still redacted on the data block.
    assert result["config_entry"]["data"]["host"] == "**REDACTED**"
