"""Tests for the NeoPool helper functions."""

import asyncio as _asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

from neopool_modbus.capabilities import has_filtvalve
from neopool_modbus.exceptions import NeoPoolError
import pytest

from custom_components.neopool.config_flow import is_host_port_open
from custom_components.neopool.helpers import (
    async_get_device_serial,
    calculate_next_interval_time,
    get_device_time,
    is_device_time_out_of_sync,
    parse_register_int,
    prepare_device_time,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

# ---------------------------------------------------------------------------
# get_device_time
# ---------------------------------------------------------------------------


def test_get_device_time_utc() -> None:
    """Decoded device time matches MBF_PAR_TIME interpreted as a unix timestamp."""
    ts = (0x1234 << 16) | 0x5678
    data = {"MBF_PAR_TIME": ts}
    assert get_device_time(data) == datetime.fromtimestamp(ts, tz=UTC)


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"MBF_PAR_TIME": None},
    ],
)
def test_get_device_time_missing_keys(data: dict) -> None:
    """Missing MBF_PAR_TIME yields None."""
    assert get_device_time(data) is None


def test_get_device_time_epoch_zero() -> None:
    """MBF_PAR_TIME == 0 -> 1970-01-01T00:00:00Z."""
    assert get_device_time({"MBF_PAR_TIME": 0}) == datetime(1970, 1, 1, tzinfo=UTC)


def test_get_device_time_with_hass(hass: HomeAssistant) -> None:
    """Passing hass interprets the device's epoch in HA's local timezone.

    The controller stores 'seconds since 1970-01-01 00:00:00 LOCAL TIME'
    rather than UTC epoch — see the WORKAROUND in helpers.get_device_time.
    The result is then converted back to UTC for HA's state machine.
    """
    hass.config.time_zone = "UTC"
    ts = 1_234_567_890
    data = {"MBF_PAR_TIME": ts}
    result = get_device_time(data, hass)
    assert result is not None
    assert result.tzinfo is not None
    # With HA timezone == UTC, the local-epoch interpretation matches the
    # plain UTC interpretation; both branches produce the same UTC datetime.
    assert result == datetime.fromtimestamp(ts, tz=UTC)


# ---------------------------------------------------------------------------
# prepare_device_time
# ---------------------------------------------------------------------------


def test_prepare_device_time_returns_unix_timestamp(hass: HomeAssistant) -> None:
    """prepare_device_time returns a positive 32-bit unix timestamp."""
    result = prepare_device_time(hass)
    assert isinstance(result, int)
    assert 0 < result < 0x100000000


# ---------------------------------------------------------------------------
# is_device_time_out_of_sync
# ---------------------------------------------------------------------------


def test_is_device_time_out_of_sync_within_threshold() -> None:
    """A small drift between device and HA returns False."""
    now = int(dt_util.utcnow().timestamp())
    data = {"MBF_PAR_TIME": now}
    with patch(
        "homeassistant.util.dt.utcnow",
        return_value=datetime.fromtimestamp(now, tz=UTC),
    ):
        assert is_device_time_out_of_sync(data, None, threshold_seconds=60) is False


def test_is_device_time_out_of_sync_above_threshold() -> None:
    """A drift larger than threshold returns True."""
    now = int(dt_util.utcnow().timestamp())
    device_time = now - 7200  # 2 hours ago
    data = {"MBF_PAR_TIME": device_time}
    with patch(
        "homeassistant.util.dt.utcnow",
        return_value=datetime.fromtimestamp(now, tz=UTC),
    ):
        assert is_device_time_out_of_sync(data, None, threshold_seconds=60) is True


def test_is_device_time_out_of_sync_no_data() -> None:
    """Missing time registers means we cannot detect drift, so return False."""
    assert is_device_time_out_of_sync({}, None, threshold_seconds=60) is False


# ---------------------------------------------------------------------------
# calculate_next_interval_time
# ---------------------------------------------------------------------------


def test_calculate_next_interval_time_with_hass(hass: HomeAssistant) -> None:
    """With hass, the next-interval timestamp is in HA's local timezone."""
    hass.config.time_zone = "Europe/Prague"
    result = calculate_next_interval_time(3600, hass)
    assert result is not None
    assert result.tzinfo is not None
    assert result.second == 0
    assert result.microsecond == 0
    expected = (
        dt_util.now(ZoneInfo("Europe/Prague")) + timedelta(seconds=3600)
    ).replace(second=0, microsecond=0)
    assert abs((result - expected).total_seconds()) < 60


def test_calculate_next_interval_time_without_hass() -> None:
    """Without hass, calculation falls back to UTC."""
    result = calculate_next_interval_time(7200, None)
    assert result is not None
    assert result.tzinfo == UTC
    assert result.second == 0
    expected = (dt_util.utcnow() + timedelta(seconds=7200)).replace(
        second=0, microsecond=0
    )
    assert abs((result - expected).total_seconds()) < 60


@pytest.mark.parametrize("invalid", [0, -100, None])
def test_calculate_next_interval_time_invalid_input(invalid) -> None:
    """Zero, negative or None seconds yield None."""
    assert calculate_next_interval_time(invalid, None) is None


