"""Tests for the NeoPool services."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.neopool.const import DOMAIN
from custom_components.neopool.services import (
    SERVICE_SET_TIMER,
    SERVICE_WRITE_REGISTER,
    _get_coordinator,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.setup import async_setup_component

from . import setup_integration

# ---------------------------------------------------------------------------
# set_timer
# ---------------------------------------------------------------------------


async def test_set_timer_writes_to_client(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """A happy-path set_timer call forwards on/interval/period to the client."""
    await setup_integration(hass, mock_config_entry)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_TIMER,
        {
            "entry_id": mock_config_entry.entry_id,
            "timer": "filtration1",
            "start": "08:30",
            "stop": "10:15",
            "period": 1234,
        },
        blocking=True,
    )

    mock_neopool_client.write_timer.assert_awaited_once_with(
        "filtration1",
        {"on": 30600, "interval": 6300, "period": 1234},
    )


async def test_set_timer_falls_back_to_first_loaded_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Omitting entry_id picks the only loaded entry."""
    await setup_integration(hass, mock_config_entry)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_TIMER,
        {
            "timer": "filtration1",
            "start": "08:30",
            "stop": "10:15",
        },
        blocking=True,
    )
    assert mock_neopool_client.write_timer.await_count == 1


async def test_set_timer_unknown_entry_id_raises(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """An entry_id that does not exist raises with translation key."""
    await setup_integration(hass, mock_config_entry)

    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_TIMER,
            {
                "entry_id": "nonexistent",
                "timer": "filtration1",
                "start": "08:30",
                "stop": "10:15",
            },
            blocking=True,
        )
    assert exc_info.value.translation_key == "entry_not_found"


async def test_set_timer_explicit_entry_id_must_be_loaded(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Explicit entry_id pointing at a NOT_LOADED entry is rejected.

    Routing a service call to a stale or unloaded entry would surface
    confusing AttributeError downstream — the resolver requires the
    matching entry to be LOADED.
    """
    await setup_integration(hass, mock_config_entry)
    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_TIMER,
            {
                "entry_id": mock_config_entry.entry_id,
                "timer": "filtration1",
                "start": "08:30",
                "stop": "10:15",
            },
            blocking=True,
        )
    assert exc_info.value.translation_key == "entry_not_found"


async def test_set_timer_no_loaded_entry_raises(
    hass: HomeAssistant,
) -> None:
    """Calling the service before any entry is loaded raises."""
    # async_setup is invoked by HA before any entry, so the service is
    # registered globally — but no LOADED entry exists yet.

    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_TIMER,
            {"timer": "filtration1", "start": "08:30", "stop": "10:15"},
            blocking=True,
        )
    assert exc_info.value.translation_key == "no_loaded_entry"


async def test_get_coordinator_raises_when_runtime_data_missing(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """If a LOADED entry has no runtime_data, _get_coordinator raises.

    Direct unit test on the helper — drives the defensive 'coordinator is None'
    branch without relying on the entry-state ordering inside HA's
    config_entries machinery.
    """

    mock_config_entry.add_to_hass(hass)
    mock_config_entry.mock_state(hass, ConfigEntryState.LOADED)
    object.__setattr__(mock_config_entry, "runtime_data", None)

    fake_call = MagicMock()
    fake_call.data = {}

    with pytest.raises(ServiceValidationError) as exc_info:
        _get_coordinator(hass, fake_call)
    assert exc_info.value.translation_key == "no_coordinator"


async def test_set_timer_invalid_timer_name_raises(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """An unknown timer name raises before reaching the Modbus client."""
    await setup_integration(hass, mock_config_entry)

    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_TIMER,
            {"timer": "not_a_real_timer"},
            blocking=True,
        )
    assert exc_info.value.translation_key == "invalid_timer"
    mock_neopool_client.write_timer.assert_not_awaited()


async def test_set_timer_invalid_time_format_raises(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Malformed start/stop strings surface a translatable invalid_timer_time error.

    `hhmm_to_seconds()` raises ValueError on garbage input; without an
    explicit catch the user would see a raw traceback instead of the
    translated UI-friendly error.
    """
    await setup_integration(hass, mock_config_entry)

    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_TIMER,
            {"timer": "filtration1", "start": "not-a-time", "stop": "10:00"},
            blocking=True,
        )
    assert exc_info.value.translation_key == "invalid_timer_time"
    mock_neopool_client.write_timer.assert_not_awaited()


