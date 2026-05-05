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

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pymodbus.framer import FramerType

import custom_components.vistapool.modbus as vistapool_modbus

ModbusException = vistapool_modbus.ModbusException


@pytest.fixture
def config():
    return {"host": "127.0.0.1", "port": 502, "slave_id": 1}


@pytest.fixture(autouse=True)
def _fast_sleep(monkeypatch):
    """Patch asyncio.sleep to a no-op for all tests in this module to speed them up."""
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())


@pytest.mark.asyncio
async def test_safe_close_client_with_none(config):
    """Test that _safe_close_client does not raise if _client is None."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    await client._safe_close_client()  # Should not raise


@pytest.mark.asyncio
async def test_close_resets_state_and_closes_client(config):
    client = vistapool_modbus.VistaPoolModbusClient(config)
    mock_client = AsyncMock()
    mock_client.connected = True
    mock_client.close = AsyncMock(return_value=None)
    client._client = mock_client
    client._connection_attempts = 42
    client._consecutive_errors = 7
    client._backoff_until = datetime.now()

    await client.close()

    mock_client.close.assert_called()
    assert client._connection_attempts == 0
    assert client._consecutive_errors == 0
    assert client._backoff_until is None
    assert client._client is None


def test_framer_defaults_to_socket(config):
    """Test that missing modbus_framer defaults to FramerType.SOCKET (Modbus TCP)."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    assert client._framer == FramerType.SOCKET


def test_framer_tcp_maps_to_socket():
    """Test that modbus_framer='tcp' maps to FramerType.SOCKET."""
    client = vistapool_modbus.VistaPoolModbusClient(
        {"host": "127.0.0.1", "port": 502, "slave_id": 1, "modbus_framer": "tcp"}
    )
    assert client._framer == FramerType.SOCKET


def test_framer_rtu_maps_to_rtu():
    """Test that modbus_framer='rtu' maps to FramerType.RTU."""
    client = vistapool_modbus.VistaPoolModbusClient(
        {"host": "127.0.0.1", "port": 502, "slave_id": 1, "modbus_framer": "rtu"}
    )
    assert client._framer == FramerType.RTU


def test_framer_normalizes_case_and_whitespace():
    """Test that modbus_framer values are normalized (stripped/lowercased) before mapping."""
    for value, expected in [
        ("  TCP  ", FramerType.SOCKET),
        ("  RTU  ", FramerType.RTU),
        ("TCP", FramerType.SOCKET),
        ("RTU", FramerType.RTU),
    ]:
        client = vistapool_modbus.VistaPoolModbusClient(
            {"host": "127.0.0.1", "port": 502, "slave_id": 1, "modbus_framer": value}
        )
        assert client._framer == expected, f"Expected {expected} for input {value!r}"


def test_framer_unknown_value_falls_back_to_socket_with_warning(caplog):
    """Test that an unknown modbus_framer value falls back to FramerType.SOCKET and logs a warning."""
    import logging

    with caplog.at_level(logging.WARNING, logger="custom_components.vistapool.modbus"):
        client = vistapool_modbus.VistaPoolModbusClient(
            {
                "host": "127.0.0.1",
                "port": 502,
                "slave_id": 1,
                "modbus_framer": "invalid",
            }
        )
    assert client._framer == FramerType.SOCKET
    assert "Unknown modbus_framer value 'invalid'" in caplog.text


