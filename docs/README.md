# NeoPool documentation

Supplementary hardware and connection material for the
[NeoPool Modbus integration](../README.md). The main project README covers
installation and configuration; the files here help you get the controller
physically connected.

## Choosing a connection

The integration talks to the NeoPool controller over Modbus RTU on the
controller's RS-485 port. There are two ways to bridge that RS-485 port to
Home Assistant.

- **Modbus TCP gateway** (RS-485 to Ethernet or USB converter). The classic
  path: a converter box sits on the bus and exposes it as a Modbus TCP port.
  See the [Modbus connection guide](modbus-connection-guide.md) for wiring,
  pinout, and gateway setup.
- **ESPHome serial proxy** (ESP32 plus an RS-485 adapter). An ESP32 exposes the
  serial port to Home Assistant over Wi-Fi through the ESPHome native API, so no
  separate gateway box is needed. A good migration target if you already run the
  controller through a Tasmota ESP. See
  [esphome-proxy-neopool-rs485.yaml](esphome-proxy-neopool-rs485.yaml) for a
  ready to flash configuration.

## ESPHome serial proxy setup

The [esphome-proxy-neopool-rs485.yaml](esphome-proxy-neopool-rs485.yaml) file is
a complete ESPHome configuration for an M5Stack Atom with a Tail485 RS-485
adapter. Its header comment has the full wiring table and notes; the steps below
are the short version.

### Requirements

- Home Assistant 2026.5 or newer (serial proxy support)
- ESPHome 2026.5 or newer (the `serial_proxy` component)
- M5Stack Atom Lite S3 (tested) or Atom Lite
- M5Stack Tail485 (SKU T002) mounted on the Atom

The `serial_proxy` component is still experimental in ESPHome, so re-check the
connection after upgrading ESPHome or Home Assistant.

### Steps

1. Create a `secrets.yaml` with `wifi_ssid`, `wifi_password`, `api_enc_key`, and
   `ota_password`. Generate the API key with `openssl rand -base64 32`.
2. If you use an Atom Lite (not the S3), change the board and the UART pins near
   the top of the YAML (the header comment lists both pin sets).
3. Flash the device, the first time over USB.
4. Adopt it in Home Assistant under **Settings** > **Devices & services** >
   **ESPHome**.
5. Add the NeoPool integration, choose the serial connection, and select the
   **NeoPool RS485** port.

The serial parameters in the YAML (19200 baud, 8N1) match the NeoPool Modbus
defaults.

### Troubleshooting

If the port appears but Modbus times out, swap `tx_pin` and `rx_pin`, then swap
the RS-485 A/B wires. For a byte-level trace, enable the UART `debug` block in
the YAML and watch the ESPHome log. The file's troubleshooting section has the
details.

## Files in this folder

- [modbus-connection-guide.md](modbus-connection-guide.md) - Modbus TCP gateway
  wiring and setup.
- [esphome-proxy-neopool-rs485.yaml](esphome-proxy-neopool-rs485.yaml) - ESPHome
  serial proxy configuration.
- `images/` - photos and screenshots used by the guides.
