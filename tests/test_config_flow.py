"""Test the NeoPool config flow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.neopool import config_flow
from custom_components.neopool.config_flow import NeoPoolConfigFlow
from custom_components.neopool.const import DEFAULT_PORT, DEFAULT_SLAVE_ID, DOMAIN
from custom_components.neopool.options_flow import NeoPoolOptionsFlowHandler
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import MOCK_HOST, MOCK_NAME, MOCK_PORT, MOCK_SERIAL

# Most config-flow tests should not hit the network — opt in to the
# is_host_port_open patch for every test in this module by default.
# Tests that exercise is_host_port_open itself opt out by name in the
# test signature (they don't take the fixture).
pytestmark = pytest.mark.usefixtures("mock_socket_connection")

USER_INPUT = {
    CONF_NAME: MOCK_NAME,
    CONF_HOST: MOCK_HOST,
    CONF_PORT: MOCK_PORT,
}


# ---------------------------------------------------------------------------
# User flow — happy path + recoverable errors
# ---------------------------------------------------------------------------


async def test_user_flow(
    hass: HomeAssistant,
    mock_neopool_client: MagicMock,
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
    assert result["title"] == MOCK_NAME
    assert result["data"][CONF_HOST] == MOCK_HOST
    assert result["data"][CONF_PORT] == MOCK_PORT
    assert result["result"].unique_id == f"neopool_{MOCK_SERIAL}"
    assert mock_setup_entry.call_count == 1


async def test_user_flow_cannot_connect(
    hass: HomeAssistant,
    mock_neopool_client: MagicMock,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test config flow surfaces a cannot_connect error and recovers."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            config_flow,
            "is_host_port_open",
            AsyncMock(return_value=False),
        )

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_HOST: "cannot_connect"}

    # Recover: probe now succeeds
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_cannot_read_modbus(
    hass: HomeAssistant,
    mock_neopool_client: MagicMock,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test config flow surfaces cannot_read_modbus when serial probe fails."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            config_flow,
            "async_get_device_serial",
            AsyncMock(return_value=None),
        )

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_HOST: "cannot_read_modbus"}

    # Recover: serial probe now succeeds
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_already_configured(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Test config flow aborts when the same device is already configured."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Different Name",
            CONF_HOST: MOCK_HOST,
            CONF_PORT: MOCK_PORT,
        },
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow_name_already_used(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Test name collision (different device, same name slug) yields a form error."""
    mock_config_entry.add_to_hass(hass)

    # Make the new device's serial probe return a *different* serial so we
    # don't trip the unique_id "already_configured" abort first.
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            config_flow,
            "async_get_device_serial",
            AsyncMock(return_value="9999999999"),
        )

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_NAME: MOCK_NAME,  # same as existing entry
                CONF_HOST: "192.0.2.99",
                CONF_PORT: MOCK_PORT,
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_NAME: "name_already_used"}


# ---------------------------------------------------------------------------
# Reconfigure flow
# ---------------------------------------------------------------------------


async def test_reconfigure_flow_happy_path(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
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
            "slave_id": 2,
            "modbus_framer": "tcp",
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


async def test_reconfigure_flow_cannot_connect(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """A reconfigure flow with an unreachable host shows the cannot_connect error."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reconfigure_flow(hass)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config_flow, "is_host_port_open", AsyncMock(return_value=False))
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.0.2.99",
                CONF_PORT: 502,
                "slave_id": 1,
                "modbus_framer": "tcp",
            },
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_HOST: "cannot_connect"}


async def test_reconfigure_flow_serial_mismatch(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """A reconfigure that targets a different physical controller is rejected."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reconfigure_flow(hass)

    with pytest.MonkeyPatch.context() as mp:
        # The probe returns a *different* serial than the entry's unique_id.
        mp.setattr(
            config_flow,
            "async_get_device_serial",
            AsyncMock(return_value="9999999999"),
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.0.2.50",
                CONF_PORT: 502,
                "slave_id": 1,
                "modbus_framer": "tcp",
            },
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_HOST: "serial_mismatch"}


async def test_reconfigure_flow_cannot_read_modbus(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """If the serial probe fails on reconfigure, we surface cannot_read_modbus."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reconfigure_flow(hass)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            config_flow,
            "async_get_device_serial",
            AsyncMock(return_value=None),
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.0.2.50",
                CONF_PORT: 502,
                "slave_id": 1,
                "modbus_framer": "tcp",
            },
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_HOST: "cannot_read_modbus"}


# ---------------------------------------------------------------------------
# Helpers covered indirectly above; explicit unit tests below.
# ---------------------------------------------------------------------------

# Note: tests for is_host_port_open are in test_helpers.py — keeping them
# out of this module avoids fighting with the module-level
# pytestmark.usefixtures("mock_socket_connection") that every config-flow
# test relies on.


async def test_default_name_translation_failure_falls_back(
    hass: HomeAssistant,
    mock_neopool_client: MagicMock,
) -> None:
    """If the translation lookup explodes, _async_get_default_name returns the literal default."""

    with patch(
        "homeassistant.helpers.translation.async_get_translations",
        side_effect=RuntimeError("boom"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
    # Form opens with the literal default rather than crashing the flow.
    assert result["type"] is FlowResultType.FORM


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