@pytest.mark.asyncio
async def test_establish_connection_passes_framer_to_client():
    """Test that _establish_connection_with_retry passes correct framer to AsyncModbusTcpClient."""
    for framer_str, expected_framer in [
        ("tcp", FramerType.SOCKET),
        ("rtu", FramerType.RTU),
    ]:
        client = vistapool_modbus.VistaPoolModbusClient(
            {
                "host": "127.0.0.1",
                "port": 502,
                "slave_id": 1,
                "modbus_framer": framer_str,
            }
        )
        with patch.object(vistapool_modbus, "AsyncModbusTcpClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.connect = AsyncMock(return_value=True)
            mock_instance.connected = True

            await client._establish_connection_with_retry()

            MockClient.assert_called_once_with(
                "127.0.0.1",
                port=502,
                timeout=5,
                framer=expected_framer,
            )


@pytest.mark.asyncio
async def test_establish_connection_with_retry_success(config):
    """Test successful connection establishment with retry."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    with patch.object(vistapool_modbus, "AsyncModbusTcpClient") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.connect = AsyncMock(return_value=True)
        mock_instance.connected = True

        result_client = await client._establish_connection_with_retry()
        assert result_client is mock_instance
        assert client._consecutive_errors == 0


@pytest.mark.asyncio
async def test_establish_connection_with_retry_failure(config):
    """Test failed connection with retries and backoff set."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    with patch.object(vistapool_modbus, "AsyncModbusTcpClient") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.connect = AsyncMock(side_effect=Exception("fail"))
        mock_instance.connected = False

        with pytest.raises(vistapool_modbus.ConnectionException):
            await client._establish_connection_with_retry()
        assert client._backoff_until is not None


@pytest.mark.asyncio
async def test_is_connection_healthy_recent_success(config):
    """Test connection health check with recent successful operation."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    client._client = AsyncMock()
    client._client.connected = True
    client._last_successful_operation = datetime.now()
    assert await client._is_connection_healthy() is True


@pytest.mark.asyncio
async def test_is_connection_healthy_healthcheck(config):
    """Test connection health check logic."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    client._client = AsyncMock()
    client._client.connected = True
    client._last_successful_operation = None

    # Mock successful Modbus reply
    healthy_reply = AsyncMock()
    healthy_reply.isError = lambda: False
    client._client.read_holding_registers = AsyncMock(return_value=healthy_reply)
    assert await client._is_connection_healthy() is True

    # Mock error Modbus reply
    error_reply = AsyncMock()
    error_reply.isError = lambda: True
    client._client.read_holding_registers = AsyncMock(return_value=error_reply)
    client._last_successful_operation = None  # reset!
    assert await client._is_connection_healthy() is False


@pytest.mark.asyncio
async def test_async_read_all_success(config):
    """Test async_read_all returns dict from _perform_read_all."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    client._perform_read_all = AsyncMock(return_value={"data": 123})
    result = await client.async_read_all()
    assert result == {"data": 123}


@pytest.mark.asyncio
async def test_async_read_all_failure(config):
    """Test async_read_all raises if _perform_read_all fails both retries."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    client._perform_read_all = AsyncMock(side_effect=Exception("read fail"))
    with pytest.raises(Exception, match="read fail"):
        await client.async_read_all()


@pytest.mark.asyncio
async def test_async_write_register_success(config):
    """Test async_write_register returns value from _perform_write_register."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    client._perform_write_register = AsyncMock(return_value={"result": True})
    result = await client.async_write_register(0x0100, 123)
    assert result == {"result": True}


@pytest.mark.asyncio
async def test_async_write_register_failure(config):
    """Test async_write_register raises if _perform_write_register raises Exception."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    client._perform_write_register = AsyncMock(side_effect=Exception("write fail"))
    with pytest.raises(Exception, match="write fail"):
        await client.async_write_register(0x0100, 123)


@pytest.mark.asyncio
async def test_write_timer_success(config):
    """Test write_timer returns True if _perform_write_timer succeeds."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    client._perform_write_timer = AsyncMock(return_value=True)
    result = await client.write_timer("filtration1", {"on": 1, "interval": 100})
    assert result is True


@pytest.mark.asyncio
async def test_write_timer_failure(config):
    """Test write_timer raises if _perform_write_timer raises Exception."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    client._perform_write_timer = AsyncMock(side_effect=Exception("timer fail"))
    with pytest.raises(Exception, match="timer fail"):
        await client.write_timer("filtration1", {"on": 0})


@pytest.mark.asyncio
async def test_async_write_aux_relay_success(config):
    """Test async_write_aux_relay returns None (success) or {} (connection error)."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    client._perform_write_aux_relay = AsyncMock(return_value=None)  # type: ignore[attr-defined]
    with pytest.raises(ModbusException):
        await client.async_write_aux_relay(1, True)


@pytest.mark.asyncio
async def test_async_write_aux_relay_failure(config):
    """Test async_write_aux_relay returns {} if _perform_write_aux_relay raises Exception."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    client._perform_write_aux_relay = AsyncMock(side_effect=Exception("aux fail"))  # type: ignore[attr-defined]
    with pytest.raises(ModbusException):
        await client.async_write_aux_relay(1, True)


@pytest.mark.asyncio
async def test_write_register_connection_lost(config):
    client = vistapool_modbus.VistaPoolModbusClient(config)
    # Simulate a ConnectionException during write
    client._perform_write_register = AsyncMock(
        side_effect=vistapool_modbus.ConnectionException("connection lost")
    )
    with pytest.raises(vistapool_modbus.ConnectionException):
        await client.async_write_register(0x0100, 456)
    assert client._consecutive_errors == 1


def test_connection_stats_content(config):
    """Test connection_stats property structure."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    stats = client.connection_stats
    assert stats["host"] == "127.0.0.1"
    assert isinstance(stats["total_operations"], int)
    assert "success_rate_percent" in stats

    # New metrics checks
    for key in [
        "failed_reads_by_address",
        "last_successful_addresses",
        "write_total_operations",
        "write_successful_operations",
        "write_success_rate_percent",
        "write_average_response_time",
        "failed_writes_by_address",
        "last_successful_writes",
    ]:
        assert key in stats


@pytest.mark.asyncio
async def test_perform_read_all_happy_path(config, monkeypatch):
    """Test _perform_read_all returns correct dict when all Modbus reads succeed."""

    client = vistapool_modbus.VistaPoolModbusClient(config)

    # Helper class for simulating Modbus response object
    class DummyResp:
        def __init__(self, regs, is_error=False):
            self.registers = regs
            self.isError = lambda: is_error

    # Prepare a fake Modbus client with async mocks for all register reads (in the correct order!)
    fake_modbus = AsyncMock()
    fake_modbus.connected = True

    # Setup values for all reads in the order used in _perform_read_all:
    # rr00 (holding), rr01 (input), rr02 (holding), rr02_hidro (holding),
    # rr03 (2x holding), rr04 (3x holding), rr05 (holding), rr06 (holding)
    fake_modbus.read_holding_registers = AsyncMock(
        side_effect=[
            DummyResp(
                [
                    1,
                    3,
                    1280,
                    32768,
                    88,
                    47,
                    16707,
                    20497,
                    8248,
                    12592,
                    0,
                    0,
                    0,
                    22069,
                    0,
                    0,  # 0x000F (unused)
                ]
            ),  # rr00
            DummyResp(
                [
                    23971,
                    8,
                    23971,
                    8,
                    26922,
                    0,
                    34208,
                    0,
                    0,
                    65426,
                    0,
                    0,
                    0,
                    0,
                    64136,
                    3,
                    25371,
                    4,
                    16,
                    0,
                ]
            ),  # rr02
            DummyResp([266, 10000]),  # rr02_hidro
            DummyResp(list(range(1, 14))),  # factory block 1 (0x0300, 13)
            DummyResp(list(range(14, 18))),  # factory block 2 (0x0322, 4)
            DummyResp(list(range(1, 32))),  # installer block 1 (0x0408, 31)
            DummyResp(
                [32, 33, 3] + list(range(35, 45))
            ),  # installer block 2 (0x0427, 13) — UV_RELAY_GPIO=3
            DummyResp([0] * 8),  # installer block 3 (0x04E8, 8) FILTVALVE
            DummyResp([650, 0, 750, 700, 0, 0, 700, 0, 100, 0, 0, 0, 5000, 0]),  # rr05
            DummyResp([9, 6, 25604, 5, 0, 2240, 545, 1281, 0, 0, 0, 0, 0]),  # rr06
        ]
    )
    fake_modbus.read_input_registers = AsyncMock(
        return_value=DummyResp(
            [
                0,
                0,
                820,
                709,
                0,
                0,
                140,
                50560,
                49536,
                1280,
                1280,
                0,
                8192,
                16928,
                0,
                0,
                9,
                52,
            ]
        )
    )

    # Patch get_client() to return the fake client
    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    # Call the tested method
    result = await client._perform_read_all()

    # Verify key values in the result (not everything, just main signals)
    assert isinstance(result, dict)
    assert "MBF_POWER_MODULE_VERSION" in result
    assert result["MBF_POWER_MODULE_VERSION"] == 1280
    assert "MBF_MEASURE_PH" in result
    assert result["MBF_MEASURE_PH"] == 8.20
    assert result["MBF_HIDRO_VOLTAGE"] == pytest.approx(5.2)
    assert "MBF_PAR_PH1" in result
    assert result["MBF_PAR_PH1"] == 7.5
    assert "FILTRATION_SPEED" in result
    # MBF_PH_STATUS_ALARM derived from MBF_PH_STATUS (reg01[7]=50560=0xC580)
    # lower 4 bits: 0xC580 & 0x000F = 0
    assert result["MBF_PH_STATUS_ALARM"] == 0

    # Verify that all Modbus calls were made as expected
    assert fake_modbus.read_holding_registers.await_count == 10
    assert fake_modbus.read_input_registers.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fail_block,modbus_method,address,error_type",
    [
        # (block, method, address, error type)
        ("rr00", "read_holding_registers", "0x0000", "exception"),
        ("rr01", "read_input_registers", "0x0100", "exception"),
        ("rr02", "read_holding_registers", "0x0206", "iserror"),
        ("rr02_hidro", "read_holding_registers", "0x0280", "iserror"),
        ("rr03-1", "read_holding_registers", "0x0300", "iserror"),
        ("rr03-2", "read_holding_registers", "0x0322", "iserror"),
        ("rr04-1", "read_holding_registers", "0x0408", "exception"),
        ("rr04-2", "read_holding_registers", "0x0427", "exception"),
        ("rr04-3", "read_holding_registers", "0x04E8", "exception"),
        ("rr05", "read_holding_registers", "0x0502", "iserror"),
        ("rr06", "read_holding_registers", "0x0600", "iserror"),
    ],
)
async def test_perform_read_all_raises_on_block(
    config, monkeypatch, fail_block, modbus_method, address, error_type
):
    """Parametrized test: _perform_read_all exception and isError branches for all main blocks."""

    from custom_components.vistapool.modbus import VistaPoolModbusClient

    client = VistaPoolModbusClient(config)
    fake_modbus = AsyncMock()
    fake_modbus.connected = True

    # Helper class for Modbus response objects
    class DummyResp:
        def __init__(self, regs=None, is_error=False):
            self.registers = regs if regs is not None else [0]
            self.isError = lambda: is_error

    # Blocks order in _perform_read_all
    order = [
        "rr00",
        "rr02",
        "rr02_hidro",
        "rr03-1",
        "rr03-2",
        "rr04-1",
        "rr04-2",
        "rr04-3",
        "rr05",
        "rr06",
    ]

    # Default: all blocks return OK, unless overridden
    rr_blocks = {
        "rr00": DummyResp([0] * 16),
        "rr01": DummyResp([0] * 18),
        "rr02": DummyResp([0] * 20),
        "rr02_hidro": DummyResp([0] * 2),
        "rr03-1": DummyResp([0] * 13),
        "rr03-2": DummyResp([0] * 4),
        "rr04-1": DummyResp([0] * 31),
        "rr04-2": DummyResp([0] * 13),
        "rr04-3": DummyResp([0] * 8),
        "rr05": DummyResp([0] * 14),
        "rr06": DummyResp([0] * 13),
    }

    # Set side effects based on error_type and block
    if error_type == "exception":
        if fail_block == "rr01":
            # For input registers (rr01), raise exception when awaited
            fake_modbus.read_input_registers = AsyncMock(
                side_effect=Exception(f"fail {fail_block}")
            )
            # All holding register blocks return OK DummyResp
            fake_modbus.read_holding_registers = AsyncMock(
                side_effect=[rr_blocks[o] for o in order]
            )
        else:
            # For holding registers, raise exception at the right position
            resp_list = []
            for blk in order:
                if blk == fail_block:
                    resp_list.append(Exception(f"fail {fail_block}"))
                else:
                    resp_list.append(rr_blocks[blk])
            fake_modbus.read_holding_registers = AsyncMock(side_effect=resp_list)
            fake_modbus.read_input_registers = AsyncMock(return_value=rr_blocks["rr01"])
    elif error_type == "iserror":
        # For isError, return DummyResp with isError=True at the selected block
        resp_list = []
        for blk in order:
            if blk == fail_block:
                resp_list.append(DummyResp(is_error=True))
            else:
                resp_list.append(rr_blocks[blk])
        fake_modbus.read_holding_registers = AsyncMock(side_effect=resp_list)
        fake_modbus.read_input_registers = AsyncMock(return_value=rr_blocks["rr01"])

    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    # Run test
    with pytest.raises(ModbusException):
        await client._perform_read_all()

    # Always check that the error was logged
    assert client._failed_reads.get(address, 0) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "block_label, address",
    [
        ("rr00", 0x0000),
        ("rr01", 0x0100),
        ("rr02", 0x0206),
        ("rr02_hidro", 0x0280),
        ("rr03-1", 0x0300),
        ("rr03-2", 0x0322),
        ("rr04-1", 0x0408),
        ("rr04-2", 0x0427),
        ("rr04-3", 0x04E8),
        ("rr05", 0x0502),
        ("rr06", 0x0600),
    ],
)
async def test_perform_read_all_block_exception(
    config, monkeypatch, block_label, address
):
    """
    Covers all 'except Exception as e' branches in _perform_read_all for each Modbus read block.
    If any block fails with exception, the whole function returns {} and logs failed_reads.
    """
    from custom_components.vistapool.modbus import VistaPoolModbusClient

    client = VistaPoolModbusClient(config)
    fake_modbus = AsyncMock()
    fake_modbus.connected = True

    class DummyResp:
        def __init__(self, regs=None):
            self.registers = regs if regs is not None else [0]
            self.isError = lambda: False

    # Prepare response order for all blocks.
    order = [
        ("rr00", DummyResp([0] * 16)),
        ("rr01", DummyResp([0] * 18)),
        ("rr02", DummyResp([0] * 20)),
        ("rr02_hidro", DummyResp([0] * 2)),
        ("rr03-1", DummyResp([0] * 13)),
        ("rr03-2", DummyResp([0] * 4)),
        ("rr04-1", DummyResp([0] * 31)),
        ("rr04-2", DummyResp([0] * 13)),
        ("rr04-3", DummyResp([0] * 8)),
        ("rr05", DummyResp([0] * 14)),
        ("rr06", DummyResp([0] * 13)),
    ]

    # Setup side_effect for each Modbus read. Only the target block raises Exception.
    rh_side_effect = []
    for label, resp in order:
        if label == block_label:
            rh_side_effect.append(Exception(f"Simulated exception at {label}"))
        else:
            rh_side_effect.append(resp)

    # holding: rr00, rr02, rr02_hidro, rr03-01, rr03-02, rr04-1, rr04-2, rr04-3, rr05, rr06 (total 10 calls)
    # input: rr01 (only one call)
    fake_modbus.read_holding_registers = AsyncMock(
        side_effect=[
            rh_side_effect[0],  # rr00 (0x0000)
            rh_side_effect[2],  # rr02 (0x0206)
            rh_side_effect[3],  # rr02_hidro (0x0280)
            rh_side_effect[4],  # rr03-1 (0x0300)
            rh_side_effect[5],  # rr03-2 (0x0322)
            rh_side_effect[6],  # rr04-1 (0x0408)
            rh_side_effect[7],  # rr04-2 (0x0427)
            rh_side_effect[8],  # rr04-3 (0x04E8)
            rh_side_effect[9],  # rr05 (0x0502)
            rh_side_effect[10],  # rr06 (0x0600)
        ]
    )
    fake_modbus.read_input_registers = AsyncMock(
        side_effect=[
            rh_side_effect[1],  # rr01
        ]
    )

    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    with pytest.raises(ModbusException):
        await client._perform_read_all()
    key = f"0x{address:04X}"
    assert client._failed_reads.get(key, 0) == 1


@pytest.mark.asyncio
async def test_read_all_timers_success(config):
    """Test read_all_timers returns dict with timers when _perform_read_all_timers succeeds."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    timers_result = {
        "filtration1": {"enable": 1, "on": 100, "interval": 3600},
        "relay_aux1": {"enable": 0, "on": 0, "interval": 0},
    }
    client._perform_read_all_timers = AsyncMock(return_value=timers_result)
    result = await client.read_all_timers()
    assert result == timers_result


