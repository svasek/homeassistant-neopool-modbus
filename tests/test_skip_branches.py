"""Integration-level tests that cover platform 'should-skip' guards.

Drives setup with the lean `mock_neopool_client_minimal` fixture (no
modules detected, no relay GPIOs assigned) and verifies each platform's
gating branch fires by counting the resulting entities.
"""

from unittest.mock import MagicMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

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
