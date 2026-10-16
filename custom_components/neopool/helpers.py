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


def _normalize_host(host: str) -> str:
    """Fold the host to lower case, matching ModbusTcpParams.

    ModbusTcpParams lower-cases the host it is given, so a TCP endpoint dedupes
    regardless of case. The socket:// device string an RTU/ASCII link builds has
    to be folded the same way, or Device.local and device.local would open two
    links to one gateway. An IPv6 scope id after a % is left untouched.
    """
    address, separator, scope = host.partition("%")
    return address.lower() + separator + scope


def build_modbus_params(
    data: Mapping[str, Any],
) -> ModbusTcpParams | ModbusSerialParams:
    """Build the shared-connection link parameters from config entry data.

    RTU/ASCII over a socket (an ESPHome stream-server gateway) is built as
    ModbusSerialParams, not ModbusTcpParams with a framer (deprecated); its baud
    rate is the modbus integration's canonical 115200 so a shared gateway
    compares equal. A missing CONF_TYPE predates the connection-type choice and
    reads as a network (TCP) entry.
    """
    if data.get(CONF_TYPE, TYPE_TCP) == TYPE_SERIAL:
        return ModbusSerialParams(
            device=data[CONF_DEVICE],
            baudrate=data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE),
            framer="rtu",
        )
    host = _normalize_host(data[CONF_HOST])
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
        baudrate=115200,
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