@pytest.mark.asyncio
async def test_read_all_timers_exception(config):
    """Test read_all_timers raises if _perform_read_all_timers throws Exception."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    client._perform_read_all_timers = AsyncMock(side_effect=Exception("timers fail"))
    with pytest.raises(Exception, match="timers fail"):
        await client.read_all_timers()
    assert client._consecutive_errors == 1


@pytest.mark.asyncio
async def test_read_all_timers_not_connected(config):
    """Test read_all_timers returns {} if client is not connected."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    client._perform_read_all_timers = AsyncMock(return_value={})
    result = await client.read_all_timers()
    assert result == {}


@pytest.mark.asyncio
async def test_perform_read_all_timers_all_enabled(config, monkeypatch):
    """Test _perform_read_all_timers reads all timer blocks when enabled_timers is None."""

    client = vistapool_modbus.VistaPoolModbusClient(config)
    fake_modbus = AsyncMock()
    fake_modbus.connected = True

    # Dummy response for timer blocks (always 15 registers, ascending numbers)
    class DummyResp:
        def __init__(self, regs, is_error=False):
            self.registers = regs
            self.isError = lambda: is_error

    # All timer blocks should return this
    fake_modbus.read_holding_registers = AsyncMock(
        return_value=DummyResp(list(range(15)))
    )

    # Patch get_client() to always return our fake_modbus
    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    # Call the method (should read all timers in TIMER_BLOCKS)
    result = await client._perform_read_all_timers(enabled_timers=None)

    # Check that all blocks from TIMER_BLOCKS were read and returned
    from custom_components.vistapool.const import TIMER_BLOCKS

    assert set(result.keys()) == set(TIMER_BLOCKS.keys())
    for timer, data in result.items():
        assert isinstance(data, dict)
        assert "enable" in data
        assert "on" in data
        assert "interval" in data

    # Ensure correct number of calls (one per block)
    assert fake_modbus.read_holding_registers.await_count == len(TIMER_BLOCKS)


@pytest.mark.asyncio
async def test_perform_read_all_timers_only_selected(config, monkeypatch):
    """Test _perform_read_all_timers reads only selected timer blocks."""

    client = vistapool_modbus.VistaPoolModbusClient(config)
    fake_modbus = AsyncMock()
    fake_modbus.connected = True

    class DummyResp:
        def __init__(self, regs, is_error=False):
            self.registers = regs
            self.isError = lambda: is_error

    fake_modbus.read_holding_registers = AsyncMock(return_value=DummyResp([0] * 15))

    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    # Pick two timers only
    enabled = ["filtration1", "relay_aux1"]
    result = await client._perform_read_all_timers(enabled_timers=enabled)
    assert set(result.keys()) == set(enabled)
    assert fake_modbus.read_holding_registers.await_count == len(enabled)


@pytest.mark.asyncio
async def test_perform_read_all_timers_modbus_error(config, monkeypatch):
    """Test _perform_read_all_timers skips block if isError is True."""

    client = vistapool_modbus.VistaPoolModbusClient(config)
    fake_modbus = AsyncMock()
    fake_modbus.connected = True

    class DummyResp:
        def __init__(self, is_error=True):
            self.isError = lambda: is_error
            self.registers = [0] * 15

    fake_modbus.read_holding_registers = AsyncMock(
        return_value=DummyResp(is_error=True)
    )
    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    # Should return empty dict (nothing read successfully)
    result = await client._perform_read_all_timers(enabled_timers=["filtration1"])
    assert result == {}


@pytest.mark.asyncio
async def test_perform_read_all_timers_exception(config, monkeypatch):
    """Test _perform_read_all_timers skips block on exception."""

    client = vistapool_modbus.VistaPoolModbusClient(config)
    fake_modbus = AsyncMock()
    fake_modbus.connected = True

    # Simulate an exception during register read
    fake_modbus.read_holding_registers = AsyncMock(side_effect=Exception("fail"))
    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    result = await client._perform_read_all_timers(enabled_timers=["relay_aux2"])
    assert result == {}


@pytest.mark.asyncio
async def test_perform_read_all_timers_not_connected(config, monkeypatch):
    """Test _perform_read_all_timers if client is not connected."""

    client = vistapool_modbus.VistaPoolModbusClient(config)
    fake_modbus = AsyncMock()
    fake_modbus.connected = False

    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    with pytest.raises(ModbusException):
        await client._perform_read_all_timers()


@pytest.mark.asyncio
async def test_perform_write_register_happy_path(config, monkeypatch):
    """Test _perform_write_register returns dict with confirmation on success."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    fake_modbus = AsyncMock()
    fake_modbus.connected = True

    class DummyResp:
        def __init__(self, val, is_error=False):
            self.isError = lambda: is_error
            self.registers = [val]

    fake_modbus.write_registers = AsyncMock(return_value=DummyResp(123, False))
    fake_modbus.read_holding_registers = AsyncMock(return_value=DummyResp(123, False))
    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    result = await client._perform_write_register(0x0100, 123)
    assert isinstance(result, dict)
    assert result["address"] == 0x0100
    assert result["value"] == 123
    assert result["confirmed"] == 123


@pytest.mark.asyncio
async def test_perform_write_register_mismatch_warning(config, monkeypatch, caplog):
    """Test _perform_write_register logs warning when read-back differs from written value."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    fake_modbus = AsyncMock()
    fake_modbus.connected = True

    class DummyResp:
        def __init__(self, val, is_error=False):
            self.isError = lambda: is_error
            self.registers = [val]

    fake_modbus.write_registers = AsyncMock(return_value=DummyResp(123, False))
    # Read-back returns a different value
    fake_modbus.read_holding_registers = AsyncMock(return_value=DummyResp(999, False))
    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    import logging

    with caplog.at_level(logging.WARNING):
        result = await client._perform_write_register(0x0100, 123)
    # Should still return a result (the write itself succeeded)
    assert result is not None
    assert result["confirmed"] == 999
    assert "Write verification mismatch" in caplog.text
    assert "framing misconfiguration" in caplog.text


@pytest.mark.asyncio
async def test_perform_write_register_write_isError(config, monkeypatch):
    """Test _perform_write_register returns None if write_registers returns error."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    fake_modbus = AsyncMock()
    fake_modbus.connected = True

    class DummyResp:
        def __init__(self, val, is_error):
            self.isError = lambda: is_error
            self.registers = [val]

    fake_modbus.write_registers = AsyncMock(return_value=DummyResp(0, True))
    fake_modbus.read_holding_registers = AsyncMock(return_value=DummyResp(0, False))
    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    result = await client._perform_write_register(0x0100, 123)
    assert result is None


@pytest.mark.asyncio
async def test_perform_write_register_confirm_isError(config, monkeypatch):
    """Test _perform_write_register returns None if confirm read returns error."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    fake_modbus = AsyncMock()
    fake_modbus.connected = True

    class DummyResp:
        def __init__(self, val, is_error):
            self.isError = lambda: is_error
            self.registers = [val]

    fake_modbus.write_registers = AsyncMock(return_value=DummyResp(123, False))
    fake_modbus.read_holding_registers = AsyncMock(return_value=DummyResp(0, True))
    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    result = await client._perform_write_register(0x0100, 123)
    assert result is None


@pytest.mark.asyncio
async def test_perform_write_register_not_connected(config, monkeypatch):
    """Test _perform_write_register raises ModbusException if client is not connected."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    fake_modbus = AsyncMock()
    fake_modbus.connected = False
    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))
    with pytest.raises(ModbusException):
        await client._perform_write_register(0x0100, 123)


@pytest.mark.asyncio
async def test_perform_write_register_exception(config, monkeypatch):
    """Test _perform_write_register raises ModbusException on write exception."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    fake_modbus = AsyncMock()
    fake_modbus.connected = True
    fake_modbus.write_registers = AsyncMock(side_effect=Exception("modbus write fail"))
    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))
    with pytest.raises(ModbusException):
        await client._perform_write_register(0x0100, 123)


@pytest.mark.asyncio
async def test_perform_write_register_apply(config, monkeypatch):
    """Test _perform_write_register triggers EEPROM/EXEC writes when apply=True."""

    client = vistapool_modbus.VistaPoolModbusClient(config)
    fake_modbus = AsyncMock()
    fake_modbus.connected = True

    class DummyResp:
        def __init__(self, is_error=False):
            self.isError = lambda: is_error
            self.registers = [1]

    fake_modbus.write_registers = AsyncMock(return_value=DummyResp(is_error=False))
    fake_modbus.read_holding_registers = AsyncMock(
        return_value=DummyResp(is_error=False)
    )
    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    result = await client._perform_write_register(0x0100, 123, apply=True)
    # Should still succeed, as happy path
    assert result is not None
    # Check that EEPROM and EXEC writes were triggered
    addrs = [
        call.kwargs["address"] for call in fake_modbus.write_registers.await_args_list
    ]
    assert 0x02F0 in addrs and 0x02F5 in addrs

    # There should be at least 3 write_registers calls (register, EEPROM, EXEC)
    assert fake_modbus.write_registers.await_count >= 3


