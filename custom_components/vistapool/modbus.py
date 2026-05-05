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

"""VistaPool Integration for Home Assistant - Modbus Client"""

import asyncio
import logging
import time
from collections import deque
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import overload

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ConnectionException, ModbusException
from pymodbus.framer import FramerType

from .const import (
    COMMAND_REGISTERS,
    DEFAULT_MODBUS_FRAMER,
    EEPROM_SAVE_REGISTER,
    EXEC_REGISTER,
    TIMER_BLOCKS,
    is_valid_relay_gpio,
)
from .helpers import (
    build_timer_block,
    get_filtration_speed,
    modbus_regs_to_ascii,
    parse_timer_block,
)
from .modbus_compat import modbus_acall
from .status_mask import (
    decode_hidro_status_bits,
    decode_ion_status_bits,
    decode_named_relay_states,
    decode_ph_rx_cl_cd_status_bits,
    decode_relay_state,
    decode_uv_lamp_state,
)

_LOGGER = logging.getLogger(__name__)

AUX_BITMASKS = {
    1: 0x0008,  # AUX1
    2: 0x0010,  # AUX2
    3: 0x0020,  # AUX3
    4: 0x0040,  # AUX4
}

# MBF_NOTIFICATION (0x0110) page-change bitmask constants
_NOTIF_MODBUS = 0x0001  # MBMSK_NOTIF_MODBUS_CHANGED
_NOTIF_GLOBAL = 0x0002  # MBMSK_NOTIF_GLOBAL_CHANGED
_NOTIF_FACTORY = 0x0004  # MBMSK_NOTIF_FACTORY_CHANGED
_NOTIF_INSTALLER = 0x0008  # MBMSK_NOTIF_INSTALLER_CHANGED
_NOTIF_USER = 0x0010  # MBMSK_NOTIF_USER_CHANGED
_NOTIF_MISC = 0x0020  # MBMSK_NOTIF_MISC_CHANGED

# Safety: force a full register read every N polls so that devices which do not
# correctly implement the NOTIFICATION register still get periodic refreshes.
_FULL_READ_INTERVAL = 60


