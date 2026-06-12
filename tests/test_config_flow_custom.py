"""HACS-only config-flow tests — vistapool import + v1 duplicate abort.

These cover behaviour that has no counterpart in the core integration:
the legacy ``vistapool`` domain rename detection, the import step that
moves an entry across domains, and the v1 unmigrated-duplicate abort
that catches connection-param matches before the unique_id is set.

Core ships fresh entries at v1 with no migration story — the sync
script excludes this whole file via ``EXCLUDE_TEST_FILES``.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.neopool import config_flow
from custom_components.neopool.const import DEFAULT_PORT, DEFAULT_SLAVE_ID, DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

# These tests must not hit the network either — same fixture as the main
# config-flow module.
pytestmark = pytest.mark.usefixtures("mock_socket_connection")


# ---------------------------------------------------------------------------
# v1 unmigrated entry duplicate detection
# ---------------------------------------------------------------------------


async def test_create_entry_aborts_unmigrated_v1_duplicate(
    hass: HomeAssistant,
    mock_neopool_client: MagicMock,
) -> None:
    """Adding a device aborts when an unmigrated v1 entry has same connection params."""
    # Simulate an existing v1 entry (unique_id=None, version=1).
    existing = MockConfigEntry(
        domain=DOMAIN,
        title="Existing",
        unique_id=None,
        version=1,
        data={
            CONF_HOST: "192.168.1.100",
            CONF_PORT: DEFAULT_PORT,
            "slave_id": DEFAULT_SLAVE_ID,
            "modbus_framer": "tcp",
        },
    )
    existing.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "My Pool",
            CONF_HOST: "192.168.1.100",
            CONF_PORT: DEFAULT_PORT,
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


# ---------------------------------------------------------------------------
# Legacy vistapool import flow — routing + step variants
# (these tests drive the flow object directly to keep coverage of the
# branches that the framework path doesn't reach in a single hass run)
# ---------------------------------------------------------------------------


async def test_user_step_routes_to_import_when_legacy_entry_exists() -> None:
    """When a legacy vistapool entry is present, user step routes to import flow."""
    flow = config_flow.NeoPoolConfigFlow()
    flow.hass = MagicMock()

    legacy_entry = MagicMock()
    legacy_entry.entry_id = "legacy_entry_xyz"
    legacy_entry.title = "Bazén"
    legacy_entry.domain = "vistapool"
    flow.hass.config_entries.async_entries = MagicMock(return_value=[legacy_entry])
    # The import step re-resolves the legacy entry by id; return it again
    flow.hass.config_entries.async_get_entry.return_value = legacy_entry

    result = await flow.async_step_user(user_input=None)
    assert result is not None
    assert result["type"] == "form"
    # The form must be the import confirmation, not the regular new-entry one
    assert result["step_id"] == "import_from_vistapool"
    # And the entry title must be propagated to the description
    assert result["description_placeholders"]["entry_title"] == "Bazén"
    # State on the flow object must be set so the migrate step can resolve it
    assert flow._legacy_entry_id == "legacy_entry_xyz"
    assert flow._legacy_entry_title == "Bazén"


async def test_import_step_falls_back_to_user_when_legacy_gone() -> None:
    """If the legacy entry vanished between detection and Submit, fall back to user."""
    flow = config_flow.NeoPoolConfigFlow()
    flow.hass = MagicMock()
    flow._legacy_entry_id = "stale_entry"
    flow._legacy_entry_title = "Bazén"
    # Legacy entry no longer in registry
    flow.hass.config_entries.async_get_entry.return_value = None
    # async_step_user fallback needs an empty list to render the regular form
    flow.hass.config_entries.async_entries = MagicMock(return_value=[])

    result = await flow.async_step_import_from_vistapool(user_input=None)
    assert result is not None
    # Fall through path — the regular new-entry form is shown
    assert result["type"] == "form"
    assert result["step_id"] == "user"


async def test_import_step_falls_back_when_entry_is_not_vistapool() -> None:
    """If the resolved entry isn't a vistapool entry, fall back to user."""
    flow = config_flow.NeoPoolConfigFlow()
    flow.hass = MagicMock()
    flow._legacy_entry_id = "some_entry"
    flow._legacy_entry_title = "Bazén"

    other_entry = MagicMock()
    other_entry.domain = "neopool"  # not vistapool — race against another flow
    flow.hass.config_entries.async_get_entry.return_value = other_entry
    flow.hass.config_entries.async_entries = MagicMock(return_value=[])

    result = await flow.async_step_import_from_vistapool(user_input=None)
    assert result["type"] == "form"
    assert result["step_id"] == "user"