@pytest.mark.asyncio
async def test_perform_write_register_logs_exception(config, monkeypatch, caplog):
    """Test that _perform_write_register logs and raises ModbusException on get_client exception."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    # Simulate get_client raising
    monkeypatch.setattr(
        client, "get_client", AsyncMock(side_effect=Exception("simulated error"))
    )
    with caplog.at_level("ERROR"):
        with pytest.raises(ModbusException):
            await client._perform_write_register(0x0100, 123)
            assert "simulated error" in caplog.text


@pytest.mark.asyncio
async def test_perform_write_timer_happy_path(config, monkeypatch):
    """Test _perform_write_timer updates timer block and triggers EEPROM/EXEC."""

    client = vistapool_modbus.VistaPoolModbusClient(config)
    fake_modbus = AsyncMock()
    fake_modbus.connected = True

    # Dummy response for timer block read (simulate block with 15 registers)
    class DummyResp:
        def __init__(self, regs, is_error=False):
            self.registers = regs
            self.isError = lambda: is_error

    block_name = "filtration1"

    # Read block returns current values
    fake_modbus.read_holding_registers = AsyncMock(return_value=DummyResp([0] * 15))
    # Write block, EEPROM save, EXEC all succeed
    fake_modbus.write_registers = AsyncMock(return_value=DummyResp([], False))

    # Patch get_client()
    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    timer_data = {"on": 123, "interval": 321}
    result = await client._perform_write_timer(block_name, timer_data)
    assert result is True

    # Verify correct addresses used
    assert fake_modbus.read_holding_registers.await_count >= 1
    assert fake_modbus.write_registers.await_count >= 3  # timer write + eeprom + exec


@pytest.mark.asyncio
async def test_perform_write_timer_not_connected(config, monkeypatch):
    """Test _perform_write_timer returns False if client is not connected."""

    client = vistapool_modbus.VistaPoolModbusClient(config)
    fake_modbus = AsyncMock()
    fake_modbus.connected = False
    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    result = await client._perform_write_timer("filtration2", {"on": 10})
    assert result is False


@pytest.mark.asyncio
async def test_perform_write_timer_read_block_error(config, monkeypatch):
    """Test _perform_write_timer returns False if reading timer block fails."""

    client = vistapool_modbus.VistaPoolModbusClient(config)
    fake_modbus = AsyncMock()
    fake_modbus.connected = True

    class DummyResp:
        def __init__(self, is_error=True):
            self.registers = [0] * 15
            self.isError = lambda: is_error

    fake_modbus.read_holding_registers = AsyncMock(
        return_value=DummyResp(is_error=True)
    )
    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    result = await client._perform_write_timer("relay_aux3", {"on": 22})
    assert result is False


@pytest.mark.asyncio
async def test_perform_write_timer_write_raises(config, monkeypatch):
    """Test _perform_write_timer raises if write_registers raises exception."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    fake_modbus = AsyncMock()
    fake_modbus.connected = True

    class DummyResp:
        def __init__(self, regs, is_error=False):
            self.registers = regs
            self.isError = lambda: is_error

    fake_modbus.read_holding_registers = AsyncMock(return_value=DummyResp([0] * 15))
    fake_modbus.write_registers = AsyncMock(side_effect=Exception("modbus write fail"))
    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    with pytest.raises(Exception, match="modbus write fail"):
        await client._perform_write_timer("relay_light", {"on": 1})


@pytest.mark.asyncio
async def test_perform_write_timer_write_isError(config, monkeypatch):
    """Test _perform_write_timer returns False if write_registers returns error."""

    client = vistapool_modbus.VistaPoolModbusClient(config)
    fake_modbus = AsyncMock()
    fake_modbus.connected = True

    class DummyResp:
        def __init__(self, regs=None, is_error=True):
            self.registers = regs if regs is not None else [0] * 15
            self.isError = lambda: is_error

    # read_holding_registers returns ok
    fake_modbus.read_holding_registers = AsyncMock(
        return_value=DummyResp([0] * 15, is_error=False)
    )
    # write_registers returns error (for block write)
    fake_modbus.write_registers = AsyncMock(
        side_effect=[
            DummyResp([], True),  # block write returns error
            DummyResp([], False),  # eeprom save
            DummyResp([], False),  # exec
        ]
    )
    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    result = await client._perform_write_timer("relay_aux4b", {"on": 10})
    assert result is False


@pytest.mark.asyncio
async def test_async_write_aux_relay_on_and_off(config, monkeypatch):
    """Test async_write_aux_relay turns AUX relay ON and OFF successfully."""

    client = vistapool_modbus.VistaPoolModbusClient(config)
    fake_modbus = AsyncMock()
    fake_modbus.connected = True

    # Helper for simulating Modbus reply with current relay state (simulate relay is OFF)
    class DummyResp:
        def __init__(self, regs, is_error=False):
            self.registers = regs
            self.isError = lambda: is_error

    # Always return relay state 0 (all relays OFF) when reading
    fake_modbus.read_input_registers = AsyncMock(return_value=DummyResp([0]))
    # All write_registers succeed
    fake_modbus.write_registers = AsyncMock(return_value=DummyResp([], False))

    # Patch get_client() to always return fake_modbus
    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    # Test turning AUX1 ON (relay_index=1, on=True)
    await client.async_write_aux_relay(1, True)
    # Test turning AUX1 OFF (relay_index=1, on=False)
    # Set initial relay state as ON (bit 0x0008 set)
    fake_modbus.read_input_registers = AsyncMock(return_value=DummyResp([0x0008]))
    await client.async_write_aux_relay(1, False)

    # Verify read and write calls for ON
    # read_input_registers should be called for 0x010E (relay state)
    args, kwargs = fake_modbus.read_input_registers.await_args
    assert kwargs["address"] == 0x010E
    assert kwargs["count"] == 1

    # write_registers is called for the sequence to update relay state and execute config
    # Order of calls: enable register, relay write, disable, execute
    assert fake_modbus.write_registers.await_count == 8  # should be 4 per call


@pytest.mark.asyncio
async def test_async_write_aux_relay_not_connected(config, monkeypatch):
    """Test async_write_aux_relay raises ModbusException if client is not connected."""

    client = vistapool_modbus.VistaPoolModbusClient(config)
    fake_modbus = AsyncMock()
    fake_modbus.connected = False

    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    with pytest.raises(ModbusException):
        await client.async_write_aux_relay(1, True)


@pytest.mark.asyncio
async def test_async_write_aux_relay_read_error(config, monkeypatch):
    """Test async_write_aux_relay handles Modbus error during read_input_registers."""

    client = vistapool_modbus.VistaPoolModbusClient(config)
    fake_modbus = AsyncMock()
    fake_modbus.connected = True

    # Simulate Modbus error
    class DummyResp:
        def __init__(self):
            self.isError = lambda: True

    fake_modbus.read_input_registers = AsyncMock(return_value=DummyResp())
    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    with pytest.raises(ModbusException):
        await client.async_write_aux_relay(1, True)


@pytest.mark.asyncio
async def test_async_write_aux_relay_write_exception(config, monkeypatch):
    """Test async_write_aux_relay raises ModbusException if write_registers throws exception."""

    client = vistapool_modbus.VistaPoolModbusClient(config)
    fake_modbus = AsyncMock()
    fake_modbus.connected = True

    class DummyResp:
        def __init__(self, regs):
            self.registers = regs
            self.isError = lambda: False

    # First, reading relay state works
    fake_modbus.read_input_registers = AsyncMock(return_value=DummyResp([0]))
    # write_registers throws exception
    fake_modbus.write_registers = AsyncMock(side_effect=Exception("write fail"))
    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    with pytest.raises(ModbusException):
        await client.async_write_aux_relay(1, True)


@pytest.mark.asyncio
async def test_get_client_respects_backoff(config):
    c = vistapool_modbus.VistaPoolModbusClient(config)
    c._backoff_until = datetime.now() + timedelta(seconds=5)
    with pytest.raises(vistapool_modbus.ConnectionException):
        await c.get_client()


# --- FC20 broadcast filter tests ---

RTU_CONFIG = {"host": "127.0.0.1", "port": 502, "slave_id": 1, "modbus_framer": "rtu"}
TCP_CONFIG = {"host": "127.0.0.1", "port": 502, "slave_id": 1, "modbus_framer": "tcp"}


def _client_with_ctx(
    cfg: dict,
) -> tuple[vistapool_modbus.VistaPoolModbusClient, Any, Any, list]:
    """Return a (VistaPoolModbusClient, mock_ctx, mock_client, received) tuple."""
    client = vistapool_modbus.VistaPoolModbusClient(cfg)
    received = []
    mock_ctx = type(
        "Ctx", (), {"data_received": lambda self, data: received.append(data)}
    )()
    mock_client = type("MC", (), {"ctx": mock_ctx})()
    return client, mock_ctx, mock_client, received


# ---- RTU framing ----


def test_install_fc20_filter_rtu_filters_fc20_frames():
    """FC20 broadcast frames are dropped with RTU framing."""
    client, mock_ctx, mock_client, received = _client_with_ctx(RTU_CONFIG)
    client._install_fc20_filter(mock_client)

    fc20_frame = bytes([1, 0x20, 0x02, 0x01, 0x5A, 0xBB, 0x39])
    mock_ctx.data_received(fc20_frame)
    assert received == [], "FC20 frame should have been filtered out"


def test_install_fc20_filter_rtu_filters_fc20_frames_with_debug_logging(caplog):
    """FC20 broadcast frames are dropped and debug-logged when DEBUG is enabled."""
    import logging

    client, mock_ctx, mock_client, received = _client_with_ctx(RTU_CONFIG)
    client._install_fc20_filter(mock_client)

    fc20_frame = bytes([1, 0x20, 0x02, 0x01, 0x5A, 0xBB, 0x39])
    with caplog.at_level(logging.DEBUG, logger="custom_components.vistapool.modbus"):
        mock_ctx.data_received(fc20_frame)

    assert received == [], "FC20 frame should have been filtered out"
    assert any("FC20 broadcast frame filtered" in m for m in caplog.messages)


