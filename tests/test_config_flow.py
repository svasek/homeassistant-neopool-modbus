"""Test the NeoPool config flow."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

from neopool_modbus.exceptions import NeoPoolModbusError, NeoPoolTimeoutError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.neopool import config_flow
from custom_components.neopool.config_flow import (
    SECTION_MORE_OPTIONS,
    NeoPoolConfigFlow,
    NeoPoolOptionsFlowHandler,
)
from custom_components.neopool.const import (
    CONF_ADVANCED,
    CONF_AUTO_TIME_SYNC,
    CONF_BAUDRATE,
    CONF_CAPABILITIES,
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
    CONF_USE_LIGHT,
    CURRENT_VERSION,
    DEFAULT_UNIT_ID,
    DOMAIN,
    TYPE_SERIAL,
    TYPE_TCP,
)
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.const import CONF_DEVICE, CONF_HOST, CONF_PORT, CONF_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError

from . import setup_integration
from .conftest import MOCK_HOST, MOCK_PORT, MOCK_SERIAL

# Every config-flow test in this module patches the probe so we don't hit the
# network. Tests that need a failing probe override the patch locally.
pytestmark = pytest.mark.usefixtures("mock_socket_connection")

# Sectioned step input: the device ID lives in a collapsed section.
TCP_INPUT = {
    CONF_HOST: MOCK_HOST,
    CONF_PORT: MOCK_PORT,
    CONF_MODBUS_FRAMER: "tcp",
    SECTION_MORE_OPTIONS: {CONF_UNIT_ID: DEFAULT_UNIT_ID},
}
SERIAL_INPUT = {
    CONF_DEVICE: "/dev/ttyUSB0",
    CONF_BAUDRATE: 19200,
    SECTION_MORE_OPTIONS: {CONF_UNIT_ID: DEFAULT_UNIT_ID},
}


async def _advance_to_step(hass: HomeAssistant, step: str) -> dict:
    """Start a user flow and pick a connection type from the menu."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "user"
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": step}
    )


# ---------------------------------------------------------------------------
# User flow, happy path + recoverable errors
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("mock_neopool_client")
async def test_user_flow_tcp(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """A happy-path TCP flow creates the entry."""
    result = await _advance_to_step(hass, TYPE_TCP)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == TYPE_TCP

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], TCP_INPUT
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == MOCK_HOST
    assert result["data"][CONF_TYPE] == TYPE_TCP
    assert result["data"][CONF_HOST] == MOCK_HOST
    assert result["data"][CONF_PORT] == MOCK_PORT
    assert result["data"][CONF_UNIT_ID] == DEFAULT_UNIT_ID
    assert result["result"].unique_id == MOCK_SERIAL
    assert mock_setup_entry.call_count == 1


@pytest.mark.usefixtures("mock_neopool_client")
async def test_user_flow_serial(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """A happy-path serial flow creates an entry with no host."""
    result = await _advance_to_step(hass, TYPE_SERIAL)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == TYPE_SERIAL

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], SERIAL_INPUT
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "/dev/ttyUSB0"
    assert result["data"][CONF_TYPE] == TYPE_SERIAL
    assert result["data"][CONF_DEVICE] == "/dev/ttyUSB0"
    assert result["data"][CONF_BAUDRATE] == 19200
    assert result["data"][CONF_UNIT_ID] == DEFAULT_UNIT_ID
    assert CONF_HOST not in result["data"]
    assert result["result"].unique_id == MOCK_SERIAL
    assert mock_setup_entry.call_count == 1


@pytest.mark.parametrize(
    ("exc", "expected_error"),
    [
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
    """Probe-side exceptions map to a form error and the flow recovers."""
    result = await _advance_to_step(hass, TYPE_TCP)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            config_flow,
            "async_probe_serial_unit",
            AsyncMock(side_effect=exc),
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], TCP_INPUT
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected_error}

    # Recover: probe now succeeds.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], TCP_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.usefixtures("mock_neopool_client")
