"""Common fixtures for the NeoPool tests."""

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.syrupy import HomeAssistantSnapshotExtension
from syrupy.assertion import SnapshotAssertion

from custom_components.neopool.const import (
    CURRENT_VERSION,
    DEFAULT_PORT,
    DEFAULT_SLAVE_ID,
    DOMAIN,
)
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT

MOCK_HOST = "192.0.2.1"
MOCK_PORT = DEFAULT_PORT
MOCK_NAME = "Pool"
MOCK_SERIAL = "1234567890"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Auto-load the custom integration in every test.

    pytest-homeassistant-custom-component ships an `enable_custom_integrations`
    fixture but it is opt-in by default; making it autouse means every test
    can resolve `custom_components.neopool` without each one redeclaring it.
    """
    return


@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Return a syrupy fixture using HA's snapshot extension.

    Stores snapshot files under `tests/snapshots/` (the HA convention)
    instead of syrupy's default `tests/__snapshots__/`.
    """
    return snapshot.use_extension(HomeAssistantSnapshotExtension)


# Minimal coordinator data for a healthy controller. Real device returns
# ~140 keys; the integration tolerates missing keys gracefully (entities
# show as unavailable). These cover the registers the coordinator's
# happy-path flow reads — firmware version, basic measurements, all GPIO
# registers (set to a valid relay so platforms register their entities),
# filtration state.
MOCK_POOL_DATA: dict[str, Any] = {
    "MBF_POWER_MODULE_VERSION": 0x1234,  # → firmware "18.52"
    "MBF_PAR_VERSION": 0x100,
    # MBF_PAR_MODEL bit 0x0001 = Ion module, 0x0002 = Hydro/Electrolysis —
    # both set so all conditional sensor / select entities register.
    "MBF_PAR_MODEL": 0x0003,
    "MBF_PAR_SERNUM": int(MOCK_SERIAL),
    # FILTRATION_CONF non-zero so the variable-speed selects register.
    "MBF_PAR_FILTRATION_CONF": 1,
    # GPIO assignments: each relay output is wired to a different physical
    # relay (1..7). Keep them valid so platforms register their entities.
    "MBF_PAR_FILT_GPIO": 1,
    "MBF_PAR_LIGHTING_GPIO": 2,
    "MBF_PAR_HEATING_GPIO": 3,
    "MBF_PAR_PH_ACID_RELAY_GPIO": 4,
    "MBF_PAR_PH_BASE_RELAY_GPIO": 5,
    "MBF_PAR_RX_RELAY_GPIO": 6,
    "MBF_PAR_CL_RELAY_GPIO": 7,
    "MBF_PAR_CD_RELAY_GPIO": 0,
    "MBF_PAR_UV_RELAY_GPIO": 1,
    # FILTVALVE_GPIO=1 makes has_filtvalve(data) True so the BACKWASH
    # button entity registers and its press path can be exercised.
    "MBF_PAR_FILTVALVE_GPIO": 1,
    "MBF_PAR_FILTVALVE_ENABLE": 1,
    # Capability flags so all the conditional climate / hydro switches
    # also register their entities.
    "MBF_PAR_TEMPERATURE_ACTIVE": 1,
    "Hydrolysis module detected": True,
    "Redox measurement module detected": True,
    "pH measurement module detected": True,
    "MBF_PAR_FILT_MODE": 0,  # manual
    "MBF_MEASURE_TEMPERATURE": 250,  # 25.0°C
    "MBF_MEASURE_PH": 720,  # 7.20
    "Filtration Pump": False,
    # Combined cover reduction / shutdown temperature register
    # (lower byte = cover reduction %, upper byte = shutdown temperature).
    # Pre-seeded so async_added_to_hass exercises the mask-decode path.
    "MBF_PAR_HIDRO_COVER_REDUCTION": 0x0C19,
    # Pool cover sensor binary (1 = pool covered, 0 = uncovered).
    "Pool Cover": 0,
    # Timer-block enable mirrors so light/aux relay-timer entities
    # report the correct state (3 = always ON, 4 = always OFF, 1 = auto).
    "relay_light_enable": 4,  # OFF
    "relay_aux1_enable": 4,
    "relay_aux2_enable": 4,
    "relay_aux3_enable": 4,
    "relay_aux4_enable": 4,
    # Cell-runtime 32-bit counters (LOW/HIGH word pairs).
    # Total = 0x0001_0000 s = 65536 s; Partial = 0x0000_0E10 s = 3600 s (1 hour);
    # Pol1/Pol2 split the partial roughly in half; pol-changes count = 7.
    "MBF_CELL_RUNTIME_LOW": 0x0000,
    "MBF_CELL_RUNTIME_HIGH": 0x0001,
    "MBF_CELL_RUNTIME_PART_LOW": 0x0E10,
    "MBF_CELL_RUNTIME_PART_HIGH": 0x0000,
    "MBF_CELL_RUNTIME_POLA_LOW": 0x0708,
    "MBF_CELL_RUNTIME_POLA_HIGH": 0x0000,
    "MBF_CELL_RUNTIME_POLB_LOW": 0x0708,
    "MBF_CELL_RUNTIME_POLB_HIGH": 0x0000,
    "MBF_CELL_RUNTIME_POL_CHANGES_LOW": 0x0007,
    "MBF_CELL_RUNTIME_POL_CHANGES_HIGH": 0x0000,
}


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Override async_setup_entry."""
    with patch(
        "custom_components.neopool.async_setup_entry", return_value=True
    ) as mock_setup_entry:
        yield mock_setup_entry


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a config entry with every optional feature toggle enabled.

    Keeping every option turned on by default means a single fixture covers
    the entity-discovery happy path for every platform; tests that need a
    leaner setup can override `options` per-test.
    """
    return MockConfigEntry(
        domain=DOMAIN,
        title=MOCK_NAME,
        unique_id=f"neopool_{MOCK_SERIAL}",
        version=CURRENT_VERSION,
        data={
            CONF_HOST: MOCK_HOST,
            CONF_PORT: MOCK_PORT,
            CONF_NAME: MOCK_NAME,
            "slave_id": DEFAULT_SLAVE_ID,
            "modbus_framer": "tcp",
        },
        options={
            "scan_interval": 30,
            "modbus_framer": "tcp",
            "use_filtration1": True,
            "use_filtration2": True,
            "use_filtration3": True,
            "use_light": True,
            "use_cover_sensor": True,
            "use_aux1": True,
            "use_aux2": True,
            "use_aux3": True,
            "use_aux4": True,
        },
    )


