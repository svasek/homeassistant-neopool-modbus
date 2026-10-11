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

"""Helper functions for the NeoPool integration."""

from collections.abc import Mapping
import datetime
from typing import Any, Literal

from modbus_connection import ModbusSerialParams, ModbusTcpParams
from neopool_modbus.decoders import (
    encode_device_time,
    parse_register_int as _lib_parse_register_int,
)
from neopool_modbus.registers import framer_to_socket_name

from homeassistant.const import CONF_DEVICE, CONF_HOST, CONF_PORT, CONF_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
import homeassistant.util.dt as dt_util

from .const import (
    CONF_BAUDRATE,
    CONF_MODBUS_FRAMER,
    DEFAULT_BAUDRATE,
    DEFAULT_PORT,
    DOMAIN,
    TYPE_SERIAL,
    TYPE_TCP,
)


def build_modbus_params(
    data: Mapping[str, Any],
) -> ModbusTcpParams | ModbusSerialParams:
    """Build the shared-connection link parameters from config entry data.

    A direct serial link uses ``ModbusSerialParams`` on the device path; NeoPool
    RS485 is RTU-framed at 8N1 (the library default), so only the baud rate is
    carried. The baud rate sets the serial inter-frame timing; 19200 is NeoPool's
    RS485 rate, giving the spec's 3.5-character gap (~2 ms) for that line.

    Otherwise the link is reached over the network. A Modbus TCP link is always
    MBAP-framed, so it uses ``ModbusTcpParams`` with the framer omitted (passing
    it is deprecated). RTU/ASCII framing over a socket (an ESPHome stream-server
    gateway) is a serial link reached through a ``socket://`` device, so it uses
    ``ModbusSerialParams`` directly; that is what the modbus integration would
    canonicalise an RTU ``ModbusTcpParams`` to anyway, built here to avoid the
    deprecation warning.

    Entries predating the connection-type choice carry no ``CONF_TYPE``; they are
    all network entries, so a missing type reads as TCP.
    """
    if data.get(CONF_TYPE, TYPE_TCP) == TYPE_SERIAL:
        return ModbusSerialParams(
            device=data[CONF_DEVICE],
            baudrate=data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE),
            framer="rtu",
        )
    host = data[CONF_HOST]
    port = data.get(CONF_PORT, DEFAULT_PORT)
    framer = framer_to_socket_name(data.get(CONF_MODBUS_FRAMER, "tcp"))
    if framer == "socket":
        return ModbusTcpParams(host=host, port=port)
    # An IPv6 literal must be bracketed, or its colons read as the port separator.
    device_host = f"[{host}]" if ":" in host else host
    serial_framer: Literal["rtu", "ascii"] = "ascii" if framer == "ascii" else "rtu"
    return ModbusSerialParams(
        device=f"socket://{device_host}:{port}",
        framer=serial_framer,
        baudrate=DEFAULT_BAUDRATE,
    )


def prepare_device_time(hass: HomeAssistant) -> int:
    """Return the unix timestamp the device should display as local wall-clock."""
    tz = dt_util.get_time_zone(hass.config.time_zone) or datetime.UTC
    return encode_device_time(dt_util.now(tz))


# CUSTOM-ONLY START, device time-drift helpers are HACS-only.
def is_device_time_out_of_sync(
    data: dict[str, Any],
    hass: HomeAssistant,
    threshold_seconds: int = 300,
) -> bool:
    """Return whether the device/HA wall-clock drift exceeds threshold_seconds."""
    device_ts: int | None = data.get("MBF_PAR_TIME")
    if device_ts is None:
        return False
    return abs(device_ts - prepare_device_time(hass)) > threshold_seconds


# CUSTOM-ONLY END
def parse_register_int(raw: int | str, name: str) -> int:
    """Parse a Modbus register value, raising a translated ServiceValidationError."""
    try:
        return _lib_parse_register_int(raw)
    except ValueError as err:
        msg = str(err)
        if msg.startswith("register value out of range"):
            key = "register_out_of_range"
        elif msg.startswith("register value must not be a float"):
            key = "invalid_register_float"
        else:
            # bool / unparsable string / unsupported type all collapse to
            # the generic "invalid type" translation.
            key = "invalid_register_type"
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key=key,
            translation_placeholders={"name": name, "value": str(raw)},
        ) from err