async def test_user_flow_device_in_use(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """A device held on different link settings surfaces as cannot_connect."""
    result = await _advance_to_step(hass, TYPE_TCP)

    @asynccontextmanager
    async def _in_use(*_args: object, **_kwargs: object) -> AsyncIterator[None]:
        # Core raises when acquiring the temporary unit, i.e. at __aenter__.
        raise HomeAssistantError("in use")
        yield  # pragma: no cover

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config_flow, "async_get_temporary_unit", _in_use)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], TCP_INPUT
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    # Recover: the conflict clears and the flow finishes.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], TCP_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.usefixtures("mock_neopool_client")
async def test_user_flow_already_configured(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The flow aborts when the same device is already configured."""
    mock_config_entry.add_to_hass(hass)

    result = await _advance_to_step(hass, TYPE_TCP)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], TCP_INPUT
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
            CONF_MODBUS_FRAMER: "tcp",
            SECTION_MORE_OPTIONS: {CONF_UNIT_ID: 2},
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_HOST] == "192.0.2.50"
    assert mock_config_entry.data[CONF_PORT] == 1502
    assert mock_config_entry.data[CONF_UNIT_ID] == 2

    # Reconfigure triggers an entry reload which schedules the coordinator's
    # update_interval timer; wait for the reload to finish, then unload to
    # cancel the timer (otherwise phacc's verify_cleanup fixture flags it
    # as a lingering timer when this test runs alongside others).
    while mock_config_entry.state is not ConfigEntryState.LOADED:
        await hass.async_block_till_done()
    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.usefixtures("mock_neopool_client")
async def test_reconfigure_flow_serial(
    hass: HomeAssistant,
    mock_config_entry_serial: MockConfigEntry,
) -> None:
    """A serial entry reconfigures through the serial step."""
    mock_config_entry_serial.add_to_hass(hass)

    result = await mock_config_entry_serial.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_DEVICE: "/dev/ttyUSB1",
            CONF_BAUDRATE: 19200,
            SECTION_MORE_OPTIONS: {CONF_UNIT_ID: DEFAULT_UNIT_ID},
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry_serial.data[CONF_DEVICE] == "/dev/ttyUSB1"
    assert CONF_HOST not in mock_config_entry_serial.data

    while mock_config_entry_serial.state is not ConfigEntryState.LOADED:
        await hass.async_block_till_done()
    await hass.config_entries.async_unload(mock_config_entry_serial.entry_id)
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    ("exc", "expected_error"),
    [
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
            "async_probe_serial_unit",
            AsyncMock(side_effect=exc),
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.0.2.99",
                CONF_PORT: 502,
                CONF_MODBUS_FRAMER: "tcp",
                SECTION_MORE_OPTIONS: {CONF_UNIT_ID: 1},
            },
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected_error}


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
            "async_probe_serial_unit",
            AsyncMock(return_value="9999999999"),
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.0.2.50",
                CONF_PORT: 502,
                CONF_MODBUS_FRAMER: "tcp",
                SECTION_MORE_OPTIONS: {CONF_UNIT_ID: 1},
            },
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "serial_mismatch"


async def test_async_get_options_flow_returns_handler() -> None:
    """async_get_options_flow returns a NeoPoolOptionsFlowHandler instance."""

    handler = NeoPoolConfigFlow.async_get_options_flow(MagicMock())
    assert isinstance(handler, NeoPoolOptionsFlowHandler)


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
            CONF_USE_LIGHT: True,
            CONF_USE_COVER_SENSOR: False,
            CONF_USE_AUX1: False,
            CONF_USE_AUX2: False,
            CONF_USE_AUX3: False,
            CONF_USE_AUX4: False,
            # CUSTOM-ONLY START, filtration pump-power is HACS-only.
            "filtration_pump_power": 0,
            # CUSTOM-ONLY END
            CONF_MEASURE_WHEN_FILTRATION_OFF: False,
            # CUSTOM-ONLY START, automatic device-time sync is HACS-only.
            CONF_AUTO_TIME_SYNC: True,
            # CUSTOM-ONLY END
            # CUSTOM-ONLY START
            CONF_ADVANCED: {},
            # CUSTOM-ONLY END
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options[CONF_USE_LIGHT] is True
    # CUSTOM-ONLY START, automatic device-time sync is HACS-only.
    assert mock_config_entry.options[CONF_AUTO_TIME_SYNC] is True
    # CUSTOM-ONLY END

    # CREATE_ENTRY triggers a background reload of the config entry. Wait for
    # it to finish before the test exits so the pytest-hass fixture can unload
    # cleanly and no coordinator refresh timer lingers.
    await hass.async_block_till_done()


@pytest.mark.usefixtures("mock_neopool_client")
async def test_options_flow_preserves_capability_snapshot(
    hass: HomeAssistant,
) -> None:
    """The options flow keeps the capability snapshot while winter mode is on.

    In winter mode the coordinator skips the poll, so the snapshot persisted in
    options is the only source for offline setup; the flow must not drop it.
    """
    snapshot = {"MBF_PAR_FILT_GPIO": 1, "MBF_PAR_LIGHTING_GPIO": 2}
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MOCK_SERIAL,
        version=CURRENT_VERSION,
        pref_disable_polling=True,
        data={
            CONF_HOST: MOCK_HOST,
            CONF_PORT: MOCK_PORT,
            CONF_UNIT_ID: DEFAULT_UNIT_ID,
            CONF_MODBUS_FRAMER: "tcp",
        },
        options={CONF_CAPABILITIES: snapshot},
    )
    await setup_integration(hass, entry)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_USE_LIGHT: True,
            CONF_USE_COVER_SENSOR: False,
            CONF_USE_AUX1: False,
            CONF_USE_AUX2: False,
            CONF_USE_AUX3: False,
            CONF_USE_AUX4: False,
            # CUSTOM-ONLY START, filtration pump-power is HACS-only.
            "filtration_pump_power": 0,
            # CUSTOM-ONLY END
            CONF_MEASURE_WHEN_FILTRATION_OFF: False,
            # CUSTOM-ONLY START, automatic device-time sync is HACS-only.
            CONF_AUTO_TIME_SYNC: False,
            # CUSTOM-ONLY END
            CONF_ADVANCED: {},
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_USE_LIGHT] is True
    assert entry.options[CONF_CAPABILITIES] == snapshot

    await hass.async_block_till_done()


# CUSTOM-ONLY START, dev_overrides live in a collapsed "advanced" section
# of the init step; these are HACS-only knobs.
@pytest.mark.usefixtures("mock_neopool_client")
async def test_options_flow_advanced_section_save(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The collapsed advanced section persists dev_overrides into flat options."""
    await setup_integration(hass, mock_config_entry)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_USE_LIGHT: False,
            CONF_USE_COVER_SENSOR: False,
            CONF_USE_AUX1: False,
            CONF_USE_AUX2: False,
            CONF_USE_AUX3: False,
            CONF_USE_AUX4: False,
            "filtration_pump_power": 0,
            CONF_MEASURE_WHEN_FILTRATION_OFF: False,
            CONF_ADVANCED: {
                CONF_DEV_OVERRIDES_ENABLED: True,
                CONF_DEV_OVERRIDES: '{"MBF_PAR_TEMPERATURE": 250}',
            },
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    # Section values are flattened into the top-level options dict.
    assert mock_config_entry.options[CONF_DEV_OVERRIDES_ENABLED] is True
    assert (
        mock_config_entry.options[CONF_DEV_OVERRIDES] == '{"MBF_PAR_TEMPERATURE": 250}'
    )

    # CREATE_ENTRY triggers a background reload of the config entry. Wait for
    # it to finish before the test exits so the pytest-hass fixture can unload
    # cleanly and no coordinator refresh timer lingers.
    await hass.async_block_till_done()


# CUSTOM-ONLY END
