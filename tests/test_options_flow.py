"""Tests for the NeoPool options flow."""

from datetime import datetime

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.neopool.const import (
    CONF_DEV_OVERRIDES,
    CONF_DEV_OVERRIDES_ENABLED,
    CONF_ENABLE_BACKWASH_OPTION,
    CONF_MEASURE_WHEN_FILTRATION_OFF,
    CONF_MODBUS_FRAMER,
    CONF_UNIT_ID,
    CONF_USE_AUX1,
    CONF_USE_AUX2,
    CONF_USE_AUX3,
    CONF_USE_AUX4,
    CONF_USE_COVER_SENSOR,
    CONF_USE_FILTRATION1,
    CONF_USE_FILTRATION2,
    CONF_USE_FILTRATION3,
    CONF_USE_LIGHT,
    CURRENT_VERSION,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import slugify

from . import setup_integration


@pytest.mark.usefixtures("mock_neopool_client")
async def test_options_flow_show_form(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Opening the options flow shows the init form."""
    await setup_integration(hass, mock_config_entry)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"


@pytest.mark.usefixtures("mock_neopool_client")
async def test_options_flow_save_changes(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Submitting the form persists the new options on the config entry."""
    await setup_integration(hass, mock_config_entry)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_USE_FILTRATION1: False,
            CONF_USE_FILTRATION2: False,
            CONF_USE_FILTRATION3: False,
            CONF_USE_LIGHT: True,
            CONF_USE_COVER_SENSOR: False,
            CONF_USE_AUX1: False,
            CONF_USE_AUX2: False,
            CONF_USE_AUX3: False,
            CONF_USE_AUX4: False,
            "filtration_pump_power": 0,
            CONF_MEASURE_WHEN_FILTRATION_OFF: False,
            # CUSTOM-ONLY START
            "unlock_advanced": "",
            # CUSTOM-ONLY END
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options[CONF_USE_LIGHT] is True
    assert mock_config_entry.options[CONF_USE_FILTRATION1] is False

    # CREATE_ENTRY triggers a background reload of the config entry. Wait for
    # it to finish before the test exits so the pytest-hass fixture can unload
    # cleanly and no coordinator refresh timer lingers.
    await hass.async_block_till_done()


# CUSTOM-ONLY START, unlock_advanced / dev_overrides / enable_backwash_option
# are HACS-only knobs gated by a password-locked "advanced" step.
@pytest.mark.usefixtures("mock_neopool_client")
async def test_options_flow_unlock_advanced_with_correct_password(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
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
            CONF_USE_FILTRATION1: False,
            CONF_USE_FILTRATION2: False,
            CONF_USE_FILTRATION3: False,
            CONF_USE_LIGHT: False,
            CONF_USE_COVER_SENSOR: False,
            CONF_USE_AUX1: False,
            CONF_USE_AUX2: False,
            CONF_USE_AUX3: False,
            CONF_USE_AUX4: False,
            "filtration_pump_power": 0,
            CONF_MEASURE_WHEN_FILTRATION_OFF: False,
            "unlock_advanced": expected,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "advanced"


@pytest.mark.usefixtures("mock_neopool_client")
async def test_options_flow_unlock_advanced_wrong_password_shows_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A wrong unlock_advanced password keeps the user on the init step."""
    await setup_integration(hass, mock_config_entry)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_USE_FILTRATION1: False,
            CONF_USE_FILTRATION2: False,
            CONF_USE_FILTRATION3: False,
            CONF_USE_LIGHT: False,
            CONF_USE_COVER_SENSOR: False,
            CONF_USE_AUX1: False,
            CONF_USE_AUX2: False,
            CONF_USE_AUX3: False,
            CONF_USE_AUX4: False,
            "filtration_pump_power": 0,
            CONF_MEASURE_WHEN_FILTRATION_OFF: False,
            "unlock_advanced": "wrong-password",
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    assert result["errors"] == {"unlock_advanced": "unlock_advanced_error"}


@pytest.mark.usefixtures("mock_neopool_client")
async def test_options_flow_advanced_step_save(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
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
            CONF_USE_FILTRATION1: False,
            CONF_USE_FILTRATION2: False,
            CONF_USE_FILTRATION3: False,
            CONF_USE_LIGHT: False,
            CONF_USE_COVER_SENSOR: False,
            CONF_USE_AUX1: False,
            CONF_USE_AUX2: False,
            CONF_USE_AUX3: False,
            CONF_USE_AUX4: False,
            "filtration_pump_power": 0,
            CONF_MEASURE_WHEN_FILTRATION_OFF: False,
            "unlock_advanced": expected,
        },
    )
    assert result["step_id"] == "advanced"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_ENABLE_BACKWASH_OPTION: True,
            CONF_DEV_OVERRIDES_ENABLED: False,
            CONF_DEV_OVERRIDES: "{}",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options[CONF_ENABLE_BACKWASH_OPTION] is True

    # CREATE_ENTRY triggers a background reload of the config entry. Wait for
    # it to finish before the test exits so the pytest-hass fixture can unload
    # cleanly and no coordinator refresh timer lingers.
    await hass.async_block_till_done()


@pytest.mark.usefixtures("mock_neopool_client")
async def test_options_flow_init_form_when_backwash_already_enabled(
    hass: HomeAssistant,
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
            CONF_UNIT_ID: 1,
            CONF_MODBUS_FRAMER: "tcp",
        },
        options={
            CONF_MODBUS_FRAMER: "tcp",
            CONF_ENABLE_BACKWASH_OPTION: True,
        },
    )
    await setup_integration(hass, entry)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    # The init step renders without erroring; the backwash toggle is now part
    # of the schema directly (no need to unlock_advanced first).
    assert result["step_id"] == "init"


# CUSTOM-ONLY END
