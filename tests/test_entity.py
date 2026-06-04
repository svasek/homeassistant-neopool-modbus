# Copyright 2025 Miloš Svašek

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from unittest.mock import MagicMock

import pytest

from custom_components.neopool.entity import VistaPoolEntity


@pytest.mark.parametrize(
    "bitmask,expected",
    [
        (None, "Unknown"),  # Should return 'Unknown' for None
        (0x0000, "None"),  # Should return 'None' for 0
        (0x0001, "Ionization"),  # Only Ionization
        (0x0002, "Hydro/Electrolysis"),  # Only Hydro/Electrolysis
        (0x0004, "UV Lamp"),  # Only UV Lamp
        (0x0008, "Salinity"),  # Only Salinity
        (0x0001 | 0x0002, "Ionization, Hydro/Electrolysis"),  # Multiple bits
        (0x0001 | 0x0004, "Ionization, UV Lamp"),
        (0x0002 | 0x0004 | 0x0008, "Hydro/Electrolysis, UV Lamp, Salinity"),
        (
            0x0001 | 0x0002 | 0x0004 | 0x0008,
            "Ionization, Hydro/Electrolysis, UV Lamp, Salinity",
        ),
        (
            0xFFFF,
            "Ionization, Hydro/Electrolysis, UV Lamp, Salinity",
        ),  # All known bits set, higher bits ignored
    ],
)
def test_decode_modules(bitmask, expected):
    """Test decode_modules returns correct module names for bitmask."""
    result = VistaPoolEntity.decode_modules(bitmask)
    assert result == expected


@pytest.mark.parametrize(
    "input_name,expected",
    [
        ("MBF_PAR_FOO_BAR", "foo_bar"),
        ("mbf_par_ph1", "ph1"),
        ("par_ph1", "ph1"),
        ("mbf_something", "something"),
        ("PAR_ANOTHER", "another"),
        ("some_value", "some_value"),
        ("MBF_SOME-Value.42", "some_value_42"),
        ("", ""),  # Empty string stays empty
        (None, ""),  # None returns empty
        ("MBF_Mixed-Case.Test", "mixed_case_test"),
    ],
)
def test_slugify(input_name, expected):
    """Test slugify generates expected slugs."""
    assert VistaPoolEntity.slugify(input_name) == expected


def _make_entity(
    winter_mode: bool, switch_type: str | None = None, last_update_success: bool = True
) -> VistaPoolEntity:
    """Create a minimal VistaPoolEntity with a mocked coordinator."""
    coordinator = MagicMock()
    coordinator.winter_mode = winter_mode
    coordinator.last_update_success = last_update_success
    entity = VistaPoolEntity.__new__(VistaPoolEntity)
    entity.coordinator = coordinator
    if switch_type is not None:
        entity._switch_type = switch_type  # type: ignore[attr-defined]
    return entity


def test_available_normal_mode():
    """Entity is available when winter mode is off and coordinator is healthy."""
    assert _make_entity(winter_mode=False).available is True


def test_available_coordinator_failure():
    """Entity is unavailable when coordinator update fails (last_update_success=False)."""
    assert _make_entity(winter_mode=False, last_update_success=False).available is False


def test_available_winter_mode_active():
    """Entity with _winter_mode_active=True (default) is unavailable during winter mode."""
    assert _make_entity(winter_mode=True).available is False


def test_available_unaffected_by_winter_mode():
    """Entity with _winter_mode_active=False stays available even during winter mode."""
    entity = _make_entity(winter_mode=True)
    entity._winter_mode_active = False
    assert entity.available is True
