"""Tests for the NeoPool helper functions."""

from unittest.mock import patch

from neopool_modbus.capabilities import has_filtvalve
import pytest

from custom_components.neopool.helpers import (
    is_device_time_out_of_sync,
    parse_register_int,
    prepare_device_time,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

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

# ``MBF_PAR_TIME`` and ``prepare_device_time`` share a TZ-less wall-clock epoch,
# so the tests compare the two directly and never decode through a timezone.
_NOW_WALL = 1_700_000_000


# CUSTOM-ONLY START, device time-drift helpers are HACS-only.
def test_is_device_time_out_of_sync_within_threshold(hass: HomeAssistant) -> None:
    """A small drift between device and HA returns False."""
    data = {"MBF_PAR_TIME": _NOW_WALL}
    with patch(
        "custom_components.neopool.helpers.prepare_device_time",
        return_value=_NOW_WALL,
    ):
        assert is_device_time_out_of_sync(data, hass, threshold_seconds=60) is False


def test_is_device_time_out_of_sync_above_threshold(hass: HomeAssistant) -> None:
    """A drift larger than threshold returns True."""
    data = {"MBF_PAR_TIME": _NOW_WALL - 7200}  # device 2 hours behind
    with patch(
        "custom_components.neopool.helpers.prepare_device_time",
        return_value=_NOW_WALL,
    ):
        assert is_device_time_out_of_sync(data, hass, threshold_seconds=60) is True


def test_is_device_time_out_of_sync_no_data(hass: HomeAssistant) -> None:
    """Missing time registers means we cannot detect drift, so return False."""
    assert is_device_time_out_of_sync({}, hass, threshold_seconds=60) is False


def test_is_device_time_out_of_sync_default_threshold(hass: HomeAssistant) -> None:
    """The default tolerance is loose: a drift under 5 minutes is ignored."""
    data = {"MBF_PAR_TIME": _NOW_WALL - 120}  # device 2 minutes behind
    with patch(
        "custom_components.neopool.helpers.prepare_device_time",
        return_value=_NOW_WALL,
    ):
        assert is_device_time_out_of_sync(data, hass) is False
        assert is_device_time_out_of_sync(data, hass, threshold_seconds=60) is True


# CUSTOM-ONLY END
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