def test_install_fc20_filter_rtu_drops_coalesced_chunk_entirely():
    """When an FC20 broadcast and a valid FC03 response arrive in the same TCP chunk,
    the entire chunk is dropped.

    The FC20 proprietary frame layout cannot be reliably parsed to determine its
    length (the observed 27-byte frame has data[6]=0x39=57, yielding a bogus
    fc20_len=66), so forwarding trailing bytes based on a miscomputed offset
    would corrupt pymodbus.  Dropping the whole chunk is the safe choice;
    pymodbus will retry and the next poll cycle will succeed.
    """
    client, mock_ctx, mock_client, received = _client_with_ctx(RTU_CONFIG)
    client._install_fc20_filter(mock_client)

    fc20_frame = bytes([0x01, 0x20, 0x02, 0x01, 0x00, 0x01, 0x00, 0xAA, 0xBB])
    fc03_tail = bytes([0x01, 0x03, 0x02, 0x00, 0x64, 0xB9, 0xAF])
    mock_ctx.data_received(fc20_frame + fc03_tail)
    assert received == [], "Entire chunk must be dropped when FC20 is detected"


def test_install_fc20_filter_rtu_drops_partial_fc20_frame():
    """A partial FC20 chunk that matches the FC20 signature is silently dropped."""
    client, mock_ctx, mock_client, received = _client_with_ctx(RTU_CONFIG)
    client._install_fc20_filter(mock_client)

    partial_fc20 = bytes([0x01, 0x20, 0x02, 0x01])
    mock_ctx.data_received(partial_fc20)
    assert received == [], "Partial FC20 chunk must be dropped"


def test_install_fc20_filter_rtu_split_fc20_second_chunk_not_dropped():
    """When an FC20 frame is split across two calls, the second chunk (FC20 tail +
    any coalesced valid response) is forwarded so valid data is never silently lost.

    The first call contains a partial FC20 and is filtered; the second call starts
    with the remaining FC20 bytes which do not match the FC20 pattern (data[1] != 0x20),
    so the entire second chunk — including any trailing valid response — is forwarded.
    """
    client, mock_ctx, mock_client, received = _client_with_ctx(RTU_CONFIG)
    client._install_fc20_filter(mock_client)

    # FC20 frame (byte_count=0 → 9 bytes total), split after the 5th byte.
    fc20_first = bytes([0x01, 0x20, 0x02, 0x01, 0x00])  # partial: matched & dropped
    # Remaining 4 FC20 bytes followed by a valid FC03 response in the same chunk.
    fc20_tail_plus_response = bytes(
        [0x01, 0x00, 0xAA, 0xBB]  # FC20 tail (CRC region), data[1]=0x00 ≠ 0x20
        + [0x01, 0x03, 0x02, 0x00, 0x64, 0xB9, 0xAF]  # valid FC03 response
    )

    mock_ctx.data_received(fc20_first)
    assert received == [], "First partial-FC20 chunk must be dropped"

    mock_ctx.data_received(fc20_tail_plus_response)
    assert received == [fc20_tail_plus_response], (
        "Second chunk (FC20 tail + valid response) must be forwarded — valid data must not be lost"
    )


def test_install_fc20_filter_rtu_passes_normal_frames():
    """Normal FC03 frames are forwarded unchanged with RTU framing."""
    client, mock_ctx, mock_client, received = _client_with_ctx(RTU_CONFIG)
    client._install_fc20_filter(mock_client)

    fc03_frame = bytes([1, 0x03, 0x02, 0x00, 0x64, 0xB9, 0xAF])
    mock_ctx.data_received(fc03_frame)
    assert received == [fc03_frame], "FC03 frame should pass through the filter"


def test_install_fc20_filter_rtu_wrong_unit_id_not_filtered():
    """FC20 frames from a different slave ID are NOT filtered with RTU framing."""
    cfg = {**RTU_CONFIG, "slave_id": 2}
    client, mock_ctx, mock_client, received = _client_with_ctx(cfg)
    client._install_fc20_filter(mock_client)

    frame = bytes([1, 0x20, 0x02, 0x01])
    mock_ctx.data_received(frame)
    assert received == [frame], "Frame from different slave ID should not be filtered"


# ---- SOCKET (Modbus TCP) framing ----


def test_install_fc20_filter_socket_filters_fc20_broadcasts():
    """Raw FC20 broadcasts (no MBAP header, bytes 2-3 != 0x0000) are dropped with SOCKET framing.

    The pool controller sends FC20 frames as raw RTU bytes without an MBAP header.
    These arrive on the TCP socket with bytes 2-3 = 0x0201 (not the Modbus TCP
    Protocol Identifier 0x0000), so the filter can safely identify and drop them.
    """
    client, mock_ctx, mock_client, received = _client_with_ctx(TCP_CONFIG)
    client._install_fc20_filter(mock_client)

    # Raw FC20 broadcast without MBAP: data[2:4] = 0x02 0x01 (not 0x00 0x00)
    fc20_frame = bytes([0x01, 0x20, 0x02, 0x01, 0x5A, 0xBB, 0x39])
    mock_ctx.data_received(fc20_frame)
    assert received == [], "Raw FC20 broadcast should be filtered with SOCKET framing"


def test_install_fc20_filter_socket_passes_valid_mbap_response_with_tid_0x0120():
    """A legitimate Modbus TCP response with TID=0x0120 must NOT be filtered.

    With SOCKET framing, data[0:2] is the MBAP Transaction ID. A TID of 0x0120
    gives data[0]=0x01, data[1]=0x20, which overlaps with the FC20 signature.
    However, a valid Modbus TCP frame always has Protocol ID 0x0000 at bytes 2-3,
    so the filter must let it through.
    """
    client, mock_ctx, mock_client, received = _client_with_ctx(TCP_CONFIG)
    client._install_fc20_filter(mock_client)

    # Valid Modbus TCP response: TID=0x0120, Protocol ID=0x0000, Length=5 (unit_id + fc + byte_count + 2 data bytes)
    valid_mbap = bytes(
        [0x01, 0x20, 0x00, 0x00, 0x00, 0x05, 0x01, 0x03, 0x02, 0x00, 0x64]
    )
    mock_ctx.data_received(valid_mbap)
    assert received == [valid_mbap], (
        "Legitimate Modbus TCP response must not be filtered"
    )


def test_install_fc20_filter_socket_passes_normal_frames():
    """Normal Modbus TCP responses (no TID overlap) pass through with SOCKET framing."""
    client, mock_ctx, mock_client, received = _client_with_ctx(TCP_CONFIG)
    client._install_fc20_filter(mock_client)

    # Normal FC03 response with TID=0x0001
    normal_frame = bytes(
        [0x00, 0x01, 0x00, 0x00, 0x00, 0x05, 0x01, 0x03, 0x02, 0x00, 0x64]
    )
    mock_ctx.data_received(normal_frame)
    assert received == [normal_frame], "Normal Modbus TCP frame must pass through"


def test_install_fc20_filter_socket_drops_coalesced_chunk_entirely():
    """With SOCKET framing, when an FC20 broadcast and a valid Modbus TCP response
    arrive in the same TCP chunk, the entire chunk is dropped.

    Same rationale as the RTU coalesced case: the FC20 frame length cannot be
    reliably computed from the proprietary payload, so forwarding trailing bytes
    would risk passing garbage to pymodbus.  The entire chunk is dropped and
    pymodbus retries on the next poll cycle.
    """
    client, mock_ctx, mock_client, received = _client_with_ctx(TCP_CONFIG)
    client._install_fc20_filter(mock_client)

    # Raw FC20 broadcast without MBAP: bytes 2-3 = 0x02 0x01 (not 0x00 0x00).
    fc20_frame = bytes([0x01, 0x20, 0x02, 0x01, 0x00, 0x01, 0x00, 0xAA, 0xBB])
    mbap_response = bytes(
        [0x00, 0x01, 0x00, 0x00, 0x00, 0x05, 0x01, 0x03, 0x02, 0x00, 0x64]
    )
    mock_ctx.data_received(fc20_frame + mbap_response)
    assert received == [], "Entire chunk must be dropped when FC20 is detected"


def test_install_fc20_filter_socket_buffers_short_ambiguous_prefix_then_drops():
    """SOCKET: 2–3 byte chunk starting with [unit_id, 0x20] is buffered; once the
    next chunk provides the Protocol ID bytes and they confirm a raw FC20 broadcast
    (≠ 0x0000), the combined data is dropped.
    """
    client, mock_ctx, mock_client, received = _client_with_ctx(TCP_CONFIG)
    client._install_fc20_filter(mock_client)

    # First TCP read: only first 2 bytes of a raw FC20 broadcast.
    mock_ctx.data_received(bytes([0x01, 0x20]))
    assert received == [], "Short ambiguous prefix must be buffered, not forwarded"

    # Second TCP read: rest of the FC20 frame; combined [0x01,0x20,0x02,0x01,...] → FC20.
    mock_ctx.data_received(bytes([0x02, 0x01, 0x5A, 0xBB, 0x39]))
    assert received == [], "Reassembled FC20 broadcast must be dropped"


def test_install_fc20_filter_socket_buffers_short_ambiguous_prefix_then_passes():
    """SOCKET: 2–3 byte chunk starting with [unit_id, 0x20] is buffered; once the
    next chunk provides the Protocol ID bytes and they confirm a valid Modbus TCP
    frame (PID = 0x0000), the combined data is forwarded unchanged.
    """
    client, mock_ctx, mock_client, received = _client_with_ctx(TCP_CONFIG)
    client._install_fc20_filter(mock_client)

    # First TCP read: first 2 bytes of a Modbus TCP response with TID=0x0120.
    mock_ctx.data_received(bytes([0x01, 0x20]))
    assert received == [], "Short ambiguous prefix must be buffered, not forwarded"

    # Second TCP read: bytes 2 onward; combined [0x01,0x20,0x00,0x00,...] → valid MBAP.
    rest = bytes([0x00, 0x00, 0x00, 0x05, 0x01, 0x03, 0x02, 0x00, 0x64])
    mock_ctx.data_received(rest)
    expected = bytes([0x01, 0x20]) + rest
    assert received == [expected], "Reassembled valid MBAP response must be forwarded"