async def test_set_timer_client_failure_translates_to_validation_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """A Modbus write failure surfaces as a translated ServiceValidationError."""
    await setup_integration(hass, mock_config_entry)
    mock_neopool_client.write_timer = AsyncMock(side_effect=ConnectionError("nope"))

    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_TIMER,
            {
                "timer": "filtration1",
                "start": "08:30",
                "stop": "10:15",
            },
            blocking=True,
        )
    assert exc_info.value.translation_key == "timer_failed"


# ---------------------------------------------------------------------------
# write_register
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("address", "value", "expected_addr", "expected_value"),
    [
        ("1539", "5", 1539, 5),
        ("0x0604", "0x0000", 0x0604, 0),
    ],
)
async def test_write_register_decimal_and_hex(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    address: str,
    value: str,
    expected_addr: int,
    expected_value: int,
) -> None:
    """Decimal and 0x-prefixed strings are both accepted."""
    await setup_integration(hass, mock_config_entry)
    mock_neopool_client.async_write_register = AsyncMock(
        return_value={"value": expected_value, "confirmed": expected_value}
    )

    await hass.services.async_call(
        DOMAIN,
        SERVICE_WRITE_REGISTER,
        {
            "entry_id": mock_config_entry.entry_id,
            "address": address,
            "value": value,
        },
        blocking=True,
    )
    mock_neopool_client.async_write_register.assert_awaited_once_with(
        expected_addr, expected_value, apply=True
    )


async def test_write_register_apply_false(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Setting apply=false skips the EEPROM commit on the client side."""
    await setup_integration(hass, mock_config_entry)
    mock_neopool_client.async_write_register = AsyncMock(
        return_value={"value": 7, "confirmed": 7}
    )

    await hass.services.async_call(
        DOMAIN,
        SERVICE_WRITE_REGISTER,
        {
            "entry_id": mock_config_entry.entry_id,
            "address": "1539",
            "value": "7",
            "apply": False,
        },
        blocking=True,
    )
    mock_neopool_client.async_write_register.assert_awaited_once_with(
        1539, 7, apply=False
    )


async def test_write_register_invalid_hex_raises(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """An unparseable hex address raises before any write."""
    await setup_integration(hass, mock_config_entry)

    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_WRITE_REGISTER,
            {
                "entry_id": mock_config_entry.entry_id,
                "address": "0xZZZZ",
                "value": "5",
            },
            blocking=True,
        )
    assert exc_info.value.translation_key == "invalid_register_type"
    mock_neopool_client.async_write_register.assert_not_awaited()


async def test_write_register_out_of_range_raises(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Values above 65535 are rejected by parse_register_int."""
    await setup_integration(hass, mock_config_entry)

    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_WRITE_REGISTER,
            {
                "entry_id": mock_config_entry.entry_id,
                "address": "1539",
                "value": "70000",
            },
            blocking=True,
        )
    assert exc_info.value.translation_key == "register_out_of_range"


async def test_write_register_verification_mismatch_raises(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """A read-back that disagrees with the write surfaces a clear error."""
    await setup_integration(hass, mock_config_entry)
    mock_neopool_client.async_write_register = AsyncMock(
        return_value={"value": 5, "confirmed": 99}
    )

    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_WRITE_REGISTER,
            {
                "entry_id": mock_config_entry.entry_id,
                "address": "1539",
                "value": "5",
            },
            blocking=True,
        )
    assert exc_info.value.translation_key == "write_verification_failed"


async def test_write_register_returns_none_raises(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """When the client returns None we surface 'write_failed'."""
    await setup_integration(hass, mock_config_entry)
    mock_neopool_client.async_write_register = AsyncMock(return_value=None)

    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_WRITE_REGISTER,
            {
                "entry_id": mock_config_entry.entry_id,
                "address": "1539",
                "value": "5",
            },
            blocking=True,
        )
    assert exc_info.value.translation_key == "write_failed"


async def test_write_register_client_failure_raises(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Modbus exceptions are wrapped in a translated ServiceValidationError."""
    await setup_integration(hass, mock_config_entry)
    mock_neopool_client.async_write_register = AsyncMock(
        side_effect=ConnectionError("Modbus down")
    )

    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_WRITE_REGISTER,
            {
                "entry_id": mock_config_entry.entry_id,
                "address": "1539",
                "value": "5",
            },
            blocking=True,
        )
    assert exc_info.value.translation_key == "register_write_failed"
