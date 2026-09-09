"""Common fixtures for the NeoPool tests."""

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

# CUSTOM-ONLY START
from pytest_homeassistant_custom_component.syrupy import HomeAssistantSnapshotExtension
from syrupy.assertion import SnapshotAssertion

# CUSTOM-ONLY END
from custom_components.neopool.const import (
    CONF_MODBUS_FRAMER,
    CONF_UNIT_ID,
    CONF_USE_AUX1,
    CONF_USE_AUX2,
    CONF_USE_AUX3,
    CONF_USE_AUX4,
    CONF_USE_COVER_SENSOR,
    CONF_USE_FILTRATION1,
    CONF_USE_FILTRATION2,
    CONF_USE_FILTRATION3,
    CONF_USE_LIGHT,
    CURRENT_VERSION,
    DEFAULT_PORT,
    DEFAULT_UNIT_ID,
    DOMAIN,
)
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT

MOCK_HOST = "192.0.2.1"
MOCK_PORT = DEFAULT_PORT
MOCK_NAME = "Pool"
MOCK_SERIAL = "1234567890"


# CUSTOM-ONLY START
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


@pytest.fixture
def entity_registry_enabled_by_default() -> Generator[None]:
    """Enable all entities in the registry (local copy of the core fixture).

    Core ships this in tests/components/conftest.py; phacc does not, so the
    custom suite defines it locally. Lets snapshot tests capture entities
    that are `entity_registry_enabled_default=False`.
    """
    with patch(
        "homeassistant.helpers.entity.Entity.entity_registry_enabled_default",
        return_value=True,
    ):
        yield


# CUSTOM-ONLY END


# Minimal coordinator data for a healthy controller. Real device returns
# ~140 keys; the integration tolerates missing keys gracefully (entities
# show as unavailable). These cover the registers the coordinator's
# happy-path flow reads, firmware version, basic measurements, all GPIO
# registers (set to a valid relay so platforms register their entities),
# filtration state.
MOCK_POOL_DATA: dict[str, Any] = {
    "MBF_POWER_MODULE_VERSION": 0x1234,  # → firmware "18.52"
    "MBF_PAR_VERSION": 0x100,
    # MBF_PAR_MODEL bit 0x0001 = Ion module, 0x0002 = Hydro/Electrolysis,
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
    "MBF_PAR_UICFG_MACHINE": 0,
    "MBF_PAR_RELAY_PH": 0,
    "Hydrolysis module detected": True,
    "Redox measurement module detected": True,
    "pH measurement module detected": True,
    "Chlorine measurement module detected": True,
    "Conductivity measurement module detected": True,
    "Ionization module detected": True,
    "MBF_PAR_FILT_MODE": 0,  # manual
    "filtration_mode": "manual",
    "filtration_speed_state": "off",
    "MBF_MEASURE_TEMPERATURE": 250,  # 25.0°C
    "MBF_MEASURE_PH": 720,  # 7.20
    "MBF_MEASURE_RX": 650,  # 650 mV
    "MBF_MEASURE_CL": 120,  # 1.20 ppm
    "MBF_MEASURE_CONDUCTIVITY": 45,  # 45 %
    "MBF_HIDRO_CURRENT": 70,  # 70 %
    "MBF_HIDRO_VOLTAGE": 24,  # 2.4 V
    "MBF_ION_CURRENT": 50,  # 50 %
    "MBF_PAR_INTELLIGENT_INTERVALS": 4,
    "MBF_PAR_INTELLIGENT_TT_NEXT_INTERVAL": 7200,
    "MBF_PAR_FILTVALVE_REMAINING": 0,
    "MBF_PAR_FILTVALVE_INTERVAL": 150,
    # 4 = always_off (manual): keeps the BACKWASH switch out of the AUTO guard
    # so its happy-path start/stop tests can drive the valve.
    "MBF_PAR_FILTVALVE_MODE": 4,
    # Decoded polarity / pH pump keys populated by the library on real reads;
    # pre-seed them so ENUM sensors read a valid option without an extra tick.
    "HIDRO_POLARITY": "off",
    "ION_POLARITY": "off",
    "PH_PUMP_STATUS": "off",
    # Raw pH-pump bits the ENUM decoder reads.
    "pH control module": True,
    "pH pump active": False,
    "pH acid pump active": False,
    # Raw polarity bits the ENUM decoder reads.
    "HIDRO in Pol1": False,
    "HIDRO in Pol2": False,
    "HIDRO in dead time": False,
    "ION in Pol1": False,
    "ION in Pol2": False,
    "ION in dead time": False,
    # Named relay states decoded from MBF_RELAY_STATE via the GPIO mapping.
    "Filtration Pump": False,
    "pH Acid Pump": False,
    # Measurement / module "active" bits. The controller keeps measuring the
    # probes regardless of filtration state, so these read True even though the
    # filtration pump above is off.
    "pH measurement active": True,
    "Redox measurement active": True,
    "Chlorine measurement active": True,
    "Conductivity measurement active": True,
    "HIDRO Module active": True,
    # Combined cover reduction / shutdown temperature register
    # (lower byte = cover reduction %, upper byte = shutdown temperature).
    # Pre-seeded so async_added_to_hass exercises the mask-decode path.
    "MBF_PAR_HIDRO_COVER_REDUCTION": 0x0C19,
    # HIDRO options bitfield (bit 0 = cover reduction enabled, bit 1 =
    # shutdown-on-high-temperature enabled). Both switches read their is_on
    # from this key; the library returns it in optimistic writes.
    "MBF_PAR_HIDRO_COVER_ENABLE": 0x0000,
    # Pool cover sensor binary (1 = pool covered, 0 = uncovered).
    "Pool Cover": 0,
    # Cell-runtime 32-bit counters (lib 3.1.3+ collapses LOW/HIGH pairs).
    # Total = 0x0001_0000 s = 65536 s; Partial = 0x0000_0E10 s = 3600 s (1 hour);
    # Pol1/Pol2 split the partial roughly in half; pol-changes count = 7.
    "CELL_RUNTIME_TOTAL": 0x00010000,
    "CELL_RUNTIME_PART": 0x00000E10,
    "CELL_RUNTIME_POLA": 0x00000708,
    "CELL_RUNTIME_POLB": 0x00000708,
    "CELL_RUNTIME_POL_CHANGES": 0x00000007,
}