@pytest.fixture
def mock_neopool_client() -> Generator[MagicMock]:
    """Patch the NeoPoolModbusClient and return a configurable mock instance."""
    with (
        patch(
            "custom_components.neopool.NeoPoolModbusClient",
            autospec=True,
        ) as mock_client_cls,
        patch(
            "custom_components.neopool.config_flow.async_get_device_serial",
            new=AsyncMock(return_value=MOCK_SERIAL),
        ),
    ):
        mock_client = mock_client_cls.return_value
        mock_client.async_read_all = AsyncMock(return_value=dict(MOCK_POOL_DATA))
        mock_client.read_all_timers = AsyncMock(return_value={})
        mock_client.async_write_register = AsyncMock(
            return_value={"value": 0, "confirmed": 0}
        )
        mock_client.write_timer = AsyncMock()
        mock_client.close = AsyncMock()
        yield mock_client


@pytest.fixture
def minimal_pool_data() -> dict[str, Any]:
    """Pool data with all optional capability flags off.

    Used to drive the 'should-skip' branches in every platform that
    suppress entities when the corresponding module / relay is absent.
    Hardcoded copy rather than a dict subtraction so the suppressed
    state is explicit at the call site.
    """
    return {
        "MBF_POWER_MODULE_VERSION": 0x1234,
        "MBF_PAR_VERSION": 0x100,
        # No bits set → no Ion, no Hydro, no special entities
        "MBF_PAR_MODEL": 0,
        "MBF_PAR_SERNUM": int(MOCK_SERIAL),
        "MBF_PAR_FILTRATION_CONF": 0,
        # All GPIO assignments are zero → entities that gate on a valid
        # relay GPIO (light, climate, UV, aux pumps, etc.) skip themselves.
        "MBF_PAR_FILT_GPIO": 0,
        "MBF_PAR_LIGHTING_GPIO": 0,
        "MBF_PAR_HEATING_GPIO": 0,
        "MBF_PAR_PH_ACID_RELAY_GPIO": 0,
        "MBF_PAR_PH_BASE_RELAY_GPIO": 0,
        "MBF_PAR_RX_RELAY_GPIO": 0,
        "MBF_PAR_CL_RELAY_GPIO": 0,
        "MBF_PAR_CD_RELAY_GPIO": 0,
        "MBF_PAR_UV_RELAY_GPIO": 0,
        "MBF_PAR_FILTVALVE_GPIO": 0,
        "MBF_PAR_FILTVALVE_ENABLE": 0,
        # No temperature sensor and no detected modules
        "MBF_PAR_TEMPERATURE_ACTIVE": 0,
        "Hydrolysis module detected": False,
        "Redox measurement module detected": False,
        "pH measurement module detected": False,
        "MBF_PAR_FILT_MODE": 0,
        "Filtration Pump": False,
    }


@pytest.fixture
def mock_neopool_client_minimal(
    minimal_pool_data: dict[str, Any],
) -> Generator[MagicMock]:
    """Like mock_neopool_client but seeded with minimal_pool_data.

    Use to exercise platform 'skip-because-disabled' branches.
    """
    with (
        patch(
            "custom_components.neopool.NeoPoolModbusClient",
            autospec=True,
        ) as mock_client_cls,
        patch(
            "custom_components.neopool.config_flow.async_get_device_serial",
            new=AsyncMock(return_value=MOCK_SERIAL),
        ),
    ):
        mock_client = mock_client_cls.return_value
        mock_client.async_read_all = AsyncMock(return_value=dict(minimal_pool_data))
        mock_client.read_all_timers = AsyncMock(return_value={})
        mock_client.async_write_register = AsyncMock(
            return_value={"value": 0, "confirmed": 0}
        )
        mock_client.write_timer = AsyncMock()
        mock_client.close = AsyncMock()
        yield mock_client


@pytest.fixture
def mock_socket_connection() -> Generator[None]:
    """Patch the TCP probe in config_flow so we don't hit the network.

    Not autouse — opt in via the fixture name when the integration's
    config-flow setup runs in the test (it would otherwise try to open
    a real TCP connection).
    """
    with patch(
        "custom_components.neopool.config_flow.is_host_port_open",
        new=AsyncMock(return_value=True),
    ):
        yield
