# VistaPool Modbus Integration for Home Assistant

- Easily connect your **NeoPool**-based pool controller to Home Assistant via Modbus TCP.
- NeoPool is a control system originally developed by **Sugar Valley** (acquired by **Hayward** in 2016), available under many brand names and in multiple device variants.
- Full local control, real-time sensors, timers, relays, automation support, and more.

[![Release](https://github.com/svasek/homeassistant-vistapool-modbus/actions/workflows/release.yaml/badge.svg)](https://github.com/svasek/homeassistant-vistapool-modbus/actions/workflows/release.yaml)
[![Hassfest](https://github.com/svasek/homeassistant-vistapool-modbus/actions/workflows/hassfest.yaml/badge.svg)](https://github.com/svasek/homeassistant-vistapool-modbus/actions/workflows/hassfest.yaml)
[![HACS](https://github.com/svasek/homeassistant-vistapool-modbus/actions/workflows/hacs.yaml/badge.svg)](https://github.com/svasek/homeassistant-vistapool-modbus/actions/workflows/hacs.yaml)
[![CodeQL](https://github.com/svasek/homeassistant-vistapool-modbus/actions/workflows/github-code-scanning/codeql/badge.svg)](https://github.com/svasek/homeassistant-vistapool-modbus/actions/workflows/github-code-scanning/codeql)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![codecov](https://codecov.io/github/svasek/homeassistant-vistapool-modbus/graph/badge.svg?token=44MRDJIHJ9)](https://app.codecov.io/github/svasek/homeassistant-vistapool-modbus?displayType=list)

[![Conventional Branch](https://img.shields.io/badge/Conventional%20Branch-Spec-6192c3)](https://conventional-branch.github.io/)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-%23FE5196?logo=conventionalcommits&logoColor=white)](https://www.conventionalcommits.org/)
[![Gitmoji](https://img.shields.io/badge/gitmoji-%20%F0%9F%98%9C%20%F0%9F%98%8D-FFDD67.svg)](https://gitmoji.dev/specification)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/svasek/homeassistant-vistapool-modbus/2-getting-started)
[![Sponsor me](https://img.shields.io/badge/sponsor-❤-brightgreen?style=flat)](https://github.com/sponsors/svasek)
[![Ko-fi](https://img.shields.io/badge/ko--fi-support-29abe0?style=flat&logo=ko-fi)](https://ko-fi.com/svasek)

> **This integration is available via [HACS](https://hacs.xyz/)**

**Supported device models** (Sugar Valley / Hayward product lines):  
Hidrolife • Aquascenic • Oxilife • Bionet • Hidroniser • UVScenic • Station • Aquarite

**Distributed by** (vendors selling NeoPool-based hardware):  
Hayward • Brilix (Albixon) • Bayrol • Certikin • Poolstar • GrupAquadirect • Pentair • ProducPool • Pool Technologie • Kripsol

---

## About NeoPool Controllers

The hardware supported by this integration uses the **NeoPool control system**, originally developed by the Spanish company **Sugar Valley** and acquired by **Hayward** in 2016. The same system is sold under many brand names worldwide (see supported list above).

The Modbus protocol implemented here is described in the official _"NeoPool Control System MODBUS Register description"_ documentation by Sugar Valley.

> **Note:** _VistaPool_ is the name of Hayward's mobile/web app for cloud-based pool management.
> This integration works entirely **locally via Modbus** — it does not require or use the VistaPool app or any cloud service.

---

## What does this integration do?

- Provides **full local control** of supported pool controllers over Modbus TCP.
- Adds real-time sensors, numbers, switches, selects, and buttons for all available features.
- Allows timer/relay/aux configuration, automation and Home Assistant UI integration.
- Supports multiple pools or hubs, each as a separate integration.

---

## Support

If you find this integration useful, consider supporting its development:

- ⭐️ Give this repository a star!
- 🛠️ Contribute code or report issues.
- 💸 [Become a GitHub Sponsor](https://github.com/sponsors/svasek)
- ☕ [Support me on Ko-fi](https://ko-fi.com/svasek)

---

## Hardware Connection

- **Gateway:** Any Modbus TCP gateway (e.g. [USR-DR164](https://www.pusr.com/products/Serial-to-Dual-Band-WiFi-Converter.html))
- **Connector:** Standard **2.54 mm** 5-pin PCB female connector
- **Settings:** 19200 baud, 1 stop bit, no parity
- **Protocol:** Modbus RTU
- **See the [Modbus Connection Guide](docs/modbus-connection-guide.md)** for more info and images.

### Plug Connector

- **RS485 port**: Use the `WIFI` or `EXTERNAL` connector (do **not** use `DISPLAY`, unless the internal LCD is disconnected).
- **Pinout** (top to bottom):

  ```
       ___
    1 |*  |– +12V (from internal power supply)
    2 |*  |– NC (not connected)
    3 |*  |– Modbus A+
    4 |*  |– Modbus B-
    5 |*__|– GND
  ```

- **The NeoPool device acts as a Modbus _server_ (slave), this integration is a Modbus _client_ (master).**
- **Only one Modbus client can be connected to a Modbus connector with the same label**. It is not possible to operate multiple clients on connectors that share the same name.
- **Modbus connectors with different labels represent independent physical interfaces.** Data traffic on one connector is **not visible** on others.
- The **DISPLAY** connector is present **twice** and is usually used by the built-in LCD.
  **Do not use it for this integration if the LCD is connected!**

---

## Features

- **Reliable single Modbus TCP connection per device/hub** (improves stability, avoids connection issues).
- **Multi-hub support**: Add multiple VistaPool devices, each with a custom prefix (used in entity IDs).
- **Sensors**:
  pH, Redox (ORP), Salt, Conductivity, Water Temperature, Ionization, Hydrolysis Intensity/Voltage, Device Time, Status/Alarm bits, Filtration speed _(if supported)_, Backwash remaining time _(if Besgo automatic filter valve is configured)_.
- **Numbers**:
  Setpoints for pH, Redox, Chlorine, Temperature, Hydrolysis production, Hydrolysis cover reduction % _(if hydrolysis module present + cover sensor enabled)_, Hydrolysis shutdown temperature threshold _(if hydrolysis module + temperature sensor + cover sensor enabled)_.
- **Switches**:
  Manual filtration, relays (_Light & AUX1–AUX4_, can be enabled in Options), automatic time sync to Home Assistant (default: disabled), **winter mode** (suspends Modbus communication while keeping all entities registered in Home Assistant), Hydrolysis cover reduction enable _(if hydrolysis module present + cover sensor enabled)_, Hydrolysis temperature shutdown enable _(if hydrolysis module + temperature sensor + cover sensor enabled)_.
- **Selects**:
  Filtration mode (Manual, Auto, Heating, Smart, Intelligent, **Backwash** _(auto-enabled if Besgo valve configured)_), timers for automatic filtration, filtration speed _(if supported)_, boost control _(if Hydro/Electrolysis module is present)_, pH pump activation delay, **Backwash Repeat Interval** _(if Besgo valve configured)_, **Backwash Valve Mode** _(if Besgo valve configured)_.
- **Buttons**:
  Manual time sync, reset alarm/error states, **Start Backwash** _(only if Besgo automatic filter valve is configured on the device)_.

---

## Installation

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=svasek&repository=homeassistant-vistapool-modbus&category=Integration)

### [HACS](https://hacs.xyz/) (recommended)

1. Open **HACS** in Home Assistant.
2. Go to **Integrations** and search for **VistaPool Modbus Integration** (no need to add a custom repository, this integration is included in the HACS default list).
3. Install **VistaPool Modbus Integration**.
4. Restart Home Assistant.

### Manual

1. Download or clone this repository.
2. Copy the `custom_components/vistapool` folder to your `/config/custom_components` directory.
3. Restart Home Assistant.

## Setup and Configuration

After installing the integration via HACS and restarting Home Assistant:

### 1. Add Your Pool to Home Assistant

You can use the button below to start configuration:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=vistapool)

Or add manually:

- Go to **Settings → Devices & Services**.
- Click **Add Integration**.
- Search for and select **VistaPool Modbus Integration**.

### 2. Enter Connection Details

- **Name**: Custom identifier for your pool.  
  _This will be used as a prefix in all entity IDs, with spaces replaced by underscores and converted to lowercase_  
  _(e.g., entering “Pool West” becomes `pool_west`, and your entity will be `sensor.pool_west_measure_ph`)_.
- **Host**: IP address of your Modbus TCP gateway
- **Port**: _(default: 502)_
- **Slave ID**: _(default: 1)_
- **Scan interval**: _(default: 30s)_

### 3. Adjust Integration Options (Optional)

After initial setup, you can fine-tune the integration:

- **Scan interval** (default: 30s)
- **Timer resolution** (default: 15m)
- **Enable/disable relays** (Light and AUX1–AUX4 are default: disabled)
- **Enable/disable cover sensor** (pool cover input — enables cover-related entities; default: disabled)
- **Enable/disable filtration timers** (filtration1, filtration2, filtration3)
- **Unlock advanced features** (see [below](#advanced-options-unlocking-backwash-mode))

Go to **Settings → Devices & Services → VistaPool Modbus Integration → Configure**  
to adjust options at any time.

---

### Winter Mode

If your pool controller is **physically disconnected during winter** (e.g. drained and stored), you can enable **Winter Mode** instead of disabling the whole integration.

- Flip the **`switch.<name>_winter_mode`** switch to ON.
- The integration stops all Modbus polling — no connection attempts, no error logs.
- All entities remain registered in Home Assistant. Control entities (switches, lights, buttons, numbers, selects) immediately become **unavailable** (greyed-out) and cannot be controlled until winter mode is disabled. Sensors and binary sensors stay available but show **unknown** values.
- Automations referencing these entities continue to exist without errors.
- When the pool season starts again, flip the switch back OFF — communication resumes and values update at the next poll cycle.

> The winter mode state is persisted across Home Assistant restarts, so you only need to set it once.
> Winter mode can also be toggled via automations (e.g. turn on every 1st November, turn off every 1st April).

---

### Advanced Options: Unlocking “Backwash” Mode

The "Backwash" option in the **filtration mode select** is hidden by default, as its remote use can be risky and is intended only for advanced users.

To enable it:

1. Go to **Settings → Devices & Services → VistaPool Modbus Integration → Configure**.
2. In the options dialog, find the field **Unlock advanced options**.
3. Enter the code: `<device_prefix><current_year>`

- Example: If your pool's prefix is `vistapool` and the year is 2025, enter `vistapool2025`.
- The prefix is the same as in your entity IDs (e.g., `switch.vistapool_light`).

4. Submit the form. The advanced settings page will open, allowing you to enable "Backwash" mode.

> **⚠️ WARNING:**
> Enabling "Backwash" exposes this function in filtration mode selection.
> **Improper use may damage your filtration system! Only activate if you fully understand the risks.**

### Start Backwash Button (Besgo Automatic Filter Valve)

If your device is configured with a **Besgo automatic filter valve** (`MBF_PAR_FILTVALVE_ENABLE = 1`), a dedicated **`Start Backwash`** button (`button.<name>_backwash`) is automatically available — no unlock code required.

- Pressing it sets the filtration mode to backwash (mode 13) and the controller opens the Besgo valve, then runs the cleaning cycle automatically.
- When switching **from manual filtration mode to backwash** on a device with a Besgo valve, the pump is intentionally **not** stopped before the mode change — this ensures the valve opens correctly under pressure.
- On devices **without** a Besgo valve (manual multi-way valve), the pump IS stopped first so the user can safely rotate the valve before the backwash cycle begins.
- The **Backwash** option in the filtration mode select is **automatically shown** when a Besgo valve is detected (no unlock code needed).

Additional Besgo-only entities are created automatically when `MBF_PAR_FILTVALVE_ENABLE = 1`:

| Entity                                   | Description                                                 |
| ---------------------------------------- | ----------------------------------------------------------- |
| `sensor.<name>_filtvalve_remaining`      | Remaining time (s) of the current backwash cycle            |
| `select.<name>_filtvalve_period_minutes` | How often automatic backwash is triggered (1 day – 4 weeks) |
| `select.<name>_filtvalve_mode`           | Valve timer mode: Automatic / Always On / Always Off        |

> **⚠️ WARNING:**
> Always verify that your filtration system is correctly set up before triggering a backwash remotely.
> **Improper use may damage your filtration system!**

---

## Example Entities

Entities are lowercased and prefixed by your custom name, e.g. `sensor.pool1_filt_mode`:

- **Sensors**:
  `sensor.<name>_measure_ph`, `sensor.<name>_measure_temperature`, `sensor.<name>_filt_mode`,
  `sensor.<name>_filtration_speed` _(if supported)_,
  `sensor.<name>_filtvalve_remaining` _(if Besgo valve configured)_
- **Numbers**:
  `number.<name>_hidro`, `number.<name>_ph1`,
  `number.<name>_heating_temp` _(if supported)_,
  `number.<name>_hidro_cover_reduction`, `number.<name>_hidro_shutdown_temperature` _(if supported + cover sensor enabled in Options)_
- **Switches**:
  `switch.<name>_winter_mode`,
  `switch.<name>_filt_manual_state`, `switch.<name>_time_auto_sync`,
  `switch.<name>_light`, `switch.<name>_aux1`-`switch.<name>_aux4` _(if enabled)_,
  `switch.<name>_hidro_cover_enable`, `switch.<name>_hidro_temp_shutdown` _(if supported + cover sensor enabled in Options)_
- **Selects**:
  `select.<name>_filt_mode`, `select.<name>_filtration1_start`, `select.<name>_filtration1_stop`,
  `select.<name>_filtration_speed` _(if supported)_,
  `select.<name>_cell_boost` _(if supported)_,
  `select.<name>_relay_activation_delay`,
  `select.<name>_filtvalve_period_minutes`, `select.<name>_filtvalve_mode` _(if Besgo valve configured)_
- **Buttons**:
  `button.<name>_sync_time`, `button.<name>_escape`,
  `button.<name>_backwash` _(if Besgo automatic filter valve is configured)_

---

## Special Notes

- **Only enabled timers and relays (per Options) are shown in Home Assistant.**
- **Winter Mode:** Suspends all Modbus polling while keeping entities registered in Home Assistant (control entities become unavailable, sensors show unknown values). See [Winter Mode](#winter-mode) above.
- **Timer resolution:** Can be set (in minutes) in integration Options.
- **Entities cache last value** if there is a Modbus communication problem.
- **Backwash (filtration mode select):** Hidden by default; unlock via advanced options. See above for details.
- **Backwash button:** Automatically available when a Besgo automatic filter valve is configured on the device. See above for details.
- **Besgo valve entities** (`sensor filtvalve_remaining`, `select filtvalve_period_minutes`, `select filtvalve_mode`): Only created when Besgo valve is detected (`MBF_PAR_FILTVALVE_ENABLE = 1`).
- **Reload on options change:** Integration is reloaded automatically on option changes.
- **Filtration speed sensor/control:** Only available for variable-speed pump models.
- **Boost control (select):** Only if Hydro/Electrolysis module is present.
- **Reset Alarm button:** Allows clearing of error and alarm states from HA.

---

## Based On

- [Tasmota NeoPool driver](https://github.com/arendst/Tasmota/blob/master/tasmota/tasmota_xsns_sensor/xsns_83_neopool.ino) — implements the NeoPool Modbus register protocol originally documented by Sugar Valley
- _NeoPool Control System MODBUS Register description_ — official Modbus register documentation by Sugar Valley (pdf)

---

## Disclaimer

This integration is provided "AS IS" and without any warranty or guarantee of any kind.  
The author takes no responsibility for any damage, loss, or malfunction resulting from the use or misuse of this code. Use at your own risk.

## License

This project is licensed under the [Apache License 2.0](https://choosealicense.com/licenses/apache-2.0/),
the same license used by [Home Assistant](https://www.home-assistant.io/developers/license/).

_This project is not affiliated with or endorsed by Sugar Valley, Hayward, or any other pool equipment manufacturer or distributor._  
_"VistaPool" is a trademark of Hayward Industries, Inc. This integration communicates locally via Modbus and does not use the VistaPool cloud service._