# Aux relay timer blocks default to a manual (ALWAYS_OFF) mode so switch writes
# pass the manual-mode guard; tests override the returned mode per case. Every
# field consumed by the coordinator is present (enable/on/interval/period/
# countdown/stop) so the derived data keys resolve for real timer polling.
def _timer_block(enable: int = 4) -> dict[str, Any]:
    """Return a full timer block dict for the mock read_all_timers."""
    return {
        "enable": enable,
        "on": 0,
        "interval": 0,
        "period": 0,
        "countdown": 0,
        "stop": None,
    }


MOCK_TIMER_BLOCKS: dict[str, dict[str, Any]] = {
    "relay_aux1": _timer_block(),
    "relay_aux2": _timer_block(),
    "relay_aux3": _timer_block(),
    "relay_aux4": _timer_block(),
}


def _read_all_timers(
    enabled_timers: list[str] | None = None, **_kwargs: Any
) -> dict[str, dict[str, Any]]:
    """Return the requested timer blocks, mirroring the library contract."""
    if enabled_timers is None:
        return {name: dict(block) for name, block in MOCK_TIMER_BLOCKS.items()}
    return {
        name: dict(MOCK_TIMER_BLOCKS[name])
        for name in enabled_timers
        if name in MOCK_TIMER_BLOCKS
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
    """Return a config entry with no optional features enabled.

    Feature-gated entities are exercised through the per-feature fixtures
    (`mock_config_entry_light`, `mock_config_entry_switch`, ...) or by
    overriding `options` per-test.
    """
    return MockConfigEntry(
        domain=DOMAIN,
        title=MOCK_NAME,
        unique_id=MOCK_SERIAL,
        version=CURRENT_VERSION,
        data={
            CONF_HOST: MOCK_HOST,
            CONF_PORT: MOCK_PORT,
            CONF_NAME: MOCK_NAME,
            CONF_UNIT_ID: DEFAULT_UNIT_ID,
            CONF_MODBUS_FRAMER: "tcp",
        },
    )


@pytest.fixture
def mock_config_entry_light() -> MockConfigEntry:
    """Return a config entry with the pool light option enabled."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=MOCK_NAME,
        unique_id=MOCK_SERIAL,
        version=CURRENT_VERSION,
        data={
            CONF_HOST: MOCK_HOST,
            CONF_PORT: MOCK_PORT,
            CONF_NAME: MOCK_NAME,
            CONF_UNIT_ID: DEFAULT_UNIT_ID,
            CONF_MODBUS_FRAMER: "tcp",
        },
        options={CONF_USE_LIGHT: True},
    )


@pytest.fixture
def mock_config_entry_switch() -> MockConfigEntry:
    """Return a config entry with the option-gated switches enabled."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=MOCK_NAME,
        unique_id=MOCK_SERIAL,
        version=CURRENT_VERSION,
        data={
            CONF_HOST: MOCK_HOST,
            CONF_PORT: MOCK_PORT,
            CONF_NAME: MOCK_NAME,
            CONF_UNIT_ID: DEFAULT_UNIT_ID,
            CONF_MODBUS_FRAMER: "tcp",
        },
        options={
            CONF_USE_COVER_SENSOR: True,
            CONF_USE_AUX1: True,
            CONF_USE_AUX2: True,
            CONF_USE_AUX3: True,
            CONF_USE_AUX4: True,
        },
    )


