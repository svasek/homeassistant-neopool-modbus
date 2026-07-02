"""Tests for the NeoPool helper functions."""

from datetime import UTC, datetime
from unittest.mock import patch

from neopool_modbus.capabilities import has_filtvalve
import pytest

from custom_components.neopool.helpers import (
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
    rather than UTC epoch; the library's ``decode_device_time`` reads that
    wall-clock value in the caller-provided tz and returns a UTC datetime.
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
        # detection, corrupted register values should not auto-create entities.
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
def test_parse_register_int_valid(raw: int | str, expected: int) -> None:
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
def test_parse_register_int_rejects_out_of_range(raw: int | str) -> None:
    """Values outside the 16-bit holding-register range are rejected."""
    with pytest.raises(ServiceValidationError):
        parse_register_int(raw, "value")
