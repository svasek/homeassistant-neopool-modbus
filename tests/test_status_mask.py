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

from custom_components.vistapool.const import is_valid_relay_gpio
from custom_components.vistapool.status_mask import (
    decode_hidro_status_bits,
    decode_ion_status_bits,
    decode_named_relay_states,
    decode_ph_rx_cl_cd_status_bits,
    decode_relay_state,
    decode_uv_lamp_state,
)


def test_decode_relay_state_basic():
    value = 0x042B
    result = decode_relay_state(value)
    assert result["AUX1"] is True
    assert result["AUX2"] is False
    assert "pH Acid Pump" not in result
    assert "Filtration Pump" not in result
    assert "Pool Light" not in result


def test_decode_relay_state_none():
    assert decode_relay_state(None) == {}


def test_decode_named_relay_states_basic():
    relay_state = 0x042B  # bits 0,1,3,5,10 set
    gpio_map = {
        "pH Acid Pump": 1,  # bit 0 -> True
        "Filtration Pump": 2,  # bit 1 -> True
        "Pool Light": 3,  # bit 2 -> False
    }
    result = decode_named_relay_states(relay_state, gpio_map)
    assert result["pH Acid Pump"] is True
    assert result["Filtration Pump"] is True
    assert result["Pool Light"] is False


def test_decode_named_relay_states_invalid_gpio():
    relay_state = 0xFFFF
    gpio_map = {
        "pH Acid Pump": 0,  # invalid -> None
        "Filtration Pump": 8,  # out of range -> None
        "Pool Light": 3,  # valid -> included
    }
    result = decode_named_relay_states(relay_state, gpio_map)
    assert result["pH Acid Pump"] is None
    assert result["Filtration Pump"] is None
    assert result["Pool Light"] is True


def test_decode_named_relay_states_none():
    assert decode_named_relay_states(None, {"Test": 1}) == {}


def test_decode_ph_rx_cl_cd_status_bits_basic():
    # flow sensor problem (bit 3), acid pump active (bit 11), control module (bit 13)
    status = 0x2808
    unit = "pH"
    result = decode_ph_rx_cl_cd_status_bits(status, unit)
    assert result["pH flow sensor problem"] is True
    assert result["pH regulation out of range"] is False
    assert result["pH module control status"] is False
    assert result["pH acid pump active"] is True
    assert result["pH pump active"] is False
    assert result["pH control module"] is True


def test_decode_ph_rx_cl_cd_status_bits_none():
    assert decode_ph_rx_cl_cd_status_bits(None, "pH") == {}


def test_decode_ph_rx_cl_cd_status_bits_no_acid_for_non_ph():
    """Bit 11 (acid pump) is only emitted for pH, not for other units."""
    status = 0x2808  # bit 11 set
    result = decode_ph_rx_cl_cd_status_bits(status, "Redox")
    assert "Redox acid pump active" not in result
    assert "Redox pump active" in result


def test_decode_ph_rx_cl_cd_status_bits_regulation_out_of_range():
    """Bit 7 (0x0080) indicates regulation out of range."""
    status = 0xE584  # bit 7 set, alarm 4, bits 13-15 set
    result = decode_ph_rx_cl_cd_status_bits(status, "pH")
    assert result["pH regulation out of range"] is True
    assert result["pH control module"] is True
    assert result["pH measurement active"] is True
    assert result["pH measurement module detected"] is True

    # Without bit 7
    status_no_bit7 = 0xE504  # same but bit 7 clear
    result2 = decode_ph_rx_cl_cd_status_bits(status_no_bit7, "pH")
    assert result2["pH regulation out of range"] is False


def test_decode_ion_status_bits_basic():
    # ION On Target, ION in Pol2
    status = 0x4001
    result = decode_ion_status_bits(status)
    assert result["ION On Target"] is True
    assert result["ION in Pol2"] is True
    assert result["ION in dead time"] is False


def test_decode_ion_status_bits_none():
    assert decode_ion_status_bits(None) == {}


def test_decode_hidro_status_bits_basic():
    # HIDRO On Target, HIDRO Module active, HIDRO in Pol1
    status = 0x2021
    result = decode_hidro_status_bits(status)
    assert result["HIDRO On Target"] is True
    assert result["HIDRO Module active"] is True
    assert result["HIDRO in Pol1"] is True
    assert result["Pool Cover"] is False


def test_decode_hidro_status_bits_none():
    assert decode_hidro_status_bits(None) == {}


# --- is_valid_relay_gpio tests ---


def test_is_valid_relay_gpio_valid():
    for gpio in range(1, 8):
        assert is_valid_relay_gpio(gpio) is True


def test_is_valid_relay_gpio_invalid():
    for gpio in (0, -1, 8, 16, 255):
        assert is_valid_relay_gpio(gpio) is False


# --- decode_uv_lamp_state tests ---


def test_decode_uv_lamp_state_on():
    """UV Lamp is ON when the bit at (gpio - 1) is set."""
    assert decode_uv_lamp_state(0x0004, 3) == {"UV Lamp": True}


def test_decode_uv_lamp_state_off():
    """UV Lamp is OFF when the bit at (gpio - 1) is clear."""
    assert decode_uv_lamp_state(0x0000, 3) == {"UV Lamp": False}


def test_decode_uv_lamp_state_gpio_boundaries():
    """GPIO 1 checks bit 0, GPIO 7 checks bit 6."""
    assert decode_uv_lamp_state(0x0001, 1)["UV Lamp"] is True
    assert decode_uv_lamp_state(0x0040, 7)["UV Lamp"] is True


def test_decode_uv_lamp_state_none_relay():
    """Returns empty dict when relay_state is None."""
    assert decode_uv_lamp_state(None, 3) == {}


def test_decode_uv_lamp_state_invalid_gpio():
    """Returns empty dict when gpio is out of range."""
    assert decode_uv_lamp_state(0xFFFF, 0) == {}
    assert decode_uv_lamp_state(0xFFFF, 8) == {}
    assert decode_uv_lamp_state(0xFFFF, 255) == {}