# CUSTOM-ONLY START
@pytest.fixture
def mock_config_entry_number() -> MockConfigEntry:
    """Return a config entry with the options the number platform gates on."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=MOCK_NAME,
        unique_id=MOCK_SERIAL,
        version=CURRENT_VERSION,
        data={
            CONF_HOST: MOCK_HOST,
            CONF_PORT: MOCK_PORT,
            CONF_NAME: MOCK_NAME,
            CONF_UNIT_ID: DEFAULT_UNIT_ID,
            CONF_MODBUS_FRAMER: "tcp",
        },
        options={CONF_USE_COVER_SENSOR: True},
    )


@pytest.fixture
def mock_config_entry_binary_sensor() -> MockConfigEntry:
    """Return a config entry with the options the binary_sensor platform gates on."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=MOCK_NAME,
        unique_id=MOCK_SERIAL,
        version=CURRENT_VERSION,
        data={
            CONF_HOST: MOCK_HOST,
            CONF_PORT: MOCK_PORT,
            CONF_NAME: MOCK_NAME,
            CONF_UNIT_ID: DEFAULT_UNIT_ID,
            CONF_MODBUS_FRAMER: "tcp",
        },
        options={
            CONF_USE_LIGHT: True,
            CONF_USE_COVER_SENSOR: True,
            CONF_USE_AUX1: True,
            CONF_USE_AUX2: True,
            CONF_USE_AUX3: True,
            CONF_USE_AUX4: True,
        },
    )


@pytest.fixture
def mock_config_entry_timers() -> MockConfigEntry:
    """Return a config entry enabling the light, aux, and filtration timers.

    Shared by the time and select platforms, which register timer / mode
    entities for every enabled relay-timer block.
    """
    return MockConfigEntry(
        domain=DOMAIN,
        title=MOCK_NAME,
        unique_id=MOCK_SERIAL,
        version=CURRENT_VERSION,
        data={
            CONF_HOST: MOCK_HOST,
            CONF_PORT: MOCK_PORT,
            CONF_NAME: MOCK_NAME,
            CONF_UNIT_ID: DEFAULT_UNIT_ID,
            CONF_MODBUS_FRAMER: "tcp",
        },
        options={
            CONF_USE_LIGHT: True,
            CONF_USE_FILTRATION1: True,
            CONF_USE_FILTRATION2: True,
            CONF_USE_FILTRATION3: True,
            CONF_USE_AUX1: True,
            CONF_USE_AUX2: True,
            CONF_USE_AUX3: True,
            CONF_USE_AUX4: True,
        },
    )


# CUSTOM-ONLY END


@pytest.fixture
def mock_neopool_client() -> Generator[MagicMock]:
    """Patch the NeoPoolModbusClient and return a configurable mock instance."""
    with (
        patch(
            "custom_components.neopool.NeoPoolModbusClient",
            autospec=True,
        ) as mock_client_cls,
        patch(
            "custom_components.neopool.config_flow.async_probe_serial",
            new=AsyncMock(return_value=MOCK_SERIAL),
        ),
    ):
        mock_client = mock_client_cls.return_value
        mock_client.async_read_all = AsyncMock(return_value=dict(MOCK_POOL_DATA))
        mock_client.read_all_timers = AsyncMock(side_effect=_read_all_timers)
        mock_client.connection_stats = {
            "host": MOCK_HOST,
            "port": MOCK_PORT,
            "unit_id": DEFAULT_UNIT_ID,
            "connected": True,
            "total_operations": 10,
            "successful_operations": 10,
            "success_rate_percent": 100.0,
        }
        mock_client.async_set_relay_state = AsyncMock(return_value={})
        mock_client.async_set_manual_filtration = AsyncMock(return_value={})
        mock_client.async_set_binary_flag = AsyncMock(return_value={})
        mock_client.async_set_bitmask_flag = AsyncMock(return_value={})
        mock_client.async_start_backwash = AsyncMock(return_value=None)
        mock_client.async_stop_backwash = AsyncMock(return_value=None)
        mock_client.close = AsyncMock()
        # CUSTOM-ONLY START
        mock_client.async_write_register = AsyncMock(
            return_value={"value": 0, "confirmed": 0}
        )
        mock_client.async_set_filtration_mode = AsyncMock(return_value=None)
        mock_client.async_set_cell_boost = AsyncMock(return_value=None)
        mock_client.async_set_filtration_speed = AsyncMock(return_value=None)
        mock_client.async_set_filtvalve_mode = AsyncMock(return_value={})
        mock_client.async_set_temp_setpoint = AsyncMock(return_value=None)
        mock_client.async_set_setpoint = AsyncMock(return_value={})
        mock_client.async_set_config_option = AsyncMock(return_value={})
        mock_client.async_sync_device_time = AsyncMock(return_value=None)
        mock_client.async_clear_errors = AsyncMock(return_value=None)
        mock_client.async_reset_user_counters = AsyncMock(return_value=None)
        mock_client.write_timer = AsyncMock()
        # CUSTOM-ONLY END
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
        "filtration_mode": "manual",
        "filtration_speed_state": "off",
        "Filtration Pump": False,
    }


@pytest.fixture
def mock_socket_connection() -> Generator[None]:
    """Patch the lib probe in config_flow so we don't hit the network.

    Not autouse, opt in via the fixture name when the integration's
    config-flow setup runs in the test (it would otherwise try to open
    a real TCP connection through ``async_probe_serial``).
    """
    with patch(
        "custom_components.neopool.config_flow.async_probe_serial",
        new=AsyncMock(return_value=MOCK_SERIAL),
    ):
        yield
