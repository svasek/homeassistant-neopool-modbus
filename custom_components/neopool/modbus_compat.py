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

"""Compatibility helpers for pymodbus 3.9.x (slave=) and 3.10+ (device_id=)."""

from __future__ import annotations

import inspect
from typing import Any, Awaitable, Callable, Dict


def address_kwargs(bound_method: Callable[..., Any], device_id: int) -> Dict[str, int]:
    """Return the correct keyword for addressing a Modbus unit/device.

    Supports only two documented variants:
      - pymodbus >= 3.10 -> 'device_id'
      - pymodbus <= 3.9  -> 'slave'

    We inspect the bound method's signature to decide which keyword is supported.
    If inspection fails, default to the new API.
    """
    try:
        sig = getattr(bound_method, "__signature__", None) or inspect.signature(
            bound_method
        )
        params = sig.parameters
    except Exception:
        return {"device_id": device_id}

    return {"device_id": device_id} if "device_id" in params else {"slave": device_id}


### Async variant of the callable wrapper
async def modbus_acall(
    bound_method: Callable[..., Awaitable[Any]], device_id: int, /, **kwargs: Any
) -> Any:
    """Await a Modbus client coroutine with the correct addressing kwarg injected.

    Any addressing keyword in kwargs (e.g., 'slave' or 'device_id') will be overridden by the correct one for the method.

    Example:
        m = client.async_read_holding_registers
        res = await acall(m, dev_id, address=0x200, count=2)
    """
    return await bound_method(**kwargs, **address_kwargs(bound_method, device_id))


### Sync variant of the callable wrapper
def modbus_scall(
    bound_method: Callable[..., Any], device_id: int, /, **kwargs: Any
) -> Any:
    """Call a sync Modbus client method with the correct addressing kwarg injected.

    Any addressing keyword in kwargs (e.g., 'slave' or 'device_id') will be overridden by the correct one for the method.

    Example:
        m = client.read_holding_registers
        res = scall(m, dev_id, address=0x200, count=2)
    """
    return bound_method(**kwargs, **address_kwargs(bound_method, device_id))
