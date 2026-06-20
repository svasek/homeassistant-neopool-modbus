"""Tests for the NeoPool options flow."""

from datetime import datetime
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.neopool.const import CURRENT_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import slugify

from . import setup_integration


async def test_options_flow_show_form(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Opening the options flow shows the init form."""
    await setup_integration(hass, mock_config_entry)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"


async def test_options_flow_save_changes(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Submitting the form persists the new options on the config entry."""
    await setup_integration(hass, mock_config_entry)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "use_filtration1": False,
            "use_filtration2": False,
            "use_filtration3": False,
            "use_light": True,
            "use_cover_sensor": False,
            "use_aux1": False,
            "use_aux2": False,
            "use_aux3": False,
            "use_aux4": False,
            "filtration_pump_power": 0,
            "measure_when_filtration_off": False,
            "unlock_advanced": "",
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options["use_light"] is True
    assert mock_config_entry.options["use_filtration1"] is False


async def test_options_flow_unlock_advanced_with_correct_password(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Entering the right unlock_advanced password reveals the advanced step."""

    # Pin the clock to a known year so the password derived inside the
    # options flow matches our `expected` value even across a New-Year roll.
    freezer.move_to(datetime(2026, 6, 1, 12, 0, 0))
    await setup_integration(hass, mock_config_entry)
    expected = f"{slugify(mock_config_entry.title)}2026"

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "use_filtration1": False,
            "use_filtration2": False,
            "use_filtration3": False,
            "use_light": False,
            "use_cover_sensor": False,
            "use_aux1": False,
            "use_aux2": False,
            "use_aux3": False,
            "use_aux4": False,
            "filtration_pump_power": 0,
            "measure_when_filtration_off": False,
            "unlock_advanced": expected,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "advanced"


async def test_options_flow_unlock_advanced_wrong_password_shows_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """A wrong unlock_advanced password keeps the user on the init step."""
    await setup_integration(hass, mock_config_entry)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "use_filtration1": False,
            "use_filtration2": False,
            "use_filtration3": False,
            "use_light": False,
            "use_cover_sensor": False,
            "use_aux1": False,
            "use_aux2": False,
            "use_aux3": False,
            "use_aux4": False,
            "filtration_pump_power": 0,
            "measure_when_filtration_off": False,
            "unlock_advanced": "wrong-password",
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    assert result["errors"] == {"unlock_advanced": "unlock_advanced_error"}


async def test_options_flow_advanced_step_save(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The advanced step accepts dev_overrides and writes them to options."""

    # Same year-pin as in test_options_flow_unlock_advanced_with_correct_password.
    freezer.move_to(datetime(2026, 6, 1, 12, 0, 0))
    await setup_integration(hass, mock_config_entry)
    expected = f"{slugify(mock_config_entry.title)}2026"

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "use_filtration1": False,
            "use_filtration2": False,
            "use_filtration3": False,
            "use_light": False,
            "use_cover_sensor": False,
            "use_aux1": False,
            "use_aux2": False,
            "use_aux3": False,
            "use_aux4": False,
            "filtration_pump_power": 0,
            "measure_when_filtration_off": False,
            "unlock_advanced": expected,
        },
    )
    assert result["step_id"] == "advanced"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "enable_backwash_option": True,
            "dev_overrides_enabled": False,
            "dev_overrides": "{}",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options["enable_backwash_option"] is True


async def test_options_flow_init_form_when_backwash_already_enabled(
    hass: HomeAssistant,
    mock_neopool_client: MagicMock,
) -> None:
    """When enable_backwash_option is already on, the init form exposes it inline."""
    entry = MockConfigEntry(
        domain="neopool",
        title="Pool",
        unique_id="neopool_backwash_enabled",
        version=CURRENT_VERSION,
        data={
            "host": "192.0.2.20",
            "port": 502,
            "name": "Pool",
            "unit_id": 1,
            "modbus_framer": "tcp",
        },
        options={
            "modbus_framer": "tcp",
            "enable_backwash_option": True,
        },
    )
    await setup_integration(hass, entry)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    # The init step renders without erroring; the backwash toggle is now part
    # of the schema directly (no need to unlock_advanced first).
    assert result["step_id"] == "init"