def test_install_fc20_filter_socket_buffers_3_byte_prefix_then_drops():
    """SOCKET: 3-byte chunk [unit_id, 0x20, x] is still too short to check PID;
    it is buffered and the FC20 is only recognised once the 4th byte arrives.
    """
    client, mock_ctx, mock_client, received = _client_with_ctx(TCP_CONFIG)
    client._install_fc20_filter(mock_client)

    mock_ctx.data_received(bytes([0x01, 0x20, 0x02]))
    assert received == [], "3-byte prefix must be buffered"

    mock_ctx.data_received(bytes([0x01, 0x5A, 0xBB]))  # byte3=0x01 → PID=0x0201 → FC20
    assert received == [], "FC20 recognised after 4th byte is received — drop"


# ---- Safety / edge cases ----


def test_install_fc20_filter_no_ctx_is_safe():
    """If client has no ctx attribute, the method must not raise."""
    client = vistapool_modbus.VistaPoolModbusClient(RTU_CONFIG)
    mock_client = type("MC", (), {})()
    client._install_fc20_filter(mock_client)  # type: ignore[arg-type]


def test_install_fc20_filter_exception_is_safe():
    """If an unexpected exception occurs when patching, the method must not raise."""
    client = vistapool_modbus.VistaPoolModbusClient(RTU_CONFIG)

    class BadCtx:
        @property
        def data_received(self):
            raise RuntimeError("boom")

        @data_received.setter
        def data_received(self, value):
            raise RuntimeError("boom on set")

    mock_client = type("MC", (), {"ctx": BadCtx()})()
    client._install_fc20_filter(mock_client)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_establish_connection_installs_fc20_filter(config):
    """After a successful connection, _install_fc20_filter is called."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    with patch.object(vistapool_modbus, "AsyncModbusTcpClient") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.connect = AsyncMock(return_value=True)
        mock_instance.connected = True

        with patch.object(client, "_install_fc20_filter") as mock_filter:
            await client._establish_connection_with_retry()
            mock_filter.assert_called_once_with(mock_instance)


# ---------------------------------------------------------------------------
# MBF_NOTIFICATION-based polling optimisation tests
# ---------------------------------------------------------------------------


class _DummyResp:
    """Minimal stand-in for a pymodbus register-read response."""

    def __init__(self, regs, is_error=False):
        self.registers = list(regs)
        self.isError = lambda: is_error


def _measure_regs(notification: int = 0) -> list:
    """Return a 18-register MEASURE block with the given notification value at index 16."""
    regs = [0] * 18
    regs[16] = notification  # MBF_NOTIFICATION is at offset 0x0110-0x0100 = 16
    return regs


@pytest.mark.asyncio
async def test_perform_read_all_skips_config_pages_when_no_notification(
    config, monkeypatch
):
    """When notification=0 and not at full-read interval, all config page reads are skipped."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    client._polls_since_full_read = 0  # not at interval → partial read allowed

    fake_modbus = AsyncMock()
    fake_modbus.connected = True
    fake_modbus.read_input_registers = AsyncMock(
        return_value=_DummyResp(_measure_regs(notification=0))
    )
    # read_holding_registers must NOT be called
    fake_modbus.read_holding_registers = AsyncMock()

    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    result = await client._perform_read_all()

    assert isinstance(result, dict)
    fake_modbus.read_holding_registers.assert_not_called()
    assert client._polls_since_full_read == 1  # incremented, not reset


@pytest.mark.asyncio
async def test_perform_read_all_reads_only_factory_when_factory_notified(
    config, monkeypatch
):
    """When only FACTORY notification bit is set, only FACTORY holding regs are read (2 calls)."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    client._polls_since_full_read = 0

    fake_modbus = AsyncMock()
    fake_modbus.connected = True
    fake_modbus.read_input_registers = AsyncMock(
        return_value=_DummyResp(
            _measure_regs(notification=vistapool_modbus._NOTIF_FACTORY)
        )
    )
    # FACTORY: 2 calls — (0x0300, 13) and (0x0322, 4)
    fake_modbus.read_holding_registers = AsyncMock(
        side_effect=[
            _DummyResp([0] * 13),  # rr03-1
            _DummyResp([0] * 4),  # rr03-2
        ]
    )

    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    result = await client._perform_read_all()

    assert fake_modbus.read_holding_registers.await_count == 2
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_perform_read_all_force_full_after_interval(config, monkeypatch):
    """When _polls_since_full_read reaches _FULL_READ_INTERVAL, all pages are read."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    client._polls_since_full_read = (
        vistapool_modbus._FULL_READ_INTERVAL
    )  # force_full=True

    fake_modbus = AsyncMock()
    fake_modbus.connected = True
    fake_modbus.read_input_registers = AsyncMock(
        return_value=_DummyResp(
            _measure_regs(notification=0)
        )  # no notification bits set
    )
    # Full read: rr00(1) + rr02(1) + rr02_hidro(1) + rr03(2) + rr04(3) + rr05(1) + rr06(1) = 10 calls
    fake_modbus.read_holding_registers = AsyncMock(
        side_effect=[
            _DummyResp([0] * 16),  # rr00
            _DummyResp([0] * 20),  # rr02
            _DummyResp([0] * 2),  # rr02_hidro
            _DummyResp([0] * 13),  # rr03-1
            _DummyResp([0] * 4),  # rr03-2
            _DummyResp([0] * 31),  # rr04-1
            _DummyResp([0] * 13),  # rr04-2
            _DummyResp([0] * 8),  # rr04-3 (FILTVALVE 0x04E8)
            _DummyResp([0] * 14),  # rr05
            _DummyResp([0] * 13),  # rr06
        ]
    )

    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    result = await client._perform_read_all()

    assert fake_modbus.read_holding_registers.await_count == 10
    assert client._polls_since_full_read == 0  # was reset after full read
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_perform_read_all_clears_notification_register(config, monkeypatch):
    """When notification != 0, write_registers is called to clear MBF_NOTIFICATION (0x0110)."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    client._polls_since_full_read = 0

    fake_modbus = AsyncMock()
    fake_modbus.connected = True
    fake_modbus.read_input_registers = AsyncMock(
        return_value=_DummyResp(
            _measure_regs(notification=vistapool_modbus._NOTIF_GLOBAL)
        )
    )
    # GLOBAL: rr02 (0x0206, 20) + rr02_hidro (0x0280, 2)
    fake_modbus.read_holding_registers = AsyncMock(
        side_effect=[
            _DummyResp([0] * 20),  # rr02
            _DummyResp([0] * 2),  # rr02_hidro
        ]
    )

    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    await client._perform_read_all()

    # write_registers must have been awaited with address=0x0110 and values=[0]
    assert fake_modbus.write_registers.called
    call_kwargs = fake_modbus.write_registers.call_args.kwargs
    assert call_kwargs.get("address") == 0x0110
    assert call_kwargs.get("values") == [0]


@pytest.mark.asyncio
async def test_perform_read_all_does_not_clear_when_notification_zero(
    config, monkeypatch
):
    """When notification == 0, write_registers is NOT called."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    client._polls_since_full_read = 0

    fake_modbus = AsyncMock()
    fake_modbus.connected = True
    fake_modbus.read_input_registers = AsyncMock(
        return_value=_DummyResp(_measure_regs(notification=0))
    )
    fake_modbus.read_holding_registers = AsyncMock()

    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    await client._perform_read_all()

    fake_modbus.write_registers.assert_not_called()


@pytest.mark.asyncio
async def test_perform_read_all_cache_serves_unread_pages(config, monkeypatch):
    """Cached values for pages not re-read are carried forward in the result."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    client._polls_since_full_read = 0
    # Pre-populate cache with a known FACTORY value
    client._cached_result = {"MBF_PAR_VERSION": 2055, "MBF_PAR_MODEL": 10}

    fake_modbus = AsyncMock()
    fake_modbus.connected = True
    # notification=0 → no pages re-read, cache is used
    fake_modbus.read_input_registers = AsyncMock(
        return_value=_DummyResp(_measure_regs(notification=0))
    )
    fake_modbus.read_holding_registers = AsyncMock()

    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    result = await client._perform_read_all()

    assert result.get("MBF_PAR_VERSION") == 2055
    assert result.get("MBF_PAR_MODEL") == 10
    fake_modbus.read_holding_registers.assert_not_called()


@pytest.mark.asyncio
async def test_perform_read_all_poll_counter_resets_on_full_read(config, monkeypatch):
    """After a forced full read, _polls_since_full_read is reset to 0."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    # A new client starts at _FULL_READ_INTERVAL → first poll is always a full read
    assert client._polls_since_full_read == vistapool_modbus._FULL_READ_INTERVAL

    fake_modbus = AsyncMock()
    fake_modbus.connected = True
    fake_modbus.read_input_registers = AsyncMock(
        return_value=_DummyResp(_measure_regs(notification=0))
    )
    fake_modbus.read_holding_registers = AsyncMock(
        side_effect=[
            _DummyResp([0] * 16),  # rr00
            _DummyResp([0] * 20),  # rr02
            _DummyResp([0] * 2),  # rr02_hidro
            _DummyResp([0] * 13),  # rr03-1
            _DummyResp([0] * 4),  # rr03-2
            _DummyResp([0] * 31),  # rr04-1
            _DummyResp([0] * 13),  # rr04-2
            _DummyResp([0] * 8),  # rr04-3 (FILTVALVE 0x04E8)
            _DummyResp([0] * 14),  # rr05
            _DummyResp([0] * 13),  # rr06
        ]
    )

    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    await client._perform_read_all()

    assert client._polls_since_full_read == 0


