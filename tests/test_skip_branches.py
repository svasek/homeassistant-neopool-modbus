"""Integration-level tests that cover platform 'should-skip' guards.

Drives setup with the lean `mock_neopool_client_minimal` fixture (no
modules detected, no relay GPIOs assigned) and verifies each platform's
gating branch fires by counting the resulting entities.
"""

from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.neopool.binary_sensor import async_setup_entry as bs_setup
from custom_components.neopool.button import async_setup_entry as button_setup
from custom_components.neopool.light import async_setup_entry as light_setup
from custom_components.neopool.number import async_setup_entry as number_setup
from custom_components.neopool.select import async_setup_entry as select_setup
from custom_components.neopool.sensor import async_setup_entry as sensor_setup
from custom_components.neopool.switch import async_setup_entry as switch_setup
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import setup_integration


async def test_platforms_skip_optional_entities_when_modules_absent(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client_minimal: MagicMock,
) -> None:
    """With no modules detected and no relay GPIOs, platforms register fewer entities.

    This test asserts the integration still loads cleanly (every platform
    setup runs, no exceptions), and the skip-branches we couldn't reach
    via the default 'fully-loaded' fixture get exercised here.
    """
    await setup_integration(hass, mock_config_entry)

    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, mock_config_entry.entry_id)
    by_platform: dict[str, int] = {}
    for e in entries:
        by_platform[e.domain] = by_platform.get(e.domain, 0) + 1

    # Light is always gated on use_light + valid lighting relay; with the
    # relay GPIO at zero the light entity must be absent.
    assert by_platform.get("light", 0) == 0
    # Some sensors / selects depend on the missing modules. The base set is
    # still non-empty (filtration timers etc.), so we just sanity-check
    # that setup completed.
    assert sum(by_platform.values()) >= 1


async def test_button_setup_short_circuits_without_data(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Button platform skips entity creation when coordinator.data is None."""

    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    coordinator.data = None  # Simulate the rare 'no data yet' state

    # Re-invoke the platform setup with a fresh add-entities collector.
    added: list = []

    async def collect(entities, *_args, **_kw):
        added.extend(entities)

    await button_setup(hass, mock_config_entry, collect)
    assert added == []
    assert "skipping button setup" in caplog.text


async def test_light_setup_short_circuits_without_data(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Light platform skips entity creation when coordinator.data is None."""

    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    coordinator.data = None

    added: list = []

    async def collect(entities, *_args, **_kw):
        added.extend(entities)

    await light_setup(hass, mock_config_entry, collect)
    assert added == []
    assert "skipping light setup" in caplog.text


async def test_switch_setup_short_circuits_without_data(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Switch platform skips entity creation when coordinator.data is None."""

    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    coordinator.data = None

    added: list = []

    async def collect(entities, *_args, **_kw):
        added.extend(entities)

    await switch_setup(hass, mock_config_entry, collect)
    assert added == []
    assert "skipping switch setup" in caplog.text


async def test_select_setup_short_circuits_without_data(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Select platform skips entity creation when coordinator.data is None."""

    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    coordinator.data = None

    added: list = []

    async def collect(entities, *_args, **_kw):
        added.extend(entities)

    await select_setup(hass, mock_config_entry, collect)
    assert added == []
    assert "skipping select setup" in caplog.text


async def test_number_setup_short_circuits_without_data(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Number platform skips entity creation when coordinator.data is None."""

    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    coordinator.data = None

    added: list = []

    async def collect(entities, *_args, **_kw):
        added.extend(entities)

    await number_setup(hass, mock_config_entry, collect)
    assert added == []
    assert "skipping number setup" in caplog.text


async def test_sensor_setup_short_circuits_without_data(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Sensor platform skips entity creation when coordinator.data is None."""

    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    coordinator.data = None

    added: list = []

    async def collect(entities, *_args, **_kw):
        added.extend(entities)

    await sensor_setup(hass, mock_config_entry, collect)
    assert added == []
    assert "skipping sensor setup" in caplog.text


async def test_binary_sensor_setup_short_circuits_without_data(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Binary sensor platform skips entity creation when coordinator.data is None."""

    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    coordinator.data = None

    added: list = []

    async def collect(entities, *_args, **_kw):
        added.extend(entities)

    await bs_setup(hass, mock_config_entry, collect)
    assert added == []
    assert "skipping binary_sensor setup" in caplog.text