async def test_import_step_shows_form_on_first_call() -> None:
    """First call (no user_input) shows the confirmation form with placeholders."""
    flow = config_flow.NeoPoolConfigFlow()
    flow.hass = MagicMock()
    flow._legacy_entry_id = "legacy_entry"
    flow._legacy_entry_title = "Bazén"

    legacy_entry = MagicMock()
    legacy_entry.domain = "vistapool"
    flow.hass.config_entries.async_get_entry.return_value = legacy_entry

    result = await flow.async_step_import_from_vistapool(user_input=None)
    assert result["type"] == "form"
    assert result["step_id"] == "import_from_vistapool"
    assert result["description_placeholders"]["entry_title"] == "Bazén"


async def test_import_step_dispatches_migration_complete() -> None:
    """Submit → import helper returns migration_complete → flow aborts."""
    flow = config_flow.NeoPoolConfigFlow()
    flow.hass = MagicMock()
    flow._legacy_entry_id = "legacy_entry"
    flow._legacy_entry_title = "Bazén"

    legacy_entry = MagicMock()
    legacy_entry.domain = "vistapool"
    flow.hass.config_entries.async_get_entry.return_value = legacy_entry

    with patch(
        "custom_components.neopool.migration.async_import_legacy_vistapool_entry",
        new=AsyncMock(return_value=("migration_complete", None)),
    ):
        result = await flow.async_step_import_from_vistapool(user_input={})

    assert result["type"] == "abort"
    assert result["reason"] == "migration_complete"


async def test_import_step_dispatches_migration_failed() -> None:
    """Submit → import helper returns migration_failed → flow aborts with error."""
    flow = config_flow.NeoPoolConfigFlow()
    flow.hass = MagicMock()
    flow._legacy_entry_id = "legacy_entry"
    flow._legacy_entry_title = "Bazén"

    legacy_entry = MagicMock()
    legacy_entry.domain = "vistapool"
    flow.hass.config_entries.async_get_entry.return_value = legacy_entry

    with patch(
        "custom_components.neopool.migration.async_import_legacy_vistapool_entry",
        new=AsyncMock(return_value=("migration_failed", "boom")),
    ):
        result = await flow.async_step_import_from_vistapool(user_input={})

    assert result["type"] == "abort"
    assert result["reason"] == "migration_failed"
    assert result["description_placeholders"]["error"] == "boom"


async def test_import_step_falls_through_when_legacy_disappears_in_helper() -> None:
    """Submit → import helper returns (None, None) → flow falls through to user step."""
    flow = config_flow.NeoPoolConfigFlow()
    flow.hass = MagicMock()
    flow._legacy_entry_id = "legacy_entry"
    flow._legacy_entry_title = "Bazén"

    legacy_entry = MagicMock()
    legacy_entry.domain = "vistapool"
    flow.hass.config_entries.async_get_entry.return_value = legacy_entry
    # No legacy vistapool entries → async_step_user goes to fresh form
    flow.hass.config_entries.async_entries = MagicMock(return_value=[])

    with patch(
        "custom_components.neopool.migration.async_import_legacy_vistapool_entry",
        new=AsyncMock(return_value=(None, None)),
    ):
        result = await flow.async_step_import_from_vistapool(user_input={})

    # async_step_user shows the regular new-entry form
    assert result["type"] == "form"
    assert result["step_id"] == "user"