@pytest.mark.asyncio
async def test_perform_read_all_cached_result_updated_after_read(config, monkeypatch):
    """After each _perform_read_all call, _cached_result is updated with the latest data."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    client._polls_since_full_read = 0

    measure_regs = _measure_regs(notification=vistapool_modbus._NOTIF_FACTORY)
    # Set MBF_MEASURE_PH (index 2) to a known value → 820 = 8.20 pH
    measure_regs[2] = 820

    fake_modbus = AsyncMock()
    fake_modbus.connected = True
    fake_modbus.read_input_registers = AsyncMock(return_value=_DummyResp(measure_regs))
    fake_modbus.read_holding_registers = AsyncMock(
        side_effect=[
            _DummyResp([0] * 13),  # rr03-1
            _DummyResp([0] * 4),  # rr03-2
        ]
    )

    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    await client._perform_read_all()

    # _cached_result must now contain the MEASURE values just read
    assert client._cached_result.get("MBF_MEASURE_PH") == pytest.approx(8.20)


@pytest.mark.asyncio
async def test_perform_read_all_notification_clear_failure_is_silently_ignored(
    config, monkeypatch, caplog
):
    """When write_registers raises while clearing MBF_NOTIFICATION, the error is swallowed and logged at DEBUG."""
    import logging

    client = vistapool_modbus.VistaPoolModbusClient(config)
    client._polls_since_full_read = 0

    fake_modbus = AsyncMock()
    fake_modbus.connected = True
    fake_modbus.read_input_registers = AsyncMock(
        return_value=_DummyResp(
            _measure_regs(notification=vistapool_modbus._NOTIF_GLOBAL)
        )
    )
    # GLOBAL: rr02 + rr02_hidro
    fake_modbus.read_holding_registers = AsyncMock(
        side_effect=[
            _DummyResp([0] * 20),  # rr02
            _DummyResp([0] * 2),  # rr02_hidro
        ]
    )
    # Make the notification-clear write raise
    fake_modbus.write_registers = AsyncMock(side_effect=Exception("write denied"))

    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    with caplog.at_level(logging.DEBUG, logger="custom_components.vistapool.modbus"):
        result = await client._perform_read_all()

    # Must not raise, must return a valid dict
    assert isinstance(result, dict)
    assert "Could not clear MBF_NOTIFICATION" in caplog.text


@pytest.mark.asyncio
async def test_perform_read_all_reads_installer_and_user_when_both_notified(
    config, monkeypatch
):
    """When both INSTALLER and USER notification bits are set, both page blocks are read."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    client._polls_since_full_read = 0

    notification = vistapool_modbus._NOTIF_INSTALLER | vistapool_modbus._NOTIF_USER

    fake_modbus = AsyncMock()
    fake_modbus.connected = True
    fake_modbus.read_input_registers = AsyncMock(
        return_value=_DummyResp(_measure_regs(notification=notification))
    )
    # INSTALLER: 3 blocks (0x0408+0x0427+0x04E8), USER: 1 block (0x0502) = 4 holding calls total
    fake_modbus.read_holding_registers = AsyncMock(
        side_effect=[
            _DummyResp([0] * 31),  # rr04-1
            _DummyResp([0] * 13),  # rr04-2
            _DummyResp([0] * 8),  # rr04-3 (FILTVALVE 0x04E8)
            _DummyResp([0] * 14),  # rr05
        ]
    )

    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    result = await client._perform_read_all()

    assert fake_modbus.read_holding_registers.await_count == 4
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_perform_read_all_timers_skips_when_no_installer_notification(
    config, monkeypatch
):
    """_perform_read_all_timers returns cached data without any Modbus reads when
    INSTALLER notification bit is not set and it is not a full-read poll.
    When enabled_timers is provided, only the requested subset is returned."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    # Simulate state after a previous partial read with no INSTALLER notification
    client._last_was_full_read = False
    client._last_notification = 0
    client._cached_timers = {
        "filtration1": {
            "enable": 1,
            "on": 3600,
            "interval": 7200,
            "period": 1,
            "function": 1,
        },
        "filtration2": {
            "enable": 0,
            "on": 0,
            "interval": 0,
            "period": 1,
            "function": 1,
        },
    }

    fake_modbus = AsyncMock()
    fake_modbus.connected = True
    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    # Only filtration1 is enabled - filtration2 must NOT appear in the result
    result = await client._perform_read_all_timers(enabled_timers=["filtration1"])

    assert result == {"filtration1": client._cached_timers["filtration1"]}
    assert "filtration2" not in result
    fake_modbus.read_holding_registers.assert_not_called()


@pytest.mark.asyncio
async def test_perform_read_all_timers_skips_returns_all_cached_when_enabled_timers_none(
    config, monkeypatch
):
    """When enabled_timers=None and the read is skipped, the full cache is returned."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    client._last_was_full_read = False
    client._last_notification = 0
    client._cached_timers = {
        "filtration1": {
            "enable": 1,
            "on": 3600,
            "interval": 7200,
            "period": 1,
            "function": 1,
        },
        "filtration2": {
            "enable": 0,
            "on": 0,
            "interval": 0,
            "period": 1,
            "function": 1,
        },
    }

    fake_modbus = AsyncMock()
    fake_modbus.connected = True
    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    result = await client._perform_read_all_timers(enabled_timers=None)

    assert result == client._cached_timers
    fake_modbus.read_holding_registers.assert_not_called()


@pytest.mark.asyncio
async def test_perform_read_all_timers_force_read_bypasses_cache(config, monkeypatch):
    """force_read timers are re-read from Modbus even when the cache would be used."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    client._last_was_full_read = False
    client._last_notification = 0  # no notification — cache would normally be used
    client._cached_timers = {
        "filtration1": {
            "enable": 1,
            "on": 3600,
            "interval": 7200,
            "period": 1,
            "function": 1,
            "countdown": 999,
        },
        "filtration2": {
            "enable": 0,
            "on": 0,
            "interval": 0,
            "period": 1,
            "function": 1,
            "countdown": 0,
        },
    }

    fake_modbus = AsyncMock()
    fake_modbus.connected = True
    fake_modbus.read_holding_registers = AsyncMock(return_value=_DummyResp([0] * 15))
    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    result = await client._perform_read_all_timers(
        enabled_timers=["filtration1", "filtration2"],
        force_read=["filtration1"],
    )

    # filtration1 must be read fresh (force_read), filtration2 served from cache
    assert fake_modbus.read_holding_registers.await_count == 1
    assert "filtration1" in result
    assert "filtration2" in result
    # filtration2 should retain cached countdown value
    assert result["filtration2"]["countdown"] == 0


@pytest.mark.asyncio
async def test_perform_read_all_timers_reads_when_installer_notified(
    config, monkeypatch
):
    """_perform_read_all_timers reads Modbus when INSTALLER notification bit is set."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    client._last_was_full_read = False
    client._last_notification = vistapool_modbus._NOTIF_INSTALLER
    client._cached_timers = {}

    fake_modbus = AsyncMock()
    fake_modbus.connected = True
    fake_modbus.read_holding_registers = AsyncMock(return_value=_DummyResp([0] * 15))
    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    result = await client._perform_read_all_timers(enabled_timers=["filtration1"])

    fake_modbus.read_holding_registers.assert_called_once()
    assert "filtration1" in result
    # Cache must be updated after the read
    assert "filtration1" in client._cached_timers


@pytest.mark.asyncio
async def test_perform_read_all_timers_reads_on_full_read_even_without_notification(
    config, monkeypatch
):
    """_perform_read_all_timers reads Modbus when _last_was_full_read=True regardless of notification."""
    client = vistapool_modbus.VistaPoolModbusClient(config)
    client._last_was_full_read = True  # forced full read
    client._last_notification = 0  # no notification bits
    client._cached_timers = {
        "filtration1": {"enable": 0, "on": 0, "interval": 0, "period": 1, "function": 1}
    }

    fake_modbus = AsyncMock()
    fake_modbus.connected = True
    fake_modbus.read_holding_registers = AsyncMock(return_value=_DummyResp([0] * 15))
    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    result = await client._perform_read_all_timers(enabled_timers=["filtration1"])

    fake_modbus.read_holding_registers.assert_called_once()
    assert "filtration1" in result


@pytest.mark.asyncio
async def test_filtration_fixup_skipped_on_partial_read(config, monkeypatch):
    """Cached MBF_PAR_FILTRATION_STATE must not override a fresh MBF_RELAY_STATE.

    Scenario (issue #122): On a partial read (no INSTALLER notification), the
    INSTALLER page is not re-read. The cached MBF_PAR_FILTRATION_STATE may be
    stale (0=off) while the fresh MBF_RELAY_STATE correctly shows the pump ON.
    The fixup must NOT fire in this case — the relay bit should be trusted.
    """
    client = vistapool_modbus.VistaPoolModbusClient(config)

    class DummyResp:
        def __init__(self, regs, is_error=False):
            self.registers = regs
            self.isError = lambda: is_error

    fake_modbus = AsyncMock()
    fake_modbus.connected = True

    # --- First poll: full read, pump off everywhere ---
    reg01_off = [0] * 18
    reg01_off[14] = 0x0000  # MBF_RELAY_STATE — pump off
    reg01_off[16] = 0  # MBF_NOTIFICATION — no changes

    installer_block1 = [0] * 31
    installer_block1[10] = 2  # MBF_PAR_FILT_GPIO = 2
    installer_block1[25] = 0  # MBF_PAR_FILTRATION_STATE = 0 (off)

    fake_modbus.read_input_registers = AsyncMock(return_value=DummyResp(reg01_off))
    fake_modbus.read_holding_registers = AsyncMock(
        side_effect=[
            DummyResp([1, 3, 1280, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
            DummyResp([0] * 20),
            DummyResp([0, 0]),
            DummyResp([0] * 13),
            DummyResp([0] * 4),
            DummyResp(installer_block1),
            DummyResp([0] * 13),
            DummyResp([0] * 8),
            DummyResp([0] * 14),
            DummyResp([0] * 13),
        ]
    )
    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))
    result1 = await client._perform_read_all()
    assert result1["Filtration Pump"] is False

    # --- Second poll: partial read (no notification), pump now ON in relay ---
    # Simulate enough polls so this is NOT a full read
    client._polls_since_full_read = 1  # just after full read

    reg01_on = [0] * 18
    reg01_on[14] = 0x0002  # MBF_RELAY_STATE — bit 1 set (pump ON)
    reg01_on[16] = 0  # MBF_NOTIFICATION — no INSTALLER change

    fake_modbus.read_input_registers = AsyncMock(return_value=DummyResp(reg01_on))
    # No holding register reads expected (partial read, no notification)
    fake_modbus.read_holding_registers = AsyncMock(side_effect=[])

    result2 = await client._perform_read_all()

    # The relay bit is fresh and says pump ON. Cached MBF_PAR_FILTRATION_STATE
    # is stale (0). Fixup must NOT override → Filtration Pump stays True.
    assert result2["Filtration Pump"] is True, (
        "Fresh relay bit should not be overridden by stale cached MBF_PAR_FILTRATION_STATE"
    )
    assert result2["MBF_RELAY_STATE"] & 0x0002, (
        "MBF_RELAY_STATE bit 1 should remain set"
    )


