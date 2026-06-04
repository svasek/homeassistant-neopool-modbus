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

"""
VistaPool Integration for Home Assistant - Status Mask Decoders Module

Mask decoders for VistaPool / NeoPool integration, based on xsns_83_neopool.ino
WARNING: DO NOT change names of this keys, they are used in the code !!!
"""

# TODO: There should be also name for each relay available in the settings.
#     Each relay name has 5 register ASCIIZ string with up to 10 characters.
#     (MBF_PAR_UICFG_MACH_NAME_AUX1, MBF_PAR_UICFG_MACH_NAME_AUX2, MBF_PAR_UICFG_MACH_NAME_AUX3, MBF_PAR_UICFG_MACH_NAME_AUX4)

from .const import is_valid_relay_gpio


def decode_uv_lamp_state(relay_state: int | None, uv_relay_gpio: int) -> dict:
    """Decode the UV Lamp relay bit from MBF_RELAY_STATE.

    Returns {"UV Lamp": bool} when relay_state and uv_relay_gpio are valid,
    otherwise returns an empty dict.
    """
    if relay_state is None or not is_valid_relay_gpio(uv_relay_gpio):
        return {}
    return {"UV Lamp": bool((relay_state >> (uv_relay_gpio - 1)) & 1)}


def decode_relay_state(value: int | None) -> dict:
    """Decode AUX1–4 relay state bits from MBF_RELAY_STATE.

    Only AUX relays are decoded here (always at fixed bit positions 3–6).
    Named functional relays (Filtration, Light, pH Acid Pump, …) use dynamic
    GPIO mapping via decode_named_relay_states().
    Speed bits (8–10) are consumed directly by get_filtration_speed().
    """
    # Bits 0-6: relay outputs 1-7 (function assignment is configurable)
    # Bits 3-6: AUX1-AUX4 (always at fixed positions)
    if value is None:
        return {}
    return {
        "AUX1": bool(value & 0x0008),
        "AUX2": bool(value & 0x0010),
        "AUX3": bool(value & 0x0020),
        "AUX4": bool(value & 0x0040),
    }


def decode_named_relay_states(
    relay_state: int | None, gpio_map: dict[str, int]
) -> dict:
    """Decode named relay states using dynamic GPIO mapping.

    Each entry in *gpio_map* is ``{"Entity Name": gpio_number}`` where
    *gpio_number* is a 1-based relay index read from a ``MBF_PAR_*_RELAY_GPIO``
    register.  A gpio_number of 0 means "not assigned"; the key is set to
    ``None`` so any stale cached value is explicitly cleared.
    """
    if relay_state is None:
        return {}
    result: dict[str, bool | None] = {}
    for name, gpio in gpio_map.items():
        if is_valid_relay_gpio(gpio):
            result[name] = bool((relay_state >> (gpio - 1)) & 1)
        else:
            result[name] = None
    return result


def decode_ph_rx_cl_cd_status_bits(status: int | None, unit: str) -> dict:
    """Decode the status bits for pH, Redox, Chlorine, and Conductivity sensors."""
    # Status bits are 16 bits, where each bit represents a status flag
    # Bit 3:  Flow sensor problem
    # Bit 10: Module control status (flow detection control)
    # Bit 11: Acid pump active (pH only; depends on MBF_PAR_PH_ACID_RELAY_GPIO)
    # Bit 12: Pump active (base pump for pH; dosing pump for Rx/CL/CD)
    # Bit 13: Control module (active regulation)
    # Bit 14: Measurement active
    # Bit 15: Measurement module detected
    if status is None:
        return {}
    result = {
        f"{unit} flow sensor problem": bool(status & 0x0008),
        f"{unit} module control status": bool(status & 0x0400),
        f"{unit} pump active": bool(status & 0x1000),
        f"{unit} control module": bool(status & 0x2000),
        f"{unit} measurement active": bool(status & 0x4000),
        f"{unit} measurement module detected": bool(status & 0x8000),
    }
    # Bit 11 is the acid pump — only meaningful for the pH module
    if unit == "pH":
        result[f"{unit} acid pump active"] = bool(status & 0x0800)
    return result


def decode_ion_status_bits(status: int | None) -> dict:
    """Decode the status bits for ION sensor."""
    # Status bits are 16 bits, where each bit represents a status flag
    # Bit 0: ION On Target
    # Bit 1: ION Low Flow
    # Bit 2: ION Reserved
    # Bit 3: ION Program time exceeded
    # Bit 12: ION in dead time
    # Bit 13: ION in Pol1
    # Bit 14: ION in Pol2
    # Bit 15: ION measurement module detected
    # Note: ION measurement module is always detected if ION sensor is present
    if status is None:
        return {}
    return {
        "ION On Target": bool(status & 0x0001),
        "ION Low Flow": bool(status & 0x0002),
        "ION Reserved": bool(status & 0x0004),
        "ION Program time exceeded": bool(status & 0x0008),
        "ION in dead time": bool(status & 0x1000),
        "ION in Pol1": bool(status & 0x2000),
        "ION in Pol2": bool(status & 0x4000),
    }


def decode_hidro_status_bits(status: int | None) -> dict:
    """Decode the status bits for HIDRO sensor."""
    # Status bits are 16 bits, where each bit represents a status flag
    # Bit 0: HIDRO On Target
    # Bit 1: HIDRO Low Flow
    # Bit 2: HIDRO Reserved
    # Bit 3: HIDRO Cell Flow FL1 (if present)
    # Bit 4: Pool Cover (cover input active)
    # Bit 5: HIDRO Module active
    # Bit 6: HIDRO Module regulated
    # Bit 7: HIDRO Activated by the RX module
    # Bit 8: HIDRO Chlorine shock mode
    # Bit 9: HIDRO Chlorine flow indicator FL2 (if present)
    # Bit 10: HIDRO Activated by the CL module
    # Bit 12: HIDRO in dead time
    # Bit 13: HIDRO in Pol1
    # Bit 14: HIDRO in Pol2
    # Bit 15: HIDRO measurement module detected
    # Note: HIDRO measurement module is always detected if HIDRO sensor is present
    if status is None:
        return {}
    return {
        "HIDRO On Target": bool(status & 0x0001),
        "HIDRO Low Flow": bool(status & 0x0002),
        "HIDRO Reserved": bool(status & 0x0004),
        "HIDRO Cell Flow FL1": bool(status & 0x0008),  # if present
        "Pool Cover": bool(status & 0x0010),
        "HIDRO Module active": bool(status & 0x0020),
        "HIDRO Module regulated": bool(status & 0x0040),
        "HIDRO Activated by the RX module": bool(status & 0x0080),
        "HIDRO Chlorine shock mode": bool(status & 0x0100),
        "HIDRO Chlorine flow indicator FL2": bool(status & 0x0200),  # if present
        "HIDRO Activated by the CL module": bool(status & 0x0400),
        "HIDRO in dead time": bool(status & 0x1000),
        "HIDRO in Pol1": bool(status & 0x2000),
        "HIDRO in Pol2": bool(status & 0x4000),
    }