class VistaPoolModbusClient:
    def __init__(self, config):
        self._host = config["host"]
        self._port = config.get("port", 502)
        self._unit = config.get("slave_id", 1)
        _framer_str = config.get("modbus_framer", DEFAULT_MODBUS_FRAMER).strip().lower()
        if _framer_str == "rtu":
            self._framer = FramerType.RTU
        elif _framer_str == "tcp":
            self._framer = FramerType.SOCKET
        else:
            _LOGGER.warning(
                "Unknown modbus_framer value '%s', falling back to 'tcp' socket (Modbus TCP / MBAP header)",
                _framer_str,
            )
            self._framer = FramerType.SOCKET
        self._client = None  # ← Persistent client instance
        self._client_lock = asyncio.Lock()

        # Connection retry parameters
        self._connection_attempts = 0
        self._max_connection_retries = 3
        self._base_delay = 1.0
        self._max_delay = 30.0
        self._backoff_until = None

        # Health tracking
        self._consecutive_errors = 0
        self._last_successful_operation = None
        self._total_operations = 0
        self._successful_operations = 0

        # Diagnostic tracking
        self._response_times = deque(maxlen=50)  # last 50 response times
        self._failed_reads = {}  # address -> count
        self._successful_addresses = deque(maxlen=20)  # last 20 successful addresses
        self._write_response_times = deque(maxlen=50)
        self._failed_writes = {}  # address -> count
        self._successful_writes = deque(maxlen=20)  # (address, timestamp)
        self._total_writes = 0
        self._successful_write_ops = 0

        # Notification-based polling optimization
        self._cached_result: dict = {}  # Last known values for all registers
        self._polls_since_full_read: int = (
            _FULL_READ_INTERVAL  # Force full read on first poll
        )
        self._last_notification: int = (
            0  # Notification bits from last _perform_read_all
        )
        self._last_was_full_read: bool = (
            True  # Whether last _perform_read_all was a full read
        )
        self._cached_timers: dict = {}  # Last known timer values

    async def get_client(self) -> AsyncModbusTcpClient:
        """Get or create a Modbus client with retry logic."""
        async with self._client_lock:
            # Check if we're in backoff period
            if self._backoff_until and datetime.now() < self._backoff_until:
                remaining = (self._backoff_until - datetime.now()).total_seconds()
                raise ConnectionException(
                    f"Connection in backoff for {remaining:.1f} seconds"
                )

            # Check existing connection health
            if self._client and self._client.connected:  # pragma: no cover
                if await self._is_connection_healthy():
                    return self._client
                else:
                    _LOGGER.debug("Connection appears unhealthy, will reconnect")
                    await self._safe_close_client()
                    self._client = None

            # Need new connection
            return await self._establish_connection_with_retry()

    async def _establish_connection_with_retry(self) -> AsyncModbusTcpClient:
        """Establish new connection with exponential backoff retry."""
        last_error = None

        for attempt in range(self._max_connection_retries):
            try:
                # Clean up any existing client
                await self._safe_close_client()

                # Create new client with optimal settings
                self._client = AsyncModbusTcpClient(
                    self._host,
                    port=self._port,
                    timeout=5,
                    framer=self._framer,
                )

                # Attempt connection with timeout
                _LOGGER.debug(
                    "Attempting Modbus connection to %s:%s (attempt %d/%d)",
                    self._host,
                    self._port,
                    attempt + 1,
                    self._max_connection_retries,
                )

                connected = await asyncio.wait_for(self._client.connect(), timeout=10)

                if not connected:
                    raise ConnectionException("Connection returned False")

                # Connection successful!
                self._connection_attempts = 0
                self._consecutive_errors = 0
                self._last_successful_operation = datetime.now()
                self._backoff_until = None

                self._install_fc20_filter(self._client)

                _LOGGER.info(
                    "Modbus connection established successfully to %s:%s",
                    self._host,
                    self._port,
                )
                return self._client

            except Exception as e:
                last_error = e
                self._connection_attempts += 1

                # Calculate exponential backoff delay
                delay = min(self._base_delay * (2**attempt), self._max_delay)

                _LOGGER.warning(
                    "Connection attempt %d/%d failed: %s",
                    attempt + 1,
                    self._max_connection_retries,
                    e,
                )

                # If not the last attempt, wait before retrying
                if attempt < self._max_connection_retries - 1:
                    _LOGGER.debug("Waiting %.1f seconds before retry...", delay)
                    await asyncio.sleep(delay)
                    continue

        # All connection attempts failed - set backoff period
        self._backoff_until = datetime.now() + timedelta(minutes=2)

        _LOGGER.error(
            "All %d connection attempts failed. Setting 2-minute backoff period.",
            self._max_connection_retries,
        )
        raise ConnectionException(
            f"Failed to establish connection after {self._max_connection_retries} attempts: {last_error}"
        )

    def _install_fc20_filter(self, client: AsyncModbusTcpClient) -> None:
        """Install a filter on the pymodbus transport to discard Sugar Valley FC20
        broadcast frames before pymodbus processes them.

        Sugar Valley devices spontaneously broadcast proprietary FC20 (0x20) frames
        on the RS485 bus approximately every 2 seconds. Gateways like the Elfin EW11
        forward these raw bytes over TCP without an MBAP header. pymodbus can mistake
        them for responses to pending FC03/FC04 requests, causing read failures.

        The filter works for both framing modes:

        - **RTU framing**: The frame layout is (slave_id, function_code, ...). An FC20
          broadcast is identified by data[0] == unit_id and data[1] == 0x20.

        - **SOCKET (Modbus TCP) framing**: The first two bytes are the MBAP Transaction
          ID, and bytes 2–3 are the Protocol Identifier, which is always 0x0000 for any
          valid Modbus TCP frame. FC20 broadcasts are raw RTU bytes forwarded without an
          MBAP header, so their bytes 2–3 are NOT 0x0000 (they are 0x0201). This lets us
          safely distinguish them from a legitimate response whose TID happens to equal
          (unit_id << 8 | 0x20).

        This method monkey-patches ``client.ctx.data_received`` at the instance level.
        The patch is intentionally non-fatal: any exception during installation is caught
        and logged at DEBUG level so future pymodbus changes cannot break the connect flow.
        """
        try:
            ctx = getattr(client, "ctx", None)
            if ctx is None:
                _LOGGER.debug("FC20 filter: client.ctx not found, skipping")
                return

            original_data_received = ctx.data_received
            unit_id = self._unit
            is_rtu = self._framer == FramerType.RTU

            # Small prefix buffer used only in SOCKET framing.  When a TCP read
            # delivers only 2–3 bytes that start with [unit_id, 0x20] we cannot
            # yet inspect the MBAP Protocol Identifier at bytes 2-3.  We stash
            # those bytes here and prepend them to the very next chunk so the
            # decision (drop FC20 vs forward valid MBAP) is always made with at
            # least 4 bytes of context.
            _socket_buf: bytes = b""

            def filtered_data_received(data: bytes) -> None:
                nonlocal _socket_buf
                # FC20 broadcasts from Sugar Valley: slave_id byte followed by 0x20.
                # For RTU framing: data[0]=slave_id, data[1]=function_code.
                # For SOCKET framing: data[0:2]=TID, data[2:4]=Protocol ID (0x0000
                # for valid Modbus TCP). Raw FC20 broadcasts have no MBAP header, so
                # bytes 2-3 are NOT 0x0000 — this is the distinguishing signal.
                if not is_rtu:
                    # Reassemble any previously buffered prefix.
                    if _socket_buf:
                        data = _socket_buf + data
                        _socket_buf = b""
                    # If we have [unit_id, 0x20] but not yet the Protocol ID bytes,
                    # buffer and wait for the next chunk rather than forwarding what
                    # could be the start of a raw FC20 broadcast.
                    if (
                        len(data) >= 2
                        and data[0] == unit_id
                        and data[1] == 0x20
                        and len(data) < 4
                    ):
                        _socket_buf = data
                        return
                if is_rtu:
                    is_fc20 = len(data) >= 2 and data[0] == unit_id and data[1] == 0x20
                else:
                    is_fc20 = (
                        len(data) >= 4
                        and data[0] == unit_id
                        and data[1] == 0x20
                        and data[2:4] != b"\x00\x00"
                    )
                if is_fc20:
                    if _LOGGER.isEnabledFor(logging.DEBUG):
                        _LOGGER.debug(
                            "FC20 broadcast frame filtered (%d bytes): %s",
                            len(data),
                            data.hex(),
                        )
                    # Drop the entire chunk.  FC20 is a proprietary Sugar Valley
                    # broadcast whose internal length field cannot be reliably parsed
                    # (the observed 27-byte frame has data[6]=0x39=57, giving a
                    # bogus fc20_len=66).  Attempting to forward trailing bytes based
                    # on a miscomputed offset would corrupt pymodbus state.  Dropping
                    # the full chunk is safe: pymodbus will time-out and retry, and
                    # the next poll cycle will succeed without interference.
                    return
                original_data_received(data)

            ctx.data_received = filtered_data_received
            _LOGGER.debug(
                "FC20 broadcast filter installed for unit_id=%d (framer=%s)",
                unit_id,
                self._framer,
            )

        except Exception as exc:
            _LOGGER.debug("Could not install FC20 filter: %s", exc)

    async def _is_connection_healthy(self) -> bool:
        """Quick health check for existing connection."""
        if not self._client or not self._client.connected:
            return False  # pragma: no cover

        # If we had a recent successful operation, assume connection is healthy
        if (
            self._last_successful_operation
            and datetime.now() - self._last_successful_operation < timedelta(minutes=2)
        ):
            return True

        # Perform a lightweight health check
        try:
            result = await asyncio.wait_for(
                modbus_acall(
                    self._client.read_holding_registers,
                    self._unit,
                    address=0x0000,
                    count=1,
                ),
                timeout=3,
            )

            is_healthy = not result.isError()
            if is_healthy:
                self._last_successful_operation = datetime.now()

            return is_healthy

        except Exception as e:  # pragma: no cover
            _LOGGER.debug("Connection health check failed: %s", e)
            return False

    async def _safe_close_client(self):
        """Safely close the Modbus client connection."""
        if self._client is not None:
            try:
                close_method = getattr(self._client, "close", None)
                if callable(close_method):
                    result = close_method()
                    if result is not None and asyncio.iscoroutine(result):
                        await asyncio.wait_for(result, timeout=5)
                _LOGGER.debug("Modbus client closed successfully")
            except Exception as e:  # pragma: no cover
                _LOGGER.debug("Error closing Modbus client: %s", e)
            finally:
                self._client = None

    async def close(self) -> None:
        """Close the client and clean up resources."""
        async with self._client_lock:
            await self._safe_close_client()
            # Reset all counters
            self._connection_attempts = 0
            self._consecutive_errors = 0
            self._backoff_until = None
            # Reset notification polling state so the next connect starts with a full read
            self._cached_result = {}
            self._polls_since_full_read = _FULL_READ_INTERVAL
            self._last_notification = 0
            self._last_was_full_read = True
            self._cached_timers = {}

    async def async_read_all(self) -> dict:
        """Read all data with retry logic."""
        self._total_operations += 1
        max_retries = 2
        last_error: Exception | None = None

        for attempt in range(max_retries):
            try:
                result = await self._perform_read_all()
                # Success
                self._successful_operations += 1
                self._last_successful_operation = datetime.now()
                self._consecutive_errors = 0
                return result

            except Exception as e:
                last_error = e
                self._consecutive_errors += 1

                _LOGGER.warning(
                    "Read attempt %d/%d failed: %s", attempt + 1, max_retries, e
                )

                # Force reconnection on error
                async with self._client_lock:
                    await self._safe_close_client()
                    self._client = None

                # Wait before retry (except on last attempt)
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue

        # All retries failed
        _LOGGER.error("All read attempts failed: %s", last_error)
        assert last_error is not None
        raise last_error

    async def _read_register_ranges(
        self,
        client,
        ranges: list[tuple[int, int]],
        read_func=None,
        label: str = "",
    ) -> list[int]:
        """Read one or more register ranges and return a flat list of values.

        WARNING: Device limit for reading registers is 31 at one request!

        Args:
            client: Connected Modbus client.
            ranges: List of (start_address, count) tuples.
            read_func: The pymodbus read function to use.
                       Defaults to client.read_holding_registers.
            label: Optional label for debug/warning log messages (e.g. "rr01").
        """
        if read_func is None:
            read_func = client.read_holding_registers

        registers: list[int] = []
        for address, count in ranges:
            await asyncio.sleep(0.05)
            try:
                rr = await modbus_acall(
                    read_func, self._unit, address=address, count=count
                )
            except Exception as e:
                self._failed_reads[f"0x{address:04X}"] = (
                    self._failed_reads.get(f"0x{address:04X}", 0) + 1
                )
                raise ModbusException(f"Read error at 0x{address:04X}: {e}") from e
            if rr.isError():
                self._failed_reads[f"0x{address:04X}"] = (
                    self._failed_reads.get(f"0x{address:04X}", 0) + 1
                )
                raise ModbusException(f"Modbus read error from 0x{address:04X}: {rr}")
            self._successful_addresses.append((f"0x{address:04X}", time.time()))
            registers.extend(rr.registers)
            _log_prefix = f"Raw {label} from" if label else "Raw registers from"
            _LOGGER.debug("%s 0x%04X: %s", _log_prefix, address, rr.registers)
            if len(rr.registers) < count:  # pragma: no cover
                _LOGGER.warning(
                    "%s 0x%04X: expected at least %d registers, got %d",
                    _log_prefix,
                    address,
                    count,
                    len(rr.registers),
                )
        return registers

    async def _perform_read_all(self) -> dict:
        result = {}

        @overload
        def get_safe(regs: list[int], idx: int) -> int | None: ...
        @overload
        def get_safe(
            regs: list[int], idx: int, transform: Callable[[int], int | float]
        ) -> int | float | None: ...
        def get_safe(
            regs: list[int],
            idx: int,
            transform: Callable[[int], int | float] | None = None,
        ) -> int | float | None:
            """Safely get a register value or return None if missing. Optionally apply a transform."""
            try:
                val = regs[idx]
            except IndexError:  # pragma: no cover
                _LOGGER.warning("Register at index %d is missing in %s", idx, regs)
                return None
            if val is None:
                return None  # pragma: no cover
            return transform(val) if transform is not None else val

        force_full = True
        notification = 0

        start = time.monotonic()
        try:
            client = await self.get_client()
            if client is None or not client.connected:  # pragma: no cover
                self._failed_reads["connection"] = (
                    self._failed_reads.get("connection", 0) + 1
                )
                raise ModbusException(
                    f"Modbus client connection failed to {self._host}:{self._port}"
                )

            """
            Request MEASURE page of registers starting from 0x0100
            Contains the different measurement information including hydrolysis current, pH level, redox level, etc.
            For measurements registers, we have to use function 0x04 (Read Input Registers).
            Always read first – provides live measurements and the MBF_NOTIFICATION register
            (0x0110) which determines which configuration pages need to be refreshed.
            """

            reg01 = await self._read_register_ranges(
                client,
                [(0x0100, 18)],  # 0x0100–0x0111
                read_func=client.read_input_registers,
                label="rr01",
            )

            # Example: [0, 0, 820, 709, 0, 0, 140, 50560, 49536, 1280, 1280, 0, 8192, 16928, 0, 0, 9, 0]
            # fmt: off
            result.update({
                "MBF_ION_CURRENT": get_safe(reg01, 0),                              # 0x0100        Ionization level measured
                "MBF_HIDRO_CURRENT": get_safe(reg01, 1, lambda v: v / 10.0),        # 0x0101        Hydrolysis intensity level
                "MBF_MEASURE_PH": get_safe(reg01, 2, lambda v: v / 100.0),          # 0x0102 ph     pH level measured in 1/100 (700 = 7.00)
                "MBF_MEASURE_RX": get_safe(reg01, 3),                               # 0x0103 mV     Redox level measured in mV
                "MBF_MEASURE_CL": get_safe(reg01, 4, lambda v: v / 100.0),          # 0x0104 ppm    Chlorine level measured in 1/100 ppm (100 = 1.00 ppm)
                "MBF_MEASURE_CONDUCTIVITY": get_safe(reg01, 5),                     # 0x0105 %      Conductivity level measured in %
                "MBF_MEASURE_TEMPERATURE": get_safe(reg01, 6, lambda v: v / 10.0),  # 0x0106 °C     Temperature sensor measured in 1/10° C (100 = 10.0°C)
                "MBF_PH_STATUS": get_safe(reg01, 7),                                # 0x0107 mask   Status of the pH-module
                "MBF_RX_STATUS": get_safe(reg01, 8),                                # 0x0108 mask   Status of the Rx-module
                "MBF_CL_STATUS": get_safe(reg01, 9),                                # 0x0109 mask   Status of the Chlorine-module
                "MBF_CD_STATUS": get_safe(reg01, 10),                               # 0x010A mask   Status of the Conductivity-module
                "MBF_ION_STATUS": get_safe(reg01, 12),                              # 0x010C mask   Status of the Ionization-module
                "MBF_HIDRO_STATUS": get_safe(reg01, 13),                            # 0x010D mask   Status of the Hydrolysis-module
                "MBF_RELAY_STATE": get_safe(reg01, 14),                             # 0x010E mask   Status of each configurable relay
                "MBF_HIDRO_SWITCH_VALUE": get_safe(reg01, 15),                      # 0x010F        INTERNAL - contains the opening of the hydrolysis PWM.
                "MBF_NOTIFICATION": get_safe(reg01, 16),                            # 0x0110 mask   Bit field that informs whether a property page has changed since the last time it was queried. (see MBMSK_NOTIF_*). This register makes it possible to refresh the content of the registers maintained by a modbus master in an optimized way, without the need to reread all registers periodically, but only those on a page that has been changed.
                "MBF_HIDRO_VOLTAGE": get_safe(reg01, 17, lambda v: v / 10.0),       # 0x0111        The voltage applied to the hydrolysis cell (in 1/10 V). This register, together with that of MBF_HIDRO_CURRENT allows extrapolation of water salinity.
            })
            # fmt: on

            # Extract pH status enum from lower bits of MBF_PH_STATUS
            _ph_status = get_safe(reg01, 7)
            result["MBF_PH_STATUS_ALARM"] = (
                (_ph_status & 0x000F) if _ph_status is not None else None
            )

            # After loading reg01, update result with all decodings:
            # fmt: off
            result.update(
                {
                    **decode_ph_rx_cl_cd_status_bits(_ph_status, "pH"),
                    **decode_ph_rx_cl_cd_status_bits(get_safe(reg01, 8), "Redox"),
                    **decode_ph_rx_cl_cd_status_bits(get_safe(reg01, 9), "Chlorine"),
                    **decode_ph_rx_cl_cd_status_bits(get_safe(reg01, 10), "Conductivity"),
                    **decode_ion_status_bits(get_safe(reg01, 12)),
                    **decode_hidro_status_bits(get_safe(reg01, 13)),
                    **decode_relay_state(get_safe(reg01, 14)),
                }
            )
            # fmt: on

            # ── Notification-based polling optimization ───────────────────────────────────
            # MBF_NOTIFICATION (0x0110) bits indicate which config pages changed since the
            # last read. Between forced refreshes, only flagged pages are re-read from the
            # device; the rest use cached values from the previous successful poll.
            # After consuming the notifications the NOTIFICATION register is cleared to 0.
            notification = result.get("MBF_NOTIFICATION", 0) or 0
            force_full = self._polls_since_full_read >= _FULL_READ_INTERVAL

            # Overlay fresh MEASURE data on top of the cached config data.
            merged = dict(self._cached_result)
            merged.update(result)  # Fresh MEASURE data takes priority over cache.
            result = merged

            if force_full:
                _LOGGER.debug(
                    "Full register read (poll %d / %d)",
                    self._polls_since_full_read,
                    _FULL_READ_INTERVAL,
                )
            elif notification:
                _LOGGER.debug("Partial read – MBF_NOTIFICATION: 0x%04X", notification)
            else:
                _LOGGER.debug(
                    "No page changes reported by device, config registers served from cache"
                )
            # ─────────────────────────────────────────────────────────────────────────────

            """
            Request MODBUS page of registers starting from 0x0000
            Manages general configuration of the box. This page is reserved for internal purposes
            """
            if force_full or (notification & _NOTIF_MODBUS):
                reg00 = await self._read_register_ranges(
                    client,
                    [
                        (0x0000, 16),  # 0x0000–0x000F
                        # (0x0022, 2),  # 0x0022–0x0024 (24-36V, 12V, 5V lines)
                        # (0x006A, 1),  # 0x006A (5V line)
                        # (0x0072, 1),  # 0x0072 (4-20mA line)
                    ],
                    label="rr00",
                )

                # Example: [1, 3, 1280, 32768, 88, 47, 16707, 20497, 8248, 12592, 0, 0, 0, 22069, 0]
                # fmt: off
                result.update({
                    "MBF_POWER_MODULE_VERSION": get_safe(reg00, 2),     # 0x0002         ! Power module version (MSB=Major, LSB=Minor)
                    "MBF_POWER_MODULE_NODEID": reg00[4:10],             # 0x0004         ! Power module Node ID (6 register 0x0004 - 0x0009)
                    "MBF_POWER_MODULE_REGISTER": get_safe(reg00, 12),   # 0x000C         ! Writing an address in this register causes the power module register address to be read out into MBF_POWER_MODULE_DATA, see MBF_POWER_MODULE_REG_*
                    "MBF_POWER_MODULE_DATA": get_safe(reg00, 13),       # 0x000D         ! power module data as requested in MBF_POWER_MODULE_REGISTER
                    # Prepared for future use:
                    # "MBF_VOLT_24_36": get_safe(reg00, 16),            # 0x0022*        ! Current 24-36V line in mV
                    # "MBF_VOLT_12": get_safe(reg00, 17),               # 0x0023*        ! Current 12V line in mV
                    # "MBF_VOLT_5": get_safe(reg00, 18),                # 0x006A*        ! 5V line in mV / 0,62069
                    # "MBF_AMP_4_20_MICRO": get_safe(reg00, 19),        # 0x0072*        ! 2-40mA line in µA * 10 (1=0,01mA)
                })
                # fmt: on
            else:
                _LOGGER.debug(
                    "Skipping MODBUS (0x00xx)  page read (no change notification)"
                )

            """
            Request GLOBAL page of registers starting from 0x0206
            Contains global information, such as the amount of time that each power unit has been working.
            For configuration registers, we have to use function 0x03 (Read Holding Registers)
            """
            if force_full or (notification & _NOTIF_GLOBAL):
                # fmt: off
                reg02 = await self._read_register_ranges(
                    client,
                    [
                        (0x0206, 20),  # 0x0206–0x0219
                        (0x0280, 2),   # 0x0280–0x0281 (hidrolysis module version and connectivity)
                    ],
                    label="rr02",
                )
                # fmt: on

                # Example: [23971, 8, 23971, 8, 26922, 0, 34208, 0, 0, 65426, 0, 0, 0, 0, 64136, 3, 25371, 4, 16, 0]
                # fmt: off
                result.update({
                    "MBF_CELL_RUNTIME_LOW":      get_safe(reg02, 0),            # 0x0206*        ! Cell runtime (32 bit value - low word)
                    "MBF_CELL_RUNTIME_HIGH":     get_safe(reg02, 1),            # 0x0207*        ! Cell runtime (32 bit value - high word)
                    "MBF_CELL_RUNTIME_PART_LOW": get_safe(reg02, 2),            # 0x0208*        ! Cell part runtime (32 bit value - low word)
                    "MBF_CELL_RUNTIME_PART_HIGH":get_safe(reg02, 3),            # 0x0209*        ! Cell part runtime (32 bit value - high word)
                    # 0x020A–0x020B skipped
                    "MBF_CELL_BOOST":            get_safe(reg02, 6),            # 0x020C* mask   ! Boost control (see MBMSK_CELL_BOOST_*)
                    # 0x020D–0x0213 skipped
                    "MBF_CELL_RUNTIME_POLA_LOW": get_safe(reg02, 14),           # 0x0214*        ! Cell runtime polarity 1 (32 bit value - low word)
                    "MBF_CELL_RUNTIME_POLA_HIGH":get_safe(reg02, 15),           # 0x0215*        ! Cell runtime polarity 1 (32 bit value - high word)
                    "MBF_CELL_RUNTIME_POLB_LOW": get_safe(reg02, 16),           # 0x0216*        ! Cell runtime polarity 2 (32 bit value - low word)
                    "MBF_CELL_RUNTIME_POLB_HIGH":get_safe(reg02, 17),           # 0x0217*        ! Cell runtime polarity 2 (32 bit value - high word)
                    "MBF_CELL_RUNTIME_POL_CHANGES_LOW": get_safe(reg02, 18),    # 0x0218*        ! Cell runtime polarity change count (32 bit value - low word)
                    "MBF_CELL_RUNTIME_POL_CHANGES_HIGH":get_safe(reg02, 19),    # 0x0219*        ! Cell runtime polarity change count (32 bit value - high word)
                    # Hydrolysis module data
                    "MBF_HIDRO_MODULE_VERSION":      get_safe(reg02, 20),       # 0x0280         ! Hydrolysis module version
                    "MBF_HIDRO_MODULE_CONNECTIVITY": get_safe(reg02, 21),       # 0x0281         ! Hydrolysis module connection quality (in myriad: 0..10000)
                })
                # fmt: on
            else:
                _LOGGER.debug(
                    "Skipping GLOBAL (0x02xx) page read (no change notification)"
                )

            if force_full or (notification & _NOTIF_FACTORY):
                """
                Request FACTORY page of registers starting from 0x0300
                Contains factory data such as calibration parameters for the different power units.
                For configuration registers, we have to use function 0x03 (Read Holding Registers)
                """
                reg03 = await self._read_register_ranges(
                    client,
                    [
                        (0x0300, 13),  # 0x0300–0x030C
                        (0x0322, 4),  # 0x0322–0x0325
                    ],
                    label="rr03",
                )

                # [2055, 10, 0, 0, 0, 0, 1000, 50, 0, 14687, 2600, 2, 1297, 125, 2, 100, 100]
                # fmt: off
                result.update({
                    "MBF_PAR_VERSION": get_safe(reg03, 0),                          # 0x0300*        Software version of the PowerBox
                    "MBF_PAR_MODEL": get_safe(reg03, 1),                            # 0x0301* mask   System model options
                    "MBF_PAR_SERNUM": get_safe(reg03, 2),                           # 0x0302*        Serial number of the PowerBox
                    "MBF_PAR_ION_NOM":  get_safe(reg03, 3),                         # 0x0303*        Ionization maximum production level (DO NOT WRITE!)
                    # 0x0304–0x0305 skipped
                    "MBF_PAR_HIDRO_NOM":  get_safe(reg03, 6, lambda v: v / 10.0),   # 0x0306*        Hydrolysis maximum production level. (DO NOT WRITE!) If the hydrolysis is set to work in percent mode, this value will be 100. If the hydrolysis module is set to work in g/h production, this module will contain the maximum amount of production in g/h units. (DO NOT WRITE!)
                    "MBF_PAR_HIDRO_NOM2": get_safe(reg03, 7),                       # 0x0307*        Hydrolysis maximum production level in g/h units (DO NOT WRITE!). This value is probably used only when the hydrolysis module is set to work in g/h production mode.
                    # 0x0308–0x0309 skipped
                    "MBF_PAR_SAL_AMPS":  get_safe(reg03, 10),                       # 0x030A         Current command in regulation for which we are going to measure voltage
                    "MBF_PAR_SAL_CELLK":  get_safe(reg03, 11),                      # 0x030B         Specifies the relationship between the resistance obtained in the measurement process and its equivalence in g / l (grams per liter)
                    "MBF_PAR_SAL_TCOMP":  get_safe(reg03, 12),                      # 0x030C         Specifies the deviation in temperature from the conductivity.
                    # 0x030D–0x0321 skipped
                    "MBF_PAR_HIDRO_MAX_VOLTAGE": get_safe(reg03, 13),               # 0x0322         Allows setting the maximum voltage value that can be reached with the hydrolysis current regulation. The value is specified in tenths of a volt. The default value of this register when the EEPROM is cleared is 80, which is equivalent to a maximum cell operating voltage of 8 volts.
                    "MBF_PAR_HIDRO_FLOW_SIGNAL": get_safe(reg03, 14),               # 0x0323         Allows to select the operation of the flow detection signal associated with the operation of the hydrolysis (see MBV_PAR_HIDRO_FLOW_SIGNAL*). The default value for this register is 0 (standard detection).
                    "MBF_PAR_HIDRO_MAX_PWM_STEP_UP": get_safe(reg03, 15),           # 0x0324         This register sets the PWM ramp up of the hydrolysis in pulses per duty cycle. This register makes it possible to adjust the rate at which the power delivered to the cell increases, allowing a gradual rise in power so that the operation of the switching source of the equipment is not saturated. Default 150
                    "MBF_PAR_HIDRO_MAX_PWM_STEP_DOWN": get_safe(reg03, 16),         # 0x0325         This register sets the PWM down ramp of the hydrolysis in pulses per duty cycle. This register allows adjusting the rate at which the power delivered to the cell decreases, allowing a gradual drop in power so that the switched source of the equipment is not disconnected due to lack of consumption. This gradual fall must be in accordance with the type of cell used, since said cell stores charge once the current stimulus has ceased. Default 20
                })
                # fmt: on
            else:
                _LOGGER.debug(
                    "Skipping FACTORY (0x03xx) page read (no change notification)"
                )

            if force_full or (notification & _NOTIF_INSTALLER):
                """
                Request INSTALLER page of registers starting from 0x0400
                Contains a set of configuration registers related to the equipment installation,
                such as the relays used for each function, the amount of time that each pump must operate, etc.
                For configuration registers, we have to use function 0x03 (Read Holding Registers)
                """

                # Read configuration registers in multiple blocks due to device limits.
                # Blocks covered:
                #   0x0408–0x0426  (31 registers) - general config (relay GPIOs, offsets, etc.)
                #   0x0427–0x0433  (13 registers) - pH/redox/chlorine config
                #   0x0434–0x04E7  - TIMER_BLOCKS, read separately via read_all_timers()
                #   0x04E8–0x04EF  ( 8 registers) - FILTVALVE / backwash valve config
                reg04 = await self._read_register_ranges(
                    client,
                    [
                        (0x0408, 31),  # 0x0408–0x0426
                        (0x0427, 13),  # 0x0427–0x0433
                        (0x04E8, 8),  # 0x04E8–0x04EF  FILTVALVE / backwash registers
                    ],
                    label="rr04",
                )

                # Example: [9861, 26670, 1, 0, 0, 0, 0, 1, 3, 1, 2, 0, 0, 0, 25, 0, 25, 10, 0, 0, 28, 480, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
                # fmt: off
                result.update({
                    "MBF_PAR_TIME_LOW": get_safe(reg04, 0),                                     # 0x0408*        System timestamp as unix timestamp (32 bit value - low word).
                    "MBF_PAR_TIME_HIGH": get_safe(reg04, 1),                                    # 0x0409*        System timestamp as unix timestamp (32 bit value - high word).
                    "MBF_PAR_PH_ACID_RELAY_GPIO": get_safe(reg04, 2),                           # 0x040A*        Relay number assigned to the acid pump function (only with pH module).
                    "MBF_PAR_PH_BASE_RELAY_GPIO": get_safe(reg04, 3),                           # 0x040B*        Relay number assigned to the base pump function (only with pH module).
                    "MBF_PAR_RX_RELAY_GPIO": get_safe(reg04, 4),                                # 0x040C*        Relay number assigned to the Redox level regulation function. If the value is 0, there is no relay assigned, and therefore there is no pump function (ON / OFF should not be displayed)
                    "MBF_PAR_CL_RELAY_GPIO": get_safe(reg04, 5),                                # 0x040D*        Relay number assigned to the chlorine pump function (only with free chlorine measuring modules).
                    "MBF_PAR_CD_RELAY_GPIO": get_safe(reg04, 6),                                # 0x040E*        Relay number assigned to the conductivity (brine) pump function (only with conductivity measurement modules).
                    "MBF_PAR_TEMPERATURE_ACTIVE": get_safe(reg04, 7),                           # 0x040F*        Indicates whether the equipment has a temperature measurement or not.
                    "MBF_PAR_LIGHTING_GPIO": get_safe(reg04, 8),                                # 0x0410*        Relay number assigned to the lighting function. 0: inactive.
                    "MBF_PAR_FILT_MODE": get_safe(reg04, 9),                                    # 0x0411*        Filtration mode (see MBV_PAR_FILT_*)
                    "MBF_PAR_FILT_GPIO": get_safe(reg04, 10),                                   # 0x0412*        Relay selected to perform the filtering function (by default it is relay 2). When this value is at zero, there is no relay assigned and therefore it is understood that the equipment does not control the filtration. In this case, the filter option does not appear in the user menu.
                    "MBF_PAR_FILT_MANUAL_STATE": get_safe(reg04, 11),                           # 0x0413         Filtration status in manual mode (on = 1; off = 0)
                    "MBF_PAR_HEATING_MODE": get_safe(reg04, 12),                                # 0x0414         Heating mode: 0 = the equipment is not heated. 1 = the equipment is heating.
                    "MBF_PAR_HEATING_GPIO": get_safe(reg04, 13),                                # 0x0415         Relay number assigned to perform the heating function (by default it is relay 7). When this value is at zero, there is no relay assigned and therefore it is understood that the equipment does not control the heating. In this case, the filter modes associated with heating will not be displayed.
                    "MBF_PAR_HEATING_TEMP": get_safe(reg04, 14),                                # 0x0416         Heating mode: Heating setpoint temperature
                    "MBF_PAR_CLIMA_ONOFF": get_safe(reg04, 15),                                 # 0x0417         Activation of the climate mode (0 = inactive, 1 = active).
                    "MBF_PAR_SMART_TEMP_HIGH": get_safe(reg04, 16),                             # 0x0418         Smart mode: Upper temperature
                    "MBF_PAR_SMART_TEMP_LOW": get_safe(reg04, 17),                              # 0x0419         Smart mode: Lower temperature
                    "MBF_PAR_SMART_ANTI_FREEZE": get_safe(reg04, 18),                           # 0x041A         Smart mode: Antifreeze mode activated (1) or not (0).
                    "MBF_PAR_SMART_INTERVAL_REDUCTION": get_safe(reg04, 19),                    # 0x041B         Smart mode: This register is read-only and reports to the outside what percentage (0 to 100%) is being applied to the nominal filtration time. 100% means that the total programmed time is being filtered.
                    "MBF_PAR_INTELLIGENT_TEMP": get_safe(reg04, 20),                            # 0x041C         Intelligent mode: Setpoint temperature
                    "MBF_PAR_INTELLIGENT_FILT_MIN_TIME": get_safe(reg04, 21),                   # 0x041D         Intelligent mode: Minimum filtration time in minutes
                    "MBF_PAR_INTELLIGENT_BONUS_TIME": get_safe(reg04, 22),                      # 0x041E         Intelligent mode: Bonus time for the current set of intervals
                    "MBF_PAR_INTELLIGENT_TT_NEXT_INTERVAL": get_safe(reg04, 23),                # 0x041F         Intelligent mode: Time to next filtration interval. When it reaches 0 an interval is started and the number of seconds is reloaded for the next interval (2x3600)
                    "MBF_PAR_INTELLIGENT_INTERVALS": get_safe(reg04, 24),                       # 0x0420         Intelligent mode: Number of started intervals. When it reaches 12 it is reset to 0 and the bonus time is reloaded with the value of MBF_PAR_INTELLIGENT_FILT_MIN_TIME
                    "MBF_PAR_FILTRATION_STATE": get_safe(reg04, 25),                            # 0x0421         Filtration state: 0 is off and 1 is on. The filtration state is regulated according to the MBF_PAR_FILT_MANUAL_STATE register if the filtration mode held in register MBF_PAR_FILT_MODE is set to FILT_MODE_MANUAL (0).
                    "MBF_PAR_HEATING_DELAY_TIME": get_safe(reg04, 26),                          # 0x0422         Timer in seconds that counts up when the heating is to be enabled. Once this counter reaches 60 seconds, the heating is then enabled. This counter is for internal use only.
                    "MBF_PAR_FILTERING_TIME_LOW": get_safe(reg04, 27),                          # 0x0423         Internal timer for the intelligent filtering mode (32-bit value - low word). It counts the filtering time done during a given day. This register is only for internal use and should not be modified by the user.
                    "MBF_PAR_FILTERING_TIME_HIGH": get_safe(reg04, 28),                         # 0x0424         Internal timer for the intelligent filtering mode (32-bit value - high word)
                    "MBF_PAR_INTELLIGENT_INTERVAL_TIME_LOW": get_safe(reg04, 29),               # 0x0425         Internal timer that counts the filtration interval assigned to the the intelligent mode (32-bit value - low word). This register is only for internal use and should not be modified by the user.
                    "MBF_PAR_INTELLIGENT_INTERVAL_TIME_HIGH": get_safe(reg04, 30),              # 0x0426         Internal timer that counts the filtration interval assigned to the the intelligent mode (32-bit value - high word)
                    "MBF_PAR_UV_MODE": get_safe(reg04, 31),                                     # 0x0427         UV mode active or not - see MBV_PAR_UV_MODE*. To enable UV support for a given device, add the mask MBMSK_MODEL_UV to the MBF_PAR_MODEL register.
                    "MBF_PAR_UV_HIDE_WARN": get_safe(reg04, 32),                                # 0x0428  mask   Suppression for warning messages in the UV mode (see MBMSK_UV_HIDE_WARN_*)
                    "MBF_PAR_UV_RELAY_GPIO": get_safe(reg04, 33),                               # 0x0429         Relay number assigned to the UV function.
                    "MBF_PAR_PH_PUMP_REP_TIME_ON": get_safe(reg04, 34),                         # 0x042A  mask   Time that the pH pump will be turn on in the repetitive mode (see MBMSK_PH_PUMP_*). Contains a special time format, see desc for MBMSK_PH_PUMP_TIME.
                    "MBF_PAR_PH_PUMP_REP_TIME_OFF": get_safe(reg04, 35),                        # 0x042B  mask   Time that the pH pump will be turn off in the repetitive mode. Contains a special time format, see desc for MBMSK_PH_PUMP_TIME, has no upper configuration bit 0x8000
                    "MBF_PAR_HIDRO_COVER_ENABLE": get_safe(reg04, 36),                          # 0x042C  mask   Options for the hydrolysis/electrolysis module (see MBMSK_HIDRO_*)
                    "MBF_PAR_HIDRO_COVER_REDUCTION": get_safe(reg04, 37),                       # 0x042D         Configured levels for the cover reduction and the hydrolysis shutdown temperature options: LSB = Percentage for the cover reduction, MSB = Temperature level for the hydrolysis shutdown (see MBMSK_HIDRO_*)
                    "MBF_PAR_PUMP_RELAY_TIME_OFF": get_safe(reg04, 38),                         # 0x042E         Time level in minutes or seconds that the dosing pump must remain off when the temporized pump mode is selected. This time level register applies to all pumps except pH. Contains a special time format, see desc for MBMSK_PH_PUMP_TIME, has no upper configuration bit 0x8000
                    "MBF_PAR_PUMP_RELAY_TIME_ON": get_safe(reg04, 39),                          # 0x042F         Time level in minutes or seconds that the dosing pump must remain on when the temporized pump mode is selected. This time level register applies to all pumps except pH. Contains a special time format, see desc for MBMSK_PH_PUMP_TIME, has no upper configuration bit 0x8000
                    "MBF_PAR_RELAY_PH": get_safe(reg04, 40),                                    # 0x0430         Determine what pH regulation configuration the equipment has (see MBV_PAR_RELAY_PH_*)
                    "MBF_PAR_RELAY_MAX_TIME": get_safe(reg04, 41),                              # 0x0431         Maximum amount of time in seconds, that a dosing pump can operate before rising an alarm signal. The behavior of the system when the dosing time is exceeded is regulated by the type of action stored in the MBF_PAR_RELAY_MODE register.
                    "MBF_PAR_RELAY_MODE": get_safe(reg04, 42),                                  # 0x0432         Behavior of the system when the dosing time is exceeded (see MBMSK_PAR_RELAY_MODE_* and MBV_PAR_RELAY_MODE_*)
                    "MBF_PAR_RELAY_ACTIVATION_DELAY": get_safe(reg04, 43, lambda v: v + 10),    # 0x0433         Delay time in seconds for the pH pump when the measured pH value is outside the allowable pH setpoints. The system internally adds an extra time of 10 seconds to the value stored here. The pump starts the dosing operation once the condition of pH out of valid interval is maintained during the time specified in this register.
                    # FILTVALVE / backwash registers (0x04E8–0x04EF) at reg04 indices 44–51
                    "MBF_PAR_FILTVALVE_ENABLE": get_safe(reg04, 44),                            # 0x04E8        Filter cleaning mode (0 = off, 1 = Besgo valve)
                    "MBF_PAR_FILTVALVE_MODE": get_safe(reg04, 45),                              # 0x04E9        Filter cleaning valve timing mode (MBV_PAR_CTIMER_ENABLED/ALWAYS_ON/ALWAYS_OFF)
                    "MBF_PAR_FILTVALVE_GPIO": get_safe(reg04, 46),                              # 0x04EA        Relay assigned to the filter cleaning function
                    "MBF_PAR_FILTVALVE_PERIOD_MINUTES": get_safe(reg04, 49),                    # 0x04ED        Period in minutes between cleaning actions
                    "MBF_PAR_FILTVALVE_INTERVAL": get_safe(reg04, 50),                          # 0x04EE        Cleaning action duration in seconds
                    "MBF_PAR_FILTVALVE_REMAINING": get_safe(reg04, 51),                         # 0x04EF        Remaining backwash time in seconds (> 0 = backwash active)

                })
                # fmt: on
            else:
                _LOGGER.debug(
                    "Skipping INSTALLER (0x04xx) page read (no change notification)"
                )

            # Decode UV Lamp relay state after INSTALLER data is available in result
            # (MBF_PAR_UV_RELAY_GPIO comes from INSTALLER page or cache merge)
            _uv_gpio = result.get("MBF_PAR_UV_RELAY_GPIO", 0) or 0
            result.update(decode_uv_lamp_state(result.get("MBF_RELAY_STATE"), _uv_gpio))

            # Decode named relay states using dynamic GPIO mapping.
            # Each functional relay (Filtration, Light, pH Acid Pump, Heating) is
            # assigned to a physical relay output via MBF_PAR_*_RELAY_GPIO registers.
            result.update(
                decode_named_relay_states(
                    result.get("MBF_RELAY_STATE"),
                    {
                        "pH Acid Pump": result.get("MBF_PAR_PH_ACID_RELAY_GPIO", 0)
                        or 0,
                        "Filtration Pump": result.get("MBF_PAR_FILT_GPIO", 0) or 0,
                        "Pool Light": result.get("MBF_PAR_LIGHTING_GPIO", 0) or 0,
                        "Heating": result.get("MBF_PAR_HEATING_GPIO", 0) or 0,
                    },
                )
            )

            if force_full or (notification & _NOTIF_USER):
                # MBF_PAR_RELAY_PH:
                #   0: The equipment works with an acid and base pump
                #   1: The equipment works with acid pump only
                #   2: The equipment works with base pump only

                """
                Request USER page of registers starting from 0x0500
                Contains user configuration registers, such as the production level
                for the ionization and the hydrolysis, or the set points for the pH, redox, or chlorine regulation loops.
                For configuration registers, we have to use function 0x03 (Read Holding Registers)
                """
                reg05 = await self._read_register_ranges(
                    client,
                    [(0x0502, 14)],  # 0x0502–0x050F
                    label="rr05",
                )

                # Example: [650, 0, 750, 700, 0, 0, 700, 0, 100, 0, 0, 0, 5000, 0]
                # fmt: off
                result.update({
                    "MBF_PAR_HIDRO": get_safe(reg05, 0, lambda v: v / 10.0),    # 0x0502        Hydrolisis target production level
                    "MBF_PAR_PH1": get_safe(reg05, 2, lambda v: v / 100.0),     # 0x0504        Higher limit of the pH regulation system
                    "MBF_PAR_PH2": get_safe(reg05, 3, lambda v: v / 100.0),     # 0x0505        Lower limit of the pH regulation system
                    # 0x0506–0x0507 skipped
                    "MBF_PAR_RX1": get_safe(reg05, 6),                          # 0x0508        Set point for the redox regulation system
                    # 0x0509 skipped
                    "MBF_PAR_CL1": get_safe(reg05, 8, lambda v: v / 100.0),     # 0x050A        Set point for the chlorine regulation system
                    # 0x050B-0x050E skipped
                    "MBF_PAR_FILTRATION_CONF": get_safe(reg05, 13),             # 0x050F* mask   ! filtration type and speed
                })
                # fmt: on
            else:
                _LOGGER.debug(
                    "Skipping USER (0x05xx) page read (no change notification)"
                )

            if force_full or (notification & _NOTIF_MISC):
                """
                Request MISC page of registers starting from 0x0600
                Contains the configuration parameters for the screen controllers (language, colours, sound, etc).
                For configuration registers, we have to use function 0x03 (Read Holding Registers)
                """
                reg06 = await self._read_register_ranges(
                    client,
                    [
                        # Includes full NAME_BOLD 0x0608-0x060B and NAME_LIGHT 0x060C-0x060F
                        (0x0600, 16),  # 0x0600–0x060F
                    ],
                    label="rr06",
                )

                # Example: [9, 6, 25604, 5, 0, 2240, 545, 1281, 0, 0, 0, 0, 0, 0, 0, 0]
                # fmt: off
                result.update({
                    "MBF_PAR_UICFG_MACHINE": get_safe(reg06, 0),                # 0x0600        Machine type (see MBV_PAR_MACH_* and  kNeoPoolMachineNames[])
                    "MBF_PAR_UICFG_LANGUAGE": get_safe(reg06, 1),               # 0x0601        Selected language (see MBV_PAR_LANG_*)
                    "MBF_PAR_UICFG_BACKLIGHT": get_safe(reg06, 2),              # 0x0602        Display backlight function (see MBV_PAR_BACKLIGHT_*)
                    "MBF_PAR_UICFG_SOUND": get_safe(reg06, 3),                  # 0x0603 mask   Audible alerts (see MBMSK_PAR_SOUND_*)
                    "MBF_PAR_UICFG_PASSWORD": get_safe(reg06, 4),               # 0x0604        System password encoded in BCD
                    "MBF_PAR_UICFG_VISUAL_OPTIONS": get_safe(reg06, 5),         # 0x0605 mask   Stores the different display options for the user interface menus (bitmask). Some bits allow you to hide options that are normally visible (bits 0 to 3) while other bits allow you to show options that are normally hidden (bits 9 to 15)
                    "MBF_PAR_UICFG_VISUAL_OPTIONS_EXT": get_safe(reg06, 6),     # 0x0606 mask   This register stores additional display options for the user interface menus (see MBMSK_VOE_*)
                    "MBF_PAR_UICFG_MACH_VISUAL_STYLE": get_safe(reg06, 7),      # 0x0607 mask   This register is an expansion of register MBF_PAR_UICFG_MACHINE and MBF_PAR_UICFG_VISUAL_OPTIONS. If MBF_PAR_UICFG_MACHINE is MBV_PAR_MACH_GENERIC then the lower part (8 bits LSB) is used to store the type of color selected. Colors and styles correspond to those listed in MBF_PAR_UICFG_MACHINE (see MBV_PAR_MACH_*). The upper part (8-bit MSB) contains extra bits MBMSK_VS_FORCE_UNITS_GRH, MBMSK_VS_FORCE_UNITS_PERCENTAGE and MBMSK_ELECTROLISIS
                    "MBF_PAR_UICFG_MACH_NAME_BOLD": modbus_regs_to_ascii(reg06[8:12]),   # 0x0608         Machine name bold part title displayed during startup if MBF_PAR_UICFG_MACHINE is MBV_PAR_MACH_GENERIC. Note: Only lowercase letters (a-z) can be used. 4 register (0x608 to 0x60B) ASCIIZ string with up to 8 characters
                    "MBF_PAR_UICFG_MACH_NAME_LIGHT": modbus_regs_to_ascii(reg06[12:16]), # 0x060C         Machine name normal intensity part title displayed during startup if MBF_PAR_UICFG_MACHINE is MBV_PAR_MACH_GENERIC. Note: Only lowercase letters (a-z) can be used. 4 register (0x060C to 0x060F) ASCIIZ string with up to 8 characters
                    # Prepared for future use:
                    # "MBF_PAR_UICFG_MACH_NAME_AUX1": modbus_regs_to_ascii(reg06[16:21]), # 0x0610         Aux1 relay name: 5 register ASCIIZ string with up to 10 characters
                    # "MBF_PAR_UICFG_MACH_NAME_AUX2": modbus_regs_to_ascii(reg06[21:26]), # 0x0615         Aux2 relay name: 5 register ASCIIZ string with up to 10 characters
                    # "MBF_PAR_UICFG_MACH_NAME_AUX3": modbus_regs_to_ascii(reg06[26:31]), # 0x061A         Aux3 relay name: 5 register ASCIIZ string with up to 10 characters
                    # "MBF_PAR_UICFG_MACH_NAME_AUX4": modbus_regs_to_ascii(reg06[31:36]), # 0x061F         Aux4 relay name: 5 register ASCIIZ string with up to 10 characters
                })
                # fmt: on
            else:
                _LOGGER.debug(
                    "Skipping MISC (0x06xx) page read (no change notification)"
                )

            if notification:
                try:
                    await modbus_acall(
                        client.write_registers, self._unit, address=0x0110, values=[0]
                    )
                    _LOGGER.debug(
                        "MBF_NOTIFICATION register cleared (was 0x%04X)", notification
                    )
                except Exception:
                    _LOGGER.debug(
                        "Could not clear MBF_NOTIFICATION (0x%04X)", notification
                    )

        except Exception as e:  # pragma: no cover
            self._failed_reads["unknown"] = self._failed_reads.get("unknown", 0) + 1
            raise ModbusException(f"Modbus TCP read error: {e}") from e
        finally:
            end = time.monotonic()
            self._response_times.append(end - start)
        if force_full:
            self._polls_since_full_read = 0
        else:
            self._polls_since_full_read += 1
        self._last_notification = notification
        self._last_was_full_read = force_full

        # Fixup: on some installations the filtration relay bit in
        # MBF_RELAY_STATE is not set even when the filtration pump is running.
        # MBF_PAR_FILTRATION_STATE (0x0421) is the authoritative source per vendor docs.
        # However, MBF_PAR_FILTRATION_STATE lives on the INSTALLER page which is
        # only re-read on notification or periodic full reads. When it comes from
        # cache it may be stale, so we must NOT let a stale cached value override
        # the fresh relay bit from MBF_RELAY_STATE (read every poll cycle).
        # Only apply the fixup when the INSTALLER page was actually read this cycle.
        installer_fresh = force_full or bool(notification & _NOTIF_INSTALLER)
        filt_gpio = result.get("MBF_PAR_FILT_GPIO", 0) or 0
        filtration_state = result.get("MBF_PAR_FILTRATION_STATE")
        if (
            installer_fresh
            and is_valid_relay_gpio(filt_gpio)
            and filtration_state in (0, 1)
        ):
            authoritative = filtration_state == 1
            if result.get("Filtration Pump") != authoritative:
                _LOGGER.debug(
                    "MBF_RELAY_STATE filtration relay (GPIO %d) disagrees with "
                    "MBF_PAR_FILTRATION_STATE (%d); patching Filtration Pump to %s",
                    filt_gpio,
                    filtration_state,
                    authoritative,
                )
                result["Filtration Pump"] = authoritative
                relay_state = result.get("MBF_RELAY_STATE", 0) or 0
                bit = 1 << (filt_gpio - 1)
                if authoritative:
                    result["MBF_RELAY_STATE"] = relay_state | bit
                else:
                    result["MBF_RELAY_STATE"] = relay_state & ~bit

        # Derive hydrolysis module presence:
        # MBF_PAR_MODEL bit 1 (MBMSK_MODEL_HIDRO) OR MBF_HIDRO_STATUS bit 6 (CTRL_ACTIVE)
        result["Hydrolysis module detected"] = bool(
            (result.get("MBF_PAR_MODEL") or 0) & 0x0002
        ) or bool((result.get("MBF_HIDRO_STATUS") or 0) & 0x0040)

        # Add filtration speed and type
        result["FILTRATION_SPEED"] = get_filtration_speed(result)

        # Update cache after fixup and derived fields so partial reads
        # start from consistent values including derived flags.
        self._cached_result.update(result)

        # _LOGGER.debug("All Results: %s", result)
        return result

    async def async_write_register(
        self, address: int, value, apply: bool = False
    ) -> dict | None:
        """Write register with retry."""
        try:
            result = await self._perform_write_register(address, value, apply)
            self._last_successful_operation = datetime.now()
            return result
        except Exception:
            self._consecutive_errors += 1
            async with self._client_lock:
                await self._safe_close_client()
                self._client = None
            raise

    def _calculate_avg_response_time(self):
        if not self._response_times:
            return None
        return sum(self._response_times) / len(self._response_times)  # pragma: no cover

    async def _perform_write_register(
        self, address: int, value, apply: bool = False
    ) -> dict | None:
        """
        Write one or more Modbus registers using function 0x10 (Write Multiple Registers).

        If apply=True, the configuration is saved to EEPROM (0x02F0)
        and executed (0x02F5) after the write.
        """
        start = time.monotonic()
        self._total_writes += 1

        try:
            client = await self.get_client()
            if client is None or not client.connected:
                self._failed_writes[f"0x{address:04X}"] = (
                    self._failed_writes.get(f"0x{address:04X}", 0) + 1
                )
                raise ModbusException(
                    f"Modbus client connection failed to {self._host}:{self._port}"
                )

            # Ensure value is always a list, even for a single register
            if not isinstance(value, list):
                value = [value]

            result = await modbus_acall(
                client.write_registers,
                self._unit,
                address=address,
                values=value,
            )
            if result.isError():
                self._failed_writes[f"0x{address:04X}"] = (
                    self._failed_writes.get(f"0x{address:04X}", 0) + 1
                )
                _LOGGER.error("Write failed at 0x%04X: %s", address, result)
                return None
            _LOGGER.debug("Wrote register(s) at 0x%04X: %s", address, value)

            # Confirm the write
            await asyncio.sleep(0.05)
            # Read back the register to confirm the write
            confirm = await modbus_acall(
                client.read_holding_registers,
                self._unit,
                address=address,
                count=len(value),
            )
            if confirm.isError():
                _LOGGER.error("Read failed at 0x%04X: %s", address, confirm)
                return None

            # Verify the read-back matches the written value.
            # Skip verification for command registers (e.g. EEPROM save, EXEC)
            # that auto-clear to 0 after being processed by the controller.
            if address not in COMMAND_REGISTERS and confirm.registers != value:
                wrote = value if len(value) > 1 else value[0]
                read_back = (
                    confirm.registers if len(value) > 1 else confirm.registers[0]
                )
                _LOGGER.warning(
                    "Write verification mismatch at 0x%04X: wrote %s, read back %s. "
                    "This may indicate a framing misconfiguration between the "
                    "Modbus gateway and the integration",
                    address,
                    wrote,
                    read_back,
                )

            # If apply is True, save the configuration to EEPROM and execute
            if apply:
                await asyncio.sleep(0.1)
                result = await modbus_acall(
                    client.write_registers,
                    self._unit,
                    address=EEPROM_SAVE_REGISTER,
                    values=[1],
                )

                if result.isError():  # pragma: no cover
                    _LOGGER.error(
                        "EEPROM save failed (0x%04X): %s", EEPROM_SAVE_REGISTER, result
                    )
                    return None
                _LOGGER.debug("EEPROM save triggered (0x%04X)", EEPROM_SAVE_REGISTER)

                await asyncio.sleep(0.1)
                result = await modbus_acall(
                    client.write_registers,
                    self._unit,
                    address=EXEC_REGISTER,
                    values=[1],
                )
                if result.isError():  # pragma: no cover
                    _LOGGER.error("EXEC failed (0x%04X): %s", EXEC_REGISTER, result)
                    return None
                _LOGGER.debug("Config EXEC triggered (0x%04X)", EXEC_REGISTER)
                await asyncio.sleep(0.1)

            # Return useful dict if everything succeeded
            self._successful_write_ops += 1
            self._successful_writes.append((f"0x{address:04X}", time.time()))
            return {
                "address": address,
                "value": value if len(value) > 1 else value[0],
                "confirmed": (
                    confirm.registers if len(value) > 1 else confirm.registers[0]
                ),
            }

        except Exception as e:
            self._failed_writes[f"0x{address:04X}"] = (
                self._failed_writes.get(f"0x{address:04X}", 0) + 1
            )
            raise ModbusException(
                f"Modbus TCP write exception at 0x{address:04X}: {e}"
            ) from e
        finally:
            end = time.monotonic()
            self._write_response_times.append(end - start)

    """ Manual controller for AUX relays (1-4) """

    async def async_write_aux_relay(self, relay_index, on) -> dict | None:
        """Write state of an AUX relay (1-4) using function 0x10 (Write Multiple Registers)."""
        if relay_index not in AUX_BITMASKS:  # pragma: no cover
            _LOGGER.error("Invalid AUX relay index: %s (expected 1–4)", relay_index)
            return None
        aux_bit = AUX_BITMASKS[relay_index]
        addr = 0x010E
        start = time.monotonic()
        self._total_writes += 1
        try:
            client = await self.get_client()
            if client is None or not client.connected:
                self._failed_writes[f"0x{addr:04X}"] = (
                    self._failed_writes.get(f"0x{addr:04X}", 0) + 1
                )
                raise ModbusException(
                    f"Modbus client connection failed to {self._host}:{self._port}"
                )
            # Read current relay state
            current_result = await modbus_acall(
                client.read_input_registers, self._unit, address=addr, count=1
            )
            if current_result.isError():
                raise ModbusException(
                    f"Modbus read error from 0x{addr:04X}: {current_result}"
                )
            current = current_result.registers[0]
            # Set or clear the aux bit
            if on:
                value = current | aux_bit
            else:
                value = current & ~aux_bit
            await modbus_acall(
                client.write_registers, self._unit, address=addr, values=[1]
            )
            await modbus_acall(
                client.write_registers, self._unit, address=addr, values=[value]
            )
            _LOGGER.debug("Wrote relay state at 0x%04X: 0x%04X", addr, value)
            await modbus_acall(
                client.write_registers, self._unit, address=0x0289, values=[0]
            )
            await modbus_acall(
                client.write_registers,
                self._unit,
                address=EXEC_REGISTER,
                values=[1],
            )
            self._successful_write_ops += 1
            self._successful_writes.append((f"0x{addr:04X}", time.time()))

        except Exception as e:
            self._failed_writes[f"0x{addr:04X}"] = (
                self._failed_writes.get(f"0x{addr:04X}", 0) + 1
            )
            raise ModbusException(
                f"Modbus TCP AUX relay write failed at 0x{addr:04X}: {e}"
            ) from e
        finally:
            end = time.monotonic()
            self._write_response_times.append(end - start)

    async def read_all_timers(self, enabled_timers=None, force_read=None) -> dict:
        """Read timers with retry."""
        try:
            result = await self._perform_read_all_timers(enabled_timers, force_read)
            self._last_successful_operation = datetime.now()
            return result
        except Exception:
            self._consecutive_errors += 1
            async with self._client_lock:
                await self._safe_close_client()
                self._client = None
            raise

    async def _perform_read_all_timers(
        self, enabled_timers=None, force_read=None
    ) -> dict:
        """Reads all timer blocks from the device.
        If enabled_timers is provided, only those timers will be read.
        If enabled_timers is None, all timers will be read.
        If force_read is provided, those timers bypass the notification cache
        and are always read fresh from the device.
        Returns a dictionary with timer names as keys and parsed timer data as values.
        """
        timers = {}
        start = time.monotonic()
        effective_timers = (
            set(enabled_timers) if enabled_timers is not None else set(TIMER_BLOCKS)
        )
        force_read = set(force_read or ()) & effective_timers

        # Skip timer reads if the INSTALLER page has not changed since the last poll
        # and this is not a forced full read.
        can_use_cache = not self._last_was_full_read and not (
            self._last_notification & _NOTIF_INSTALLER
        )
        if can_use_cache and self._cached_timers and not force_read:
            _LOGGER.debug("Skipping timer read (no INSTALLER change notification)")
            return {
                k: v for k, v in self._cached_timers.items() if k in effective_timers
            }

        client = await self.get_client()
        if client is None or not client.connected:
            self._failed_reads["timers_connection"] = (
                self._failed_reads.get("timers_connection", 0) + 1
            )
            raise ModbusException(
                f"Modbus client connection failed to {self._host}:{self._port}"
            )
        for name, addr in TIMER_BLOCKS.items():
            if name not in effective_timers:
                continue
            # Use cache for non-forced timers when INSTALLER page hasn't changed
            if can_use_cache and name not in force_read and name in self._cached_timers:
                timers[name] = self._cached_timers[name]
                continue
            try:
                rr = await modbus_acall(
                    client.read_holding_registers, self._unit, address=addr, count=15
                )
            except Exception as e:
                self._failed_reads[f"0x{addr:04X}"] = (
                    self._failed_reads.get(f"0x{addr:04X}", 0) + 1
                )
                _LOGGER.error("Timer block read error at 0x%04X: %s", addr, e)
                continue
            if rr.isError():
                self._failed_reads[f"0x{addr:04X}"] = (
                    self._failed_reads.get(f"0x{addr:04X}", 0) + 1
                )
                _LOGGER.error("Modbus read error from 0x%04X: %s", addr, rr)
                continue
            _LOGGER.debug("Raw rr-%s from 0x%04X: %s", name, addr, rr.registers)
            self._successful_addresses.append((f"0x{addr:04X}", time.time()))
            timers[name] = parse_timer_block(rr.registers)
            await asyncio.sleep(0.05)

        end = time.monotonic()
        self._response_times.append(end - start)
        self._cached_timers.update(timers)
        return timers

    async def write_timer(self, block_name, timer_data) -> bool:
        """Write register with retry."""
        try:
            result = await self._perform_write_timer(block_name, timer_data)
            self._last_successful_operation = datetime.now()
            return result
        except Exception:
            self._consecutive_errors += 1
            async with self._client_lock:
                await self._safe_close_client()
                self._client = None
            raise

    async def _perform_write_timer(self, block_name, timer_data) -> bool:
        """
        Writes only requested fields to a timer block. Preserves all other fields.
        Only update 'on' and 'interval' (and optionally other editable fields).
        Other values (enable, period, function, ...) are preserved as read.
        """
        addr = TIMER_BLOCKS[block_name]
        start = time.monotonic()
        self._total_writes += 1

        # 1. Read current timer block from Modbus
        client = await self.get_client()
        try:
            if client is None or not client.connected:
                self._failed_writes[f"0x{addr:04X}"] = (
                    self._failed_writes.get(f"0x{addr:04X}", 0) + 1
                )
                _LOGGER.error(
                    "Modbus client connection failed to %s:%s", self._host, self._port
                )
                return False
            rr = await modbus_acall(
                client.read_holding_registers, self._unit, address=addr, count=15
            )
            if rr.isError():
                self._failed_writes[f"0x{addr:04X}"] = (
                    self._failed_writes.get(f"0x{addr:04X}", 0) + 1
                )
                _LOGGER.error(
                    "Could not read timer block at 0x%04X before write: %s", addr, rr
                )
                return False
            current_regs = rr.registers
            current_data = parse_timer_block(current_regs)

            # 2. Update only requested fields
            for k, v in timer_data.items():
                current_data[k] = v

            # 3. Build block for write (preserve other fields)
            regs = build_timer_block(current_data)
            for idx, reg in enumerate(regs):
                if not isinstance(reg, int):  # pragma: no cover
                    _LOGGER.error("Register %d is not int: %r", idx, reg)

            _LOGGER.debug(
                "Timer block %s (0x%04X) to write: %s", block_name, addr, regs
            )

            # 4. Write full block back to Modbus
            if client is None or not client.connected:  # pragma: no cover
                _LOGGER.error(
                    "Modbus client connection failed to %s:%s", self._host, self._port
                )
                return False
            result = await modbus_acall(
                client.write_registers, self._unit, address=addr, values=regs
            )
            if result.isError():
                self._failed_writes[f"0x{addr:04X}"] = (
                    self._failed_writes.get(f"0x{addr:04X}", 0) + 1
                )
                _LOGGER.error("Timer block write error at 0x%04X: %s", addr, result)
                return False

            _LOGGER.debug("Wrote timer block %s (0x%04X): %s", block_name, addr, regs)
            await asyncio.sleep(0.1)
            # Write to EEPROM and execute
            await modbus_acall(
                client.write_registers,
                self._unit,
                address=EEPROM_SAVE_REGISTER,
                values=[1],
            )
            await asyncio.sleep(0.1)
            await modbus_acall(
                client.write_registers,
                self._unit,
                address=EXEC_REGISTER,
                values=[1],
            )
            await asyncio.sleep(0.1)

            self._successful_write_ops += 1
            self._successful_writes.append((f"0x{addr:04X}", time.time()))
            return True
        except Exception as e:
            self._failed_writes[f"0x{addr:04X}"] = (
                self._failed_writes.get(f"0x{addr:04X}", 0) + 1
            )
            _LOGGER.error("Modbus TCP write timer exception at 0x%04X: %s", addr, e)
            raise
        finally:
            end = time.monotonic()
            self._write_response_times.append(end - start)

    def _calculate_avg_write_response_time(self):
        if not self._write_response_times:
            return None
        return sum(self._write_response_times) / len(
            self._write_response_times
        )  # pragma: no cover

    @property
    def connection_stats(self) -> dict:
        """Return connection statistics for diagnostics."""
        return {
            "host": self._host,
            "port": self._port,
            "unit_id": self._unit,
            "connected": getattr(self._client, "connected", False),
            "total_operations": self._total_operations,
            "successful_operations": self._successful_operations,
            "consecutive_errors": self._consecutive_errors,
            "success_rate_percent": (
                round(self._successful_operations / self._total_operations * 100, 1)
                if self._total_operations > 0
                else 0
            ),
            "last_successful_operation": (
                self._last_successful_operation.isoformat()
                if self._last_successful_operation
                else None
            ),
            "currently_in_backoff": (
                self._backoff_until is not None and datetime.now() < self._backoff_until
            ),
            "backoff_until": (
                self._backoff_until.isoformat() if self._backoff_until else None
            ),
            "connection_attempts": self._connection_attempts,
            "average_response_time": self._calculate_avg_response_time(),
            "failed_reads_by_address": dict(self._failed_reads),
            "last_successful_addresses": list(self._successful_addresses),
            "write_total_operations": self._total_writes,
            "write_successful_operations": self._successful_write_ops,
            "write_success_rate_percent": (
                round(self._successful_write_ops / self._total_writes * 100, 1)
                if self._total_writes > 0
                else 0
            ),
            "write_average_response_time": self._calculate_avg_write_response_time(),
            "failed_writes_by_address": dict(self._failed_writes),
            "last_successful_writes": list(self._successful_writes),
        }