@pytest.mark.asyncio
async def test_filtration_state_fixup_v8_07_firmware(config, monkeypatch):
    """Test that MBF_PAR_FILTRATION_STATE overrides MBF_RELAY_STATE bit 1 when they disagree.

    On firmware v8.07 (HIDRO-only, e.g. Oxilife), MBF_RELAY_STATE = 0x0700 with bit 1
    not set even when the pump runs. MBF_PAR_FILTRATION_STATE (0x0421) is authoritative.
    """
    client = vistapool_modbus.VistaPoolModbusClient(config)

    class DummyResp:
        def __init__(self, regs, is_error=False):
            self.registers = regs
            self.isError = lambda: is_error

    fake_modbus = AsyncMock()
    fake_modbus.connected = True

    # reg01 (input registers from 0x0100): MBF_RELAY_STATE at index 14 = 0x0700
    # (firmware v8.07 quirk: bits 8-10 set, bit 1 not set)
    reg01 = [0] * 18
    reg01[14] = 0x0700  # MBF_RELAY_STATE

    # installer block 1 (0x0408, 31 registers): MBF_PAR_FILTRATION_STATE at index 25 = 1
    installer_block1 = [0] * 31
    installer_block1[10] = 2  # MBF_PAR_FILT_GPIO = 2 (relay 2, bit 1)
    installer_block1[25] = 1  # MBF_PAR_FILTRATION_STATE = 1 (pump running)

    fake_modbus.read_holding_registers = AsyncMock(
        side_effect=[
            DummyResp([1, 3, 1280, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),  # rr00
            DummyResp([0] * 20),  # rr02
            DummyResp([0, 0]),  # rr02_hidro
            DummyResp([0] * 13),  # factory block 1 (0x0300)
            DummyResp([0] * 4),  # factory block 2 (0x0322)
            DummyResp(
                installer_block1
            ),  # installer block 1 (0x0408, 31) — has MBF_PAR_FILTRATION_STATE
            DummyResp([0] * 13),  # installer block 2 (0x0427)
            DummyResp([0] * 8),  # installer block 3 (0x04E8, FILTVALVE)
            DummyResp([0] * 14),  # rr05
            DummyResp([0] * 13),  # rr06
        ]
    )
    fake_modbus.read_input_registers = AsyncMock(return_value=DummyResp(reg01))

    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    result = await client._perform_read_all()

    # Fixup must have overridden MBF_RELAY_STATE bit 1 with the authoritative value
    assert result["Filtration Pump"] is True, (
        "Filtration Pump should be True based on MBF_PAR_FILTRATION_STATE=1"
    )
    assert result["MBF_RELAY_STATE"] & 0x0002, (
        "MBF_RELAY_STATE bit 1 should be patched so get_filtration_speed sees pump as running"
    )


@pytest.mark.asyncio
async def test_filtration_state_fixup_pump_off_agrees(config, monkeypatch):
    """Test that when MBF_RELAY_STATE and MBF_PAR_FILTRATION_STATE agree (both off), no fixup fires."""
    client = vistapool_modbus.VistaPoolModbusClient(config)

    class DummyResp:
        def __init__(self, regs, is_error=False):
            self.registers = regs
            self.isError = lambda: is_error

    fake_modbus = AsyncMock()
    fake_modbus.connected = True

    reg01 = [0] * 18
    reg01[14] = 0x0000  # MBF_RELAY_STATE — bit 1 not set (pump off)

    installer_block1 = [0] * 31
    installer_block1[10] = 2  # MBF_PAR_FILT_GPIO = 2 (relay 2, bit 1)
    installer_block1[25] = 0  # MBF_PAR_FILTRATION_STATE = 0 (pump off — agrees)

    fake_modbus.read_holding_registers = AsyncMock(
        side_effect=[
            DummyResp([1, 3, 1280, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
            DummyResp([0] * 20),
            DummyResp([0, 0]),
            DummyResp([0] * 13),
            DummyResp([0] * 4),
            DummyResp(installer_block1),
            DummyResp([0] * 13),
            DummyResp([0] * 8),
            DummyResp([0] * 14),
            DummyResp([0] * 13),
        ]
    )
    fake_modbus.read_input_registers = AsyncMock(return_value=DummyResp(reg01))

    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    result = await client._perform_read_all()

    assert result["Filtration Pump"] is False
    assert not (result["MBF_RELAY_STATE"] & 0x0002)


@pytest.mark.asyncio
async def test_filtration_state_fixup_relay_on_but_state_off(config, monkeypatch):
    """Test fixup when MBF_RELAY_STATE bit 1 is set but MBF_PAR_FILTRATION_STATE says off.

    Edge case: relay state claims pump is running but authoritative register says it's off.
    Fixup must clear bit 1 from MBF_RELAY_STATE and set Filtration Pump to False.
    """
    client = vistapool_modbus.VistaPoolModbusClient(config)

    class DummyResp:
        def __init__(self, regs, is_error=False):
            self.registers = regs
            self.isError = lambda: is_error

    fake_modbus = AsyncMock()
    fake_modbus.connected = True

    reg01 = [0] * 18
    reg01[14] = 0x0002  # MBF_RELAY_STATE — bit 1 set (relay claims pump on)

    installer_block1 = [0] * 31
    installer_block1[10] = 2  # MBF_PAR_FILT_GPIO = 2 (relay 2, bit 1)
    installer_block1[25] = 0  # MBF_PAR_FILTRATION_STATE = 0 (authoritative: pump off)

    fake_modbus.read_holding_registers = AsyncMock(
        side_effect=[
            DummyResp([1, 3, 1280, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
            DummyResp([0] * 20),
            DummyResp([0, 0]),
            DummyResp([0] * 13),
            DummyResp([0] * 4),
            DummyResp(installer_block1),
            DummyResp([0] * 13),
            DummyResp([0] * 8),
            DummyResp([0] * 14),
            DummyResp([0] * 13),
        ]
    )
    fake_modbus.read_input_registers = AsyncMock(return_value=DummyResp(reg01))

    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    result = await client._perform_read_all()

    assert result["Filtration Pump"] is False, (
        "Filtration Pump should be False based on MBF_PAR_FILTRATION_STATE=0"
    )
    assert not (result["MBF_RELAY_STATE"] & 0x0002), (
        "MBF_RELAY_STATE bit 1 should be cleared to match the authoritative register"
    )


@pytest.mark.asyncio
async def test_hydrolysis_detected_via_model_bit(config, monkeypatch):
    """Hydrolysis module detected is True when MBF_PAR_MODEL bit 1 (MBMSK_MODEL_HIDRO) is set."""
    client = vistapool_modbus.VistaPoolModbusClient(config)

    class DummyResp:
        def __init__(self, regs, is_error=False):
            self.registers = regs
            self.isError = lambda: is_error

    fake_modbus = AsyncMock()
    fake_modbus.connected = True

    reg01 = [0] * 18  # MBF_HIDRO_STATUS at index 13 = 0 (no CTRL_ACTIVE)

    factory_block1 = [0] * 13
    factory_block1[1] = 0x0002  # MBF_PAR_MODEL bit 1 set (MBMSK_MODEL_HIDRO)

    fake_modbus.read_holding_registers = AsyncMock(
        side_effect=[
            DummyResp([0] * 16),  # rr00
            DummyResp([0] * 20),  # rr02
            DummyResp([0, 0]),  # rr02_hidro
            DummyResp(factory_block1),  # factory block 1 (0x0300)
            DummyResp([0] * 4),  # factory block 2 (0x0322)
            DummyResp([0] * 31),  # installer block 1
            DummyResp([0] * 13),  # installer block 2
            DummyResp([0] * 8),  # installer block 3
            DummyResp([0] * 14),  # rr05
            DummyResp([0] * 16),  # rr06
        ]
    )
    fake_modbus.read_input_registers = AsyncMock(return_value=DummyResp(reg01))
    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    result = await client._perform_read_all()

    assert result["Hydrolysis module detected"] is True


@pytest.mark.asyncio
async def test_hydrolysis_detected_via_status_ctrl_active(config, monkeypatch):
    """Hydrolysis module detected is True when MBF_HIDRO_STATUS bit 6 (CTRL_ACTIVE) is set."""
    client = vistapool_modbus.VistaPoolModbusClient(config)

    class DummyResp:
        def __init__(self, regs, is_error=False):
            self.registers = regs
            self.isError = lambda: is_error

    fake_modbus = AsyncMock()
    fake_modbus.connected = True

    reg01 = [0] * 18
    reg01[13] = 0x0040  # MBF_HIDRO_STATUS bit 6 (CTRL_ACTIVE)

    factory_block1 = [0] * 13
    factory_block1[1] = 0x0000  # MBF_PAR_MODEL — no HIDRO bit

    fake_modbus.read_holding_registers = AsyncMock(
        side_effect=[
            DummyResp([0] * 16),  # rr00
            DummyResp([0] * 20),  # rr02
            DummyResp([0, 0]),  # rr02_hidro
            DummyResp(factory_block1),  # factory block 1 (0x0300)
            DummyResp([0] * 4),  # factory block 2 (0x0322)
            DummyResp([0] * 31),  # installer block 1
            DummyResp([0] * 13),  # installer block 2
            DummyResp([0] * 8),  # installer block 3
            DummyResp([0] * 14),  # rr05
            DummyResp([0] * 16),  # rr06
        ]
    )
    fake_modbus.read_input_registers = AsyncMock(return_value=DummyResp(reg01))
    monkeypatch.setattr(client, "get_client", AsyncMock(return_value=fake_modbus))

    result = await client._perform_read_all()

    assert result["Hydrolysis module detected"] is True