# ---------------------------------------------------------------------------
# has_filtvalve
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"MBF_PAR_FILTVALVE_ENABLE": 1}, True),
        ({"MBF_PAR_FILTVALVE_ENABLE": 0, "MBF_PAR_FILTVALVE_GPIO": 5}, True),
        ({"MBF_PAR_FILTVALVE_ENABLE": 1, "MBF_PAR_FILTVALVE_GPIO": 5}, True),
        ({"MBF_PAR_FILTVALVE_ENABLE": 0, "MBF_PAR_FILTVALVE_GPIO": 0}, False),
        ({}, False),
        # GPIO=8 is outside the valid hardware range (1-7) and must not trigger
        # detection — corrupted register values should not auto-create entities.
        ({"MBF_PAR_FILTVALVE_ENABLE": 0, "MBF_PAR_FILTVALVE_GPIO": 8}, False),
    ],
)
def test_has_filtvalve(data: dict, expected: bool) -> None:
    """has_filtvalve treats GPIO 1..7 or ENABLE=1 as active, anything else as off."""
    assert has_filtvalve(data) is expected


# ---------------------------------------------------------------------------
# parse_register_int
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1539", 1539),
        ("0x0603", 0x0603),
        (0, 0),
        (65535, 65535),
        ("0", 0),
        ("0xFFFF", 0xFFFF),
    ],
)
def test_parse_register_int_valid(raw, expected: int) -> None:
    """parse_register_int accepts decimal and 0x-prefixed strings as well as ints."""
    assert parse_register_int(raw, "address") == expected


def test_parse_register_int_rejects_bool() -> None:
    """A bare bool must not silently coerce to 0/1."""
    with pytest.raises(ServiceValidationError):
        parse_register_int(True, "address")


def test_parse_register_int_rejects_float() -> None:
    """A float would lose precision; reject it explicitly."""
    with pytest.raises(ServiceValidationError):
        parse_register_int(1.5, "address")


@pytest.mark.parametrize("raw", ["nonsense", "", "0xZZZZ"])
def test_parse_register_int_rejects_unparsable(raw: str) -> None:
    """Unparsable strings raise ServiceValidationError."""
    with pytest.raises(ServiceValidationError):
        parse_register_int(raw, "address")


@pytest.mark.parametrize("raw", [-1, 65536, "0x10000"])
def test_parse_register_int_rejects_out_of_range(raw) -> None:
    """Values outside the 16-bit holding-register range are rejected."""
    with pytest.raises(ServiceValidationError):
        parse_register_int(raw, "value")


# ---------------------------------------------------------------------------
# is_host_port_open (config_flow helper, but logic-tested here so it does
# not collide with config_flow's autouse mock_socket_connection fixture)
# ---------------------------------------------------------------------------


async def test_is_host_port_open_succeeds() -> None:
    """is_host_port_open returns True when asyncio reports a connection."""
    fake_writer = MagicMock()
    fake_writer.close = MagicMock()
    fake_writer.wait_closed = AsyncMock()
    with patch(
        "custom_components.neopool.config_flow.asyncio.open_connection",
        new=AsyncMock(return_value=(MagicMock(), fake_writer)),
    ):
        assert await is_host_port_open("127.0.0.1", 502) is True
    fake_writer.close.assert_called_once()


async def test_is_host_port_open_returns_false_on_oserror() -> None:
    """is_host_port_open returns False when the probe raises OSError."""
    with patch(
        "custom_components.neopool.config_flow.asyncio.open_connection",
        new=AsyncMock(side_effect=OSError("connection refused")),
    ):
        assert await is_host_port_open("127.0.0.1", 1) is False


async def test_is_host_port_open_returns_false_on_timeout() -> None:
    """is_host_port_open returns False when asyncio.wait_for times out."""
    with patch(
        "custom_components.neopool.config_flow.asyncio.wait_for",
        new=AsyncMock(side_effect=TimeoutError),
    ):
        assert await is_host_port_open("127.0.0.1", 1) is False


# ---------------------------------------------------------------------------
# async_get_device_serial
# ---------------------------------------------------------------------------


async def test_async_get_device_serial_success() -> None:
    """async_get_device_serial returns the serial when the probe succeeds."""

    config = {"host": "192.0.2.1", "port": 502, "unit_id": 1, "modbus_framer": "tcp"}
    with patch(
        "custom_components.neopool.helpers.async_probe_serial",
        new=AsyncMock(return_value="ABCDEF1234"),
    ):
        assert await async_get_device_serial(config) == "ABCDEF1234"


async def test_async_get_device_serial_legacy_slave_id_fallback() -> None:
    """Legacy configs with only ``slave_id`` are still routed correctly."""

    config = {"host": "192.0.2.1", "port": 502, "slave_id": 5, "modbus_framer": "tcp"}
    probe = AsyncMock(return_value="ABCDEF1234")
    with patch("custom_components.neopool.helpers.async_probe_serial", new=probe):
        assert await async_get_device_serial(config) == "ABCDEF1234"
    probe.assert_awaited_once()
    kwargs = probe.await_args.kwargs
    assert kwargs["unit_id"] == 5


async def test_async_get_device_serial_neopool_error_returns_none() -> None:
    """A NeoPoolError from the probe yields None and a warning log entry."""

    config = {"host": "192.0.2.1", "port": 502}
    with patch(
        "custom_components.neopool.helpers.async_probe_serial",
        new=AsyncMock(side_effect=NeoPoolError("connection refused")),
    ):
        assert await async_get_device_serial(config) is None


async def test_async_get_device_serial_propagates_cancelled_error() -> None:
    """async.CancelledError propagates so callers can act on cancellation."""

    config = {"host": "192.0.2.1", "port": 502}
    with (
        patch(
            "custom_components.neopool.helpers.async_probe_serial",
            new=AsyncMock(side_effect=_asyncio.CancelledError),
        ),
        pytest.raises(_asyncio.CancelledError),
    ):
        await async_get_device_serial(config)
