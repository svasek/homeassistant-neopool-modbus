"""Test the NeoPool config flow."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from freezegun.api import FrozenDateTimeFactory
from neopool_modbus.exceptions import (
    NeoPoolConnectionError,
    NeoPoolModbusError,
    NeoPoolTimeoutError,
)
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.neopool import config_flow
from custom_components.neopool.config_flow import (
    NeoPoolConfigFlow,
    NeoPoolOptionsFlowHandler,
)
from custom_components.neopool.const import (
    CONF_DEV_OVERRIDES,
    CONF_DEV_OVERRIDES_ENABLED,
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
    DOMAIN,
)
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import slugify

from . import setup_integration
from .conftest import MOCK_HOST, MOCK_PORT, MOCK_SERIAL

# Every config-flow test in this module patches the lib probe so we don't
# hit the network. Tests that need a failing probe override the patch
# locally via monkeypatch.
pytestmark = pytest.mark.usefixtures("mock_socket_connection")

USER_INPUT = {
    CONF_HOST: MOCK_HOST,
    CONF_PORT: MOCK_PORT,
}


# ---------------------------------------------------------------------------
# User flow, happy path + recoverable errors
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("mock_neopool_client")
async def test_user_flow(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test a happy-path config flow creates the entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert not result["errors"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == MOCK_HOST
    assert result["data"][CONF_HOST] == MOCK_HOST
    assert result["data"][CONF_PORT] == MOCK_PORT
    assert result["result"].unique_id == MOCK_SERIAL
    assert mock_setup_entry.call_count == 1


@pytest.mark.parametrize(
    ("exc", "expected_error"),
    [
        (NeoPoolConnectionError("refused"), "cannot_connect"),
        (NeoPoolTimeoutError("timeout"), "cannot_connect"),
        (NeoPoolModbusError("bad payload"), "cannot_read_modbus"),
    ],
)
@pytest.mark.usefixtures("mock_neopool_client")
async def test_user_flow_probe_errors(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    exc: Exception,
    expected_error: str,
) -> None:
    """Probe-side exceptions are mapped to user-facing errors and the flow recovers."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            config_flow,
            "async_probe_serial",
            AsyncMock(side_effect=exc),
        )

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_HOST: expected_error}

    # Recover: probe now succeeds.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.usefixtures("mock_neopool_client")
async def test_user_flow_already_configured(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test config flow aborts when the same device is already configured."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: MOCK_HOST,
            CONF_PORT: MOCK_PORT,
        },
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


# ---------------------------------------------------------------------------
# Reconfigure flow
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("mock_neopool_client")
async def test_reconfigure_flow_happy_path(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A reconfigure flow updates host/port and reloads the entry."""
    mock_config_entry.add_to_hass(hass)

    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "192.0.2.50",
            CONF_PORT: 1502,
            CONF_UNIT_ID: 2,
            CONF_MODBUS_FRAMER: "tcp",
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_HOST] == "192.0.2.50"
    assert mock_config_entry.data[CONF_PORT] == 1502

    # Reconfigure triggers an entry reload which schedules the coordinator's
    # update_interval timer; wait for the reload to finish, then unload to
    # cancel the timer (otherwise phacc's verify_cleanup fixture flags it
    # as a lingering timer when this test runs alongside others).
    while mock_config_entry.state is not ConfigEntryState.LOADED:
        await hass.async_block_till_done()
    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    ("exc", "expected_error"),
    [
        (NeoPoolConnectionError("refused"), "cannot_connect"),
        (NeoPoolTimeoutError("timeout"), "cannot_connect"),
        (NeoPoolModbusError("bad payload"), "cannot_read_modbus"),
    ],
)
@pytest.mark.usefixtures("mock_neopool_client")
async def test_reconfigure_flow_probe_errors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    exc: Exception,
    expected_error: str,
) -> None:
    """A reconfigure flow surfaces probe-side errors."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reconfigure_flow(hass)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            config_flow,
            "async_probe_serial",
            AsyncMock(side_effect=exc),
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.0.2.99",
                CONF_PORT: 502,
                CONF_UNIT_ID: 1,
                CONF_MODBUS_FRAMER: "tcp",
            },
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_HOST: expected_error}


@pytest.mark.usefixtures("mock_neopool_client")
async def test_reconfigure_flow_serial_mismatch(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A reconfigure that targets a different physical controller is rejected."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reconfigure_flow(hass)

    with pytest.MonkeyPatch.context() as mp:
        # The probe returns a *different* serial than the entry's unique_id.
        mp.setattr(
            config_flow,
            "async_probe_serial",
            AsyncMock(return_value="9999999999"),
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.0.2.50",
                CONF_PORT: 502,
                CONF_UNIT_ID: 1,
                CONF_MODBUS_FRAMER: "tcp",
            },
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_HOST: "serial_mismatch"}


# ---------------------------------------------------------------------------
# Edge cases on the reconfigure step
# ---------------------------------------------------------------------------


async def test_async_get_options_flow_returns_handler() -> None:
    """async_get_options_flow returns a NeoPoolOptionsFlowHandler instance."""

    handler = NeoPoolConfigFlow.async_get_options_flow(MagicMock())
    assert isinstance(handler, NeoPoolOptionsFlowHandler)


async def test_reconfigure_flow_aborts_when_entry_id_missing(
    hass: HomeAssistant,
) -> None:
    """async_step_reconfigure aborts when context has no entry_id."""

    flow = NeoPoolConfigFlow()
    flow.hass = hass
    flow.context = {}  # no entry_id at all
    result = await flow.async_step_reconfigure()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "entry_not_found"


async def test_reconfigure_flow_aborts_when_entry_not_found(
    hass: HomeAssistant,
) -> None:
    """async_step_reconfigure aborts when the referenced entry was deleted."""

    flow = NeoPoolConfigFlow()
    flow.hass = hass
    flow.context = {"entry_id": "nonexistent"}
    result = await flow.async_step_reconfigure()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "entry_not_found"


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
            CONF_DEV_OVERRIDES_ENABLED: False,
            CONF_DEV_OVERRIDES: "{}",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY

    # CREATE_ENTRY triggers a background reload of the config entry. Wait for
    # it to finish before the test exits so the pytest-hass fixture can unload
    # cleanly and no coordinator refresh timer lingers.
    await hass.async_block_till_done()


# CUSTOM-ONLY END
