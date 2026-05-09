# NeoPool Control System - MODBUS Register Description

**Author:** Juan Ramón Vadillo  
**Date:** March 23rd, 2015  
**Manufacturer:** Sugar Valley

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Register Description](#2-register-description)
   - 2.1 [Measures Page (MEASURE)](#21-measures-page-measure)
   - 2.2 [Global Page (GLOBAL)](#22-global-page-global)
   - 2.3 [Installer Page (INSTALLER)](#23-installer-page-installer)
   - 2.4 [Factory Page (FACTORY)](#24-factory-page-factory)
   - 2.5 [User Page (USER)](#25-user-page-user)
   - 2.6 [Miscellaneous Page (MISC)](#26-miscellaneous-page-misc)

---

## 1 Introduction

The NeoPool Control System is equipped with two RS485 communication ports with a MODBUS protocol that allows a remote controller to adjust the different working parameters of the device.

The first port, labelled on the board as **"DISPLAY"**, is usually connected to the Screen Controller, which is itself a MODBUS master. The other port, labelled as **"RF/WIFI"**, is available for external communications.

A semaphore system has been implemented between both ports in order to manage register change requests happening simultaneously in both ports. However, the remote masters can always read any register concurrently.

The slave has the **MODBUS address 1** as default communication address, but it can be changed with a reserved procedure.

**Communication parameters for the RS485 asynchronous serial port:**

| Parameter | Value       |
| --------- | ----------- |
| Baud rate | 19200 bauds |
| Parity    | None        |
| Stop bits | 1           |

> **Warning:** The alteration of registers other than the ones described in this document could lead to a bad operation of the system, and in some cases, to an unrecoverable failure requiring technical assistance.

---

## 2 Register Description

The register set is divided into 7 different pages:

| Starting Address | Name      | Description                                                                                                                                                                   |
| ---------------- | --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0x0000           | MODBUS    | Manages general configuration of the box. This page is reserved for internal purposes.                                                                                        |
| 0x0100           | MEASURE   | Contains the different measurement information including hydrolysis current, pH level, redox level, etc.                                                                      |
| 0x0200           | GLOBAL    | Contains global information, such as the amount of time that each power unit has been working.                                                                                |
| 0x0300           | FACTORY   | Contains factory data such as calibration parameters for the different power units.                                                                                           |
| 0x0400           | INSTALLER | Contains a set of configuration registers related to the box installation, such as the relays used for each function, the amount of time that each pump must operate, etc.    |
| 0x0500           | USER      | Contains user configuration registers, such as the production level for the ionization and the hydrolysis, or the set points for the pH, redox, or chlorine regulation loops. |
| 0x0600           | MISC      | Contains the configuration parameters for the screen controllers (language, colours, sound, etc.).                                                                            |

Any modifications done over the registers should be made persistent by requesting an EEPROM storage. See [`MBF_SAVE_TO_EEPROM`](#register-0x02f0--mbf_save_to_eeprom) for more information.

---

## 2.1 Measures Page (MEASURE)

### Register 0x0100 - `MBF_ION_CURRENT`

Current measured in the ionization system. The value is obtained from the microcontroller ADC and corrected using the calibration data:

- `MBF_PAR_ION_NOM`: Maximum ionization current
- `MBF_PAR_ION_CAL0`: ADC value measured at idle state
- `MBF_PAR_ION_CAL1`: ADC value measured at maximum ionization current

Formula: `MBF_ION_CURRENT = (adcValue - MBF_PAR_ION_CAL0) / (MBF_PAR_ION_CAL1 - MBF_PAR_ION_CAL0) * MBF_PAR_ION_NOM`

---

### Register 0x0101 - `MBF_HIDRO_CURRENT`

Current working level measured in the hydrolysis/electrolysis system.

Formula: `MBF_HIDRO_CURRENT = (hidroAdcValue - MBF_PAR_HIDRO_CAL0) / (MBF_PAR_HIDRO_CAL1 - MBF_PAR_HIDRO_CAL0) * MBF_PAR_HIDRO_NOM`

---

### Register 0x0102 - `MBF_MEASURE_PH`

pH level measured in hundredths. A value of 700 means pH 7.00.

This register is only valid if the pH module is enabled. Check `MBF_PH_STATUS` for the module status.

---

### Register 0x0103 - `MBF_MEASURE_RX`

Redox/ORP level measured in hundredths of ppm. A value of 100 means 1.00 ppm.

This register is only valid if the Redox module is enabled. Check `MBF_RX_STATUS`.

---

### Register 0x0104 - `MBF_MEASURE_CL`

Chlorine concentration level measured in hundredths of ppm. A value of 100 means 1.00 ppm.

This register is only valid if the Chlorine module is enabled. Check `MBF_CL_STATUS`.

---

### Register 0x0105 - `MBF_MEASURE_CONDUCTIVITY`

Conductivity level measured in the water. Only valid if the conductivity module is enabled. Check `MBF_CD_STATUS`.

---

### Register 0x0106 - `MBF_MEASURE_TEMPERATURE`

Temperature measured by the water temperature sensor, in tenths of degrees Celsius. A value of 200 means 20.0 °C.

---

### Register 0x0107 - `MBF_PH_STATUS`

Status of the pH control module. Bitmask:

| Bits | Mask   | Description                                                                                |
| ---- | ------ | ------------------------------------------------------------------------------------------ |
| 0-3  | 0x000F | pH alarm (see alarm value tables below)                                                    |
| 7    | 0x0080 | Regulation out of range (measured value too far from setpoint for regulation to correct)   |
| 10   | 0x0400 | pH control module controlled by flow detection (if enabled via `MBF_PAR_HIDRO_ION_CAUDAL`) |
| 11   | 0x0800 | Low pH pump relay on (pump activated)                                                      |
| 12   | 0x1000 | High pH pump relay on (pump activated)                                                     |
| 13   | 0x2000 | pH control module active and controlling pumps                                             |
| 14   | 0x4000 | pH measurement module active and taking measurements                                       |
| 15   | 0x8000 | pH measurement module detected                                                             |

**pH alarm values for acid and base regulation:**

| Value | Description                                                                                                      |
| ----- | ---------------------------------------------------------------------------------------------------------------- |
| 0     | No alarm                                                                                                         |
| 1     | pH too high: pH value exceeds PH1 setpoint by 0.8 units                                                          |
| 2     | pH too low: pH value is below PH2 setpoint by 0.8 units                                                          |
| 3     | pH pump (acid or base) exceeded the maximum working time set in `MBF_PAR_RELAY_PH_MAX_TIME` and has been stopped |
| 4     | pH value is above PH1 setpoint                                                                                   |
| 5     | pH value is below PH2 setpoint                                                                                   |

**pH alarm values for acid-only regulation:**

| Value | Description                                                |
| ----- | ---------------------------------------------------------- |
| 0     | No alarm                                                   |
| 1     | pH too high: pH value exceeds PH1 setpoint by 0.8 units    |
| 2     | pH too low: pH value is below PH1 setpoint by 0.8 units    |
| 3     | pH pump exceeded maximum working time and has been stopped |
| 4     | pH value is above PH1 setpoint + 0.1                       |
| 5     | pH value is below PH1 setpoint - 0.3                       |

**pH alarm values for base-only regulation:**

| Value | Description                                                |
| ----- | ---------------------------------------------------------- |
| 0     | No alarm                                                   |
| 1     | pH too high: pH value exceeds PH2 setpoint by 0.8 units    |
| 2     | pH too low: pH value is below PH2 setpoint by 0.8 units    |
| 3     | pH pump exceeded maximum working time and has been stopped |
| 4     | pH value is above PH2 setpoint + 0.1                       |
| 5     | pH value is below PH2 setpoint - 0.3                       |

---

### Register 0x0108 - `MBF_RX_STATUS`

Status of the Redox/ORP control module. Bitmask:

| Bits | Mask   | Description                                             |
| ---- | ------ | ------------------------------------------------------- |
| 7    | 0x0080 | Regulation out of range (Redox too low for regulation)  |
| 12   | 0x1000 | Redox pump relay on (pump activated)                    |
| 13   | 0x2000 | Redox control module active and controlling pump        |
| 14   | 0x4000 | Redox measurement module active and taking measurements |
| 15   | 0x8000 | Redox measurement module detected in the system         |

---

### Register 0x0109 - `MBF_CL_STATUS`

Status of the chlorine control module. Bitmask:

| Bits | Mask   | Description                                                                                                                                                                  |
| ---- | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 3    | 0x0008 | Chlorine probe flow sensor. Integrated in the probe itself; detects if water is passing through the chlorine measurement probe. If 0, the chlorine measurement is not valid. |
| 7    | 0x0080 | Regulation out of range (measured value too far from setpoint for regulation to correct)                                                                                     |
| 12   | 0x1000 | Chlorine pump relay on (pump activated)                                                                                                                                      |
| 13   | 0x2000 | Chlorine control module active and controlling pump                                                                                                                          |
| 14   | 0x4000 | Chlorine measurement module active and taking measurements (display bar should be shown)                                                                                     |
| 15   | 0x8000 | Chlorine measurement module detected in the system                                                                                                                           |

---

### Register 0x010A - `MBF_CD_STATUS`

Status of the conductivity control module. Bitmask:

| Bits | Mask   | Description                                                                                  |
| ---- | ------ | -------------------------------------------------------------------------------------------- |
| 7    | 0x0080 | Regulation out of range (measured value too far from setpoint for regulation to correct)     |
| 12   | 0x1000 | Conductivity pump relay on (pump activated)                                                  |
| 13   | 0x2000 | Conductivity control module active and controlling pump                                      |
| 14   | 0x4000 | Conductivity measurement module active and taking measurements (display bar should be shown) |
| 15   | 0x8000 | Conductivity measurement module detected in the system                                       |

---

### Register 0x010C - `MBF_ION_STATUS`

Status of the ionization control module. Bitmask:

| Bit | Mask   | Description                                                |
| --- | ------ | ---------------------------------------------------------- |
| 0   | 0x0001 | On Target - the system has reached the configured setpoint |
| 1   | 0x0002 | Low - the ionization cannot reach the configured setpoint  |
| 2   | 0x0004 | Elec - reserved                                            |
| 3   | 0x0008 | Pr off - the programmed ionization time has been exceeded  |
| 12  | 0x1000 | Ion Pol off - ionization in dead time                      |
| 13  | 0x2000 | Ion Pol 1 - ionization working in polarization 1           |
| 14  | 0x4000 | Ion Pol 2 - ionization working in polarization 2           |

---

### Register 0x010D - `MBF_HIDRO_STATUS`

Status of the hydrolysis/electrolysis control module. Bitmask:

| Bit | Mask   | Description                                                            |
| --- | ------ | ---------------------------------------------------------------------- |
| 0   | 0x0001 | On Target - the system has reached the configured setpoint             |
| 1   | 0x0002 | Low - the hydrolysis cannot reach the configured setpoint              |
| 2   | 0x0004 | Elec - reserved                                                        |
| 3   | 0x0008 | Flow - cell flow indicator (FL1)                                       |
| 4   | 0x0010 | Cover - cover input active                                             |
| 5   | 0x0020 | Active - hydrolysis module active (`hydroEnable`)                      |
| 6   | 0x0040 | Control - hydrolysis working in regulation mode (`hydroControlEnable`) |
| 7   | 0x0080 | Redox enable - hydrolysis activation by the Redox module (`rx_hen`)    |
| 8   | 0x0100 | Hidro shock enabled - chlorine shock mode active                       |
| 9   | 0x0200 | FL2 - chlorine probe flow indicator, if present                        |
| 10  | 0x0400 | Cl enable - hydrolysis activation by the chlorine module (`cl_hen`)    |
| 11  | 0x0800 | Not used                                                               |
| 12  | 0x1000 | Ion Pol off - ionization in dead time                                  |
| 13  | 0x2000 | Ion Pol 1 - ionization working in polarization 1                       |
| 14  | 0x4000 | Ion Pol 2 - ionization working in polarization 2                       |
| 15  | 0x8000 | Not used                                                               |

---

### Register 0x010E - `MBF_RELAY_STATE`

State of all configurable relays. Bitmask:

| Bit | Mask   | Description                                                   |
| --- | ------ | ------------------------------------------------------------- |
| 0   | 0x0001 | Relay 1 state (1=on, 0=off) - normally assigned to pH         |
| 1   | 0x0002 | Relay 2 state (1=on, 0=off) - normally assigned to filtration |
| 2   | 0x0004 | Relay 3 state (1=on, 0=off) - normally assigned to lighting   |
| 3   | 0x0008 | Relay 4 state                                                 |
| 4   | 0x0010 | Relay 5 state                                                 |
| 5   | 0x0020 | Relay 6 state                                                 |
| 6   | 0x0040 | Relay 7 state                                                 |

---

### Register 0x010F - `MBF_HIDRO_SWITCH_VALUE`

Hydrolysis PWM duty cycle (0-65535). An internal value indicating the voltage being applied by the system to the hydrolysis cell to achieve the desired production current.

---

### Register 0x0110 - `MBF_NOTIFICATION`

Bitmask indicating which register page has changed since the last time it was read. This enables a MODBUS master to refresh its cached register values in an optimized way, only re-reading pages that have changed rather than polling all registers periodically.

It is the responsibility of the MODBUS master to clear this register to 0 once the modified page registers have been read.

| Bit | Mask   | Description                     |
| --- | ------ | ------------------------------- |
| 0   | 0x0001 | `MBMSK_NOTIF_MODBUS_CHANGED`    |
| 1   | 0x0002 | `MBMSK_NOTIF_GLOBAL_CHANGED`    |
| 2   | 0x0004 | `MBMSK_NOTIF_FACTORY_CHANGED`   |
| 3   | 0x0008 | `MBMSK_NOTIF_INSTALLER_CHANGED` |
| 4   | 0x0010 | `MBMSK_NOTIF_USER_CHANGED`      |
| 5   | 0x0020 | `MBMSK_NOTIF_MISC_CHANGED`      |

---

### Register 0x0111 - `MBF_HIDRO_VOLTAGE`

Voltage applied to the hydrolysis cell. Together with `MBF_HIDRO_CURRENT` (0x0101), this register allows extrapolation of the water salinity.

---

## 2.2 Global Page (GLOBAL)

### Register 0x02F0 - `MBF_SAVE_TO_EEPROM`

Writing the value 1 to this register immediately starts an EEPROM storage operation. During the EEPROM storage procedure, the system may be unresponsive to MODBUS requests. The operation will always last less than 1 second.

EEPROM write operations occur automatically every 10 minutes. However, after modifying a MODBUS configuration register it is recommended to force a write operation, as this is the only safe way to preserve the information if the box is switched off before the periodic EEPROM write automatically occurs.

> **Warning:** The number of EEPROM write operations is guaranteed to be 100,000 cycles. Once this number is exceeded, safe storage of information cannot be guaranteed.

---

## 2.3 Installer Page (INSTALLER)

### Register 0x0400 - `MBF_PAR_ION_POL0`

Time in minutes that the system must remain working in **positive polarization** during copper-silver ionization.

> To make changes persistent, execute the EEPROM storage procedure described in `MBF_SAVE_TO_EEPROM`.

---

### Register 0x0401 - `MBF_PAR_ION_POL1`

Time in minutes that the system must remain working in **negative polarization** during copper-silver ionization.

> To make changes persistent, execute the EEPROM storage procedure described in `MBF_SAVE_TO_EEPROM`.

---

### Register 0x0402 - `MBF_PAR_ION_POL2`

Time in minutes that the system must remain in **dead time** (no power delivery) during copper-silver ionization.

> To make changes persistent, execute the EEPROM storage procedure described in `MBF_SAVE_TO_EEPROM`.

---

### Register 0x0403 - `MBF_PAR_HIDRO_ION_CAUDAL`

Bitmask controlling external control of ionization, hydrolysis, and pumps. Active bits enable the corresponding behavior:

| Bit | Mask   | Name                 | Description                                                                                                                                      |
| --- | ------ | -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| 0   | 0x0001 | `FL1_CTRL`           | If FL1 signal is inactive, disable all system elements                                                                                           |
| 1   | 0x0002 | `FL2_CTRL`           | If FL2 signal is inactive, disable all system elements                                                                                           |
| 2   | 0x0004 | `FULL_CL_HIDRO_CTRL` | If a Cl module is installed and its flow sensor is inactive, disable all system elements                                                         |
| 3   | 0x0008 | `SLAVE`              | If slave input is inactive, disable all system elements                                                                                          |
| 4   | 0x0010 | `PADDLE_SWITCH`      | Enable paddle switch                                                                                                                             |
| 5   | 0x0020 | `PADDLE_SWITCH_INV`  | Enable inverted paddle switch                                                                                                                    |
| 7   | 0x0080 | `INVERSION`          | Determines whether "active" means open or closed for input signals; allows inverting behavior (e.g., a paddle that closes when there is no flow) |

> To make changes persistent, execute the EEPROM storage procedure described in `MBF_SAVE_TO_EEPROM`.

---

### Register 0x0404 - `MBF_PAR_HIDRO_MODE`

External hydrolysis control mode from measurement modules:

| Value | Description               |
| ----- | ------------------------- |
| 0     | No control                |
| 1     | Standard control (on/off) |
| 2     | With timed pump           |

---

### Register 0x0405 - `MBF_PAR_HIDRO_POL0`

Time in minutes for hydrolysis/electrolysis **positive polarization**.

> To make changes persistent, execute the EEPROM storage procedure described in `MBF_SAVE_TO_EEPROM`.

---

### Register 0x0406 - `MBF_PAR_HIDRO_POL1`

Time in minutes for hydrolysis/electrolysis **negative polarization**.

> To make changes persistent, execute the EEPROM storage procedure described in `MBF_SAVE_TO_EEPROM`.

---

### Register 0x0407 - `MBF_PAR_HIDRO_POL2`

Time in minutes for hydrolysis/electrolysis **dead time** (no power delivery).

> To make changes persistent, execute the EEPROM storage procedure described in `MBF_SAVE_TO_EEPROM`.

---

### Registers 0x0408-0x0409 - `MBF_PAR_TIME_LOW` and `MBF_PAR_TIME_HIGH`

Two registers forming a 32-bit time counter. This counter stores the system time as seconds elapsed since January 1, 1970 (Unix Epoch).

- `MBF_PAR_TIME_LOW` (0x0408): Low 16 bits
- `MBF_PAR_TIME_HIGH` (0x0409): High 16 bits

See also `MBF_ACTION_COPY_TO_RTC` (0x04F0) for writing this time to the hardware RTC.

---

### Register 0x040A - `MBF_PAR_PH_ACID_RELAY_GPIO`

Relay number assigned to the acid pump function (pH modules only).

---

### Register 0x040B - `MBF_PAR_PH_BASE_RELAY_GPIO`

Relay number assigned to the base pump function (pH modules only).

---

### Register 0x040C - `MBF_PAR_RX_RELAY_GPIO`

Relay number assigned to the Redox regulation function. If the value is 0, no relay is assigned and therefore there is no pump function.

To check whether this relay is active:

- **Method 1:** Check the `MBMSK_RX_STATUS_RELAY` bit in `MBF_RX_STATUS`
- **Method 2:** Calculate the bit assigned to the relay in `MBF_RELAY_STATE`

---

### Register 0x040D - `MBF_PAR_CL_RELAY_GPIO`

Relay number assigned to the chlorine pump function (free chlorine measurement modules only).

---

### Register 0x040E - `MBF_PAR_CD_RELAY_GPIO`

Relay number assigned to the conductivity pump function (brine) (conductivity measurement modules only).

---

### Register 0x040F - `MBF_PAR_TEMPERATURE_ACTIVE`

Indicates whether the device has temperature measurement: 1 = yes, 0 = no.

---

### Register 0x0410 - `MBF_PAR_LIGHTING_GPIO`

Relay number assigned to the lighting function. 0 = inactive.

---

### Register 0x0411 - `MBF_PAR_FILT_MODE`

Filtration mode:

| Value | Name               | Description                                                                                                                                               |
| ----- | ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0     | MANUAL             | Always available. Allows filtration (and all dependent systems) to be switched on and off manually.                                                       |
| 1     | AUTO               | Always available. Filtration is switched on and off according to the configuration of timers TIMER1, TIMER2, and TIMER3.                                  |
| 2     | HEATING            | Similar to AUTO mode, but includes temperature configuration for the heating function. Requires `MBF_PAR_HEATING_MODE = 1` and an assigned heating relay. |
| 3     | SMART              | Adjusts pump working times based on water temperature. Requires `MBF_PAR_TEMPERATURE_ACTIVE = 1`.                                                         |
| 4     | INTELLIGENT        | Most complex mode - combines temperature and heating. Requires both `MBF_PAR_TEMPERATURE_ACTIVE = 1` and `MBF_PAR_HEATING_MODE = 1`.                      |
| 13    | BACKWASH           | Started when the backwash operation is activated.                                                                                                         |
| 14    | CHLORINATION SHOCK | Started when the chlorination shock operation is activated.                                                                                               |

**Mode 0: MANUAL**

This mode allows the filtration to be switched on and off manually. No timers or additional functions are involved. The state is controlled via `MBF_PAR_FILT_MANUAL_STATE`.

**Mode 1: AUTO (timed)**

Filtration is switched on according to timers. The timers allow setting start and end times for filtration. Timers always operate on a daily basis.

**Mode 2: HEATING (timed with optional climate control)**

Works like AUTO mode but also includes a relay that is activated or deactivated based on water temperature. The setpoint temperature is configured in this mode, and the system uses a 1-degree hysteresis.

Additionally, there is an optional "climate control" (shown on screen as "CLIMA" on/off). This option keeps the filtration running after its scheduled period if the temperature is below the setpoint. When the setpoint is reached, filtration stops and does not restart until the next scheduled period.

Example of hysteresis: if the setpoint is 23 °C, the system activates when temperature drops below 22 °C and stops when it exceeds 23 °C.

> Note: This mode is only visible when the temperature sensor option is active and heating is enabled.

**Mode 3: SMART**

Based on the AUTO/timed mode, but adjusts filtration times based on temperature. Two temperature parameters are provided: the maximum temperature (at which filtration times follow the configured timers) and the minimum temperature (at which filtration is reduced to 5 minutes, the minimum working time). Filtration times scale linearly between these two temperatures.

Additionally there is an optional anti-freeze mode, which keeps filtration on if the system temperature is below 2 °C.

> Note: This mode is only visible when the temperature sensor option is active.

**Mode 4: INTELLIGENT**

The most complex filtration mode. It involves both temperature and heating.

The user has two working parameters:

- Desired temperature
- Minimum filtration time (minimum 2 hours, maximum 24 hours) = Tfilt

Operation:

- The system starts filtration every 2 hours.
- The minimum filtration time is divided into 12 segments (Tfon = Tfilt/12).
- A variable Tbonus = Tfilt - 2 hours is created.
- After 10 minutes, Tbonus starts counting down. When Tbonus is exhausted, filtration stops.
- After Tfon, the temperature is measured (the first 10 minutes ensure sufficient water flow). If the temperature is at or above the setpoint, filtration stops.
- If the temperature is below the setpoint, filtration continues and the time is deducted from Tbonus.
- Filtration runs a minimum of 10 minutes every 2 hours to check temperature. So the minimum filtration in intelligent mode is 2 hours per day (10 min × 12 times).

Example: with 10 hours minimum filtration time: 10h × 60min / 12 = 50 minutes per 2-hour interval. Of those 50 minutes, 10 are mandatory and 40 are used when heating is needed.

> Note: This mode is only visible when the temperature sensor option is active.

---

### Register 0x0412 - `MBF_PAR_FILT_GPIO`

Relay selected for the filtration function (default: relay 2). When this value is 0, no relay is assigned and the equipment does not control filtration; the filtration option will not appear in the user menu.

---

### Register 0x0413 - `MBF_PAR_FILT_MANUAL_STATE`

Filtration state in manual mode: 1 = on, 0 = off.

---

### Register 0x0414 - `MBF_PAR_HEATING_MODE`

Heating mode: 0 = the device has no heating, 1 = the device has heating.

---

### Register 0x0415 - `MBF_PAR_HEATING_GPIO`

Relay selected for the heating function (default: relay 7). When this value is 0, no relay is assigned and the heating-related filtration modes will not be shown.

---

### Register 0x0416 - `MBF_PAR_HEATING_TEMP`

Heating setpoint temperature.

---

### Register 0x0417 - `MBF_PAR_CLIMA_ONOFF`

Climate mode activation: 0 = inactive, 1 = active.

---

### Register 0x0418 - `MBF_PAR_SMART_TEMP_HIGH`

Upper temperature threshold for Smart filtration mode.

---

### Register 0x0419 - `MBF_PAR_SMART_TEMP_LOW`

Lower temperature threshold for Smart filtration mode.

---

### Register 0x041A - `MBF_PAR_SMART_ANTI_FREEZE`

Anti-freeze mode: 1 = enabled, 0 = disabled. Only available in Smart filtration mode.

---

### Register 0x041B - `MBF_PAR_SMART_INTERVAL_REDUCTION`

Read-only. Reports what percentage (0-100%) is being applied to the nominal filtration time. A value of 100% means the full programmed filtration time is active.

---

### Register 0x041C - `MBF_PAR_INTELLIGENT_TEMP`

Temperature setpoint for Intelligent filtration mode.

---

### Register 0x041D - `MBF_PAR_INTELLIGENT_FILT_MIN_TIME`

Minimum filtration time in minutes for Intelligent mode.

---

### Register 0x041E - `MBF_PAR_INTELLIGENT_BONUS_TIME`

Bonus time for the current set of intervals in Intelligent mode.

---

### Register 0x041F - `MBF_PAR_INTELLIGENT_TT_NEXT_INTERVAL`

Time remaining until the next filtration interval in Intelligent mode. When it reaches 0, a new interval starts and the counter is reloaded with the interval period (2 × 3600 seconds).

---

### Register 0x0420 - `MBF_PAR_INTELLIGENT_INTERVALS`

Number of started intervals in Intelligent mode. When it reaches 12, it resets to 0 and the bonus time is reloaded from `MBF_PAR_INTELLIGENT_FILT_MIN_TIME`.

---

### Register 0x0421 - `MBF_PAR_FILTRATION_STATE`

Read-only. Current state of the filtration: 0 = off, 1 = on.

In MANUAL mode (`MBF_PAR_FILT_MODE = 0`), the state is set by writing to `MBF_PAR_FILT_MANUAL_STATE`.

---

### Register 0x0422 - `MBF_PAR_HEATING_DELAY_TIME`

Internal timer in seconds that counts up when heating is due to be enabled. Once it reaches 60 seconds, heating is enabled. For internal use only.

---

### Registers 0x0423-0x0424 - `MBF_PAR_FILTERING_TIME_LOW` and `MBF_PAR_FILTERING_TIME_HIGH`

Internal 32-bit timer for Intelligent filtration mode. Counts the total filtration time performed during a given day. **For internal use only; should not be modified.**

---

### Registers 0x0425-0x0426 - `MBF_PAR_INTELLIGENT_INTERVAL_TIME_LOW` and `MBF_PAR_INTELLIGENT_INTERVAL_TIME_HIGH`

Internal 32-bit timer that counts the filtration interval assigned to Intelligent mode. **For internal use only; should not be modified.**

---

### Register 0x0427 - `MBF_PAR_UV_MODE`

UV radiation disinfection mode. To enable UV support for a given device, add the mask `MBMSK_MODEL_UV` to the `MBF_PAR_MODEL` register.

| Value | Name | Description                                                                                             |
| ----- | ---- | ------------------------------------------------------------------------------------------------------- |
| 0     | OFF  | UV is switched off and will not turn on when filtration starts                                          |
| 1     | ON   | UV is switched on and will turn on when filtration starts; the UV lamp time counter will be incremented |

---

### Register 0x0428 - `MBF_PAR_UV_HIDE_WARN`

Suppression of UV mode warning messages:

| Mask   | Name                         | Description                  |
| ------ | ---------------------------- | ---------------------------- |
| 0x0001 | `MBMSK_UV_HIDE_WARN_CLEAN`   | Suppress cleaning warning    |
| 0x0002 | `MBMSK_UV_HIDE_WARN_REPLACE` | Suppress replacement warning |

---

### Register 0x0429 - `MBF_PAR_UV_RELAY_GPIO`

Relay number assigned to the UV function.

---

### Register 0x042A - `MBF_PAR_PH_PUMP_REP_TIME_ON`

Time that the pH pump will be turned on in repetitive mode.

| Bits | Mask   | Description                                                                     |
| ---- | ------ | ------------------------------------------------------------------------------- |
| 0-14 | 0x7FFF | Time value (see time coding below)                                              |
| 15   | 0x8000 | `MBMSK_PH_PUMP_REPETITIVE` - if active, the pH pump operates in repetitive mode |

**Time coding:** Covers periods of 1 to 180 seconds (1-second granularity) and 3 to 999 minutes (1-minute granularity). A value of ≤180 equals that many seconds. A value of >180: time in minutes = (value - 180 + 3). Example: value 200 → (200 - 180 + 3) = 23 minutes on.

---

### Register 0x042B - `MBF_PAR_PH_PUMP_REP_TIME_OFF`

Time that the pH pump will be turned off in repetitive mode. No upper configuration bits. Uses the same time coding as `MBF_PAR_PH_PUMP_REP_TIME_ON`.

---

### Register 0x042C - `MBF_PAR_HIDRO_COVER_ENABLE`

Configuration options for the hydrolysis/electrolysis module with cover detection:

| Bit | Mask   | Name                                      | Description                                                                                                                         |
| --- | ------ | ----------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| 0   | 0x0001 | `MBMSK_HIDRO_COVER_ENABLE`                | When active, hydrolysis production is reduced by the percentage in `MBF_PAR_HIDRO_COVER_REDUCTION` when the cover input is detected |
| 1   | 0x0002 | `MBMSK_HIDRO_TEMPERATURE_SHUTDOWN_ENABLE` | When active, hydrolysis production stops when the temperature falls below the threshold in `MBF_PAR_HIDRO_COVER_REDUCTION`          |

---

### Register 0x042D - `MBF_PAR_HIDRO_COVER_REDUCTION`

Configuration levels for cover reduction and hydrolysis shutdown temperature:

| Bits | Mask   | Name                               | Description                               |
| ---- | ------ | ---------------------------------- | ----------------------------------------- |
| 0-7  | 0x00FF | `MBMSK_HIDRO_COVER_REDUCTION`      | Percentage for cover reduction            |
| 8-15 | 0xFF00 | `MBMSK_HIDRO_SHUTDOWN_TEMPERATURE` | Temperature level for hydrolysis shutdown |

---

### Register 0x042E - `MBF_PAR_PUMP_RELAY_TIME_OFF`

Time in minutes or seconds that a dosing pump must remain **off** in temporized pump mode. Applies to all pumps except pH. Uses the same time coding as `MBF_PAR_PH_PUMP_REP_TIME_ON`.

---

### Register 0x042F - `MBF_PAR_PUMP_RELAY_TIME_ON`

Time in minutes or seconds that a dosing pump must remain **on** in temporized pump mode. Applies to all pumps except pH. Uses the same time coding as `MBF_PAR_PH_PUMP_REP_TIME_ON`.

---

### Register 0x0430 - `MBF_PAR_RELAY_PH`

pH regulation configuration:

| Value | Name                             | Description                                |
| ----- | -------------------------------- | ------------------------------------------ |
| 0     | `MBV_PAR_RELAY_PH_ACID_AND_BASE` | Device works with both acid and base pumps |
| 1     | `MBV_PAR_RELAY_PH_ACID_ONLY`     | Device works with acid pump only           |
| 2     | `MBV_PAR_RELAY_PH_BASE_ONLY`     | Device works with base pump only           |

---

### Register 0x0431 - `MBF_PAR_RELAY_MAX_TIME`

Maximum time in seconds that a dosing pump can operate before raising an alarm. The behavior of the system when this time is exceeded is controlled by `MBF_PAR_RELAY_MODE`.

---

### Register 0x0432 - `MBF_PAR_RELAY_MODE`

System behavior when the dosing time limit (set in `MBF_PAR_RELAY_MAX_TIME`) is exceeded:

| Bits | Mask   | Module            |
| ---- | ------ | ----------------- |
| 0-1  | 0x0003 | pH                |
| 2-3  | 0x000C | Rx (Redox)        |
| 4-5  | 0x0030 | Cl (Chlorine)     |
| 6-7  | 0x00C0 | Cd (Conductivity) |
| 8-9  | 0x0300 | Turbidity         |

Possible values for each field:

| Value | Name                               | Description                                                    |
| ----- | ---------------------------------- | -------------------------------------------------------------- |
| 0     | `MBV_PAR_RELAY_MODE_IGNORE`        | The system ignores the alarm and dosing continues              |
| 1     | `MBV_PAR_RELAY_MODE_SHOW_ONLY`     | The system shows the alarm on screen, but dosing continues     |
| 2     | `MBV_PAR_RELAY_MODE_SHOW_AND_STOP` | The system shows the alarm on screen and stops the dosing pump |

---

### Register 0x0433 - `MBF_PAR_RELAY_ACTIVATION_DELAY`

Delay time in seconds for the pH pump when the measured pH value is outside the allowable setpoints. The system internally adds an extra 10 seconds to the stored value. The pump starts dosing once the pH-out-of-range condition has been maintained for the configured time.

---

### Registers 0x0434-0x04E7 - `MBF_PAR_TIMER_BLOCK_BASE`

A block of 180 registers holding the configuration of the 12 system timers. Each timer is assigned to a specific function:

| Timer | Base Register | Assigned Function                   |
| ----- | ------------- | ----------------------------------- |
| 0     | 0x0434        | Filtration interval 1               |
| 1     | 0x0443        | Filtration interval 2               |
| 2     | 0x0452        | Filtration interval 3               |
| 3     | 0x0461        | Auxiliary relay 1 - second interval |
| 4     | 0x0470        | Lighting interval                   |
| 5     | 0x047F        | Auxiliary relay 2 - second interval |
| 6     | 0x048E        | Auxiliary relay 3 - second interval |
| 7     | 0x049D        | Auxiliary relay 4 - second interval |
| 8     | 0x04AC        | Auxiliary relay 1 - first interval  |
| 9     | 0x04BB        | Auxiliary relay 2 - first interval  |
| 10    | 0x04CA        | Auxiliary relay 3 - first interval  |
| 11    | 0x04D9        | Auxiliary relay 4 - first interval  |

Each timer block uses 15 registers:

| Offset | Name                    | Description                                                                   |
| ------ | ----------------------- | ----------------------------------------------------------------------------- |
| 0      | `OFFMB_TIMER_ENABLE`    | Enables the timer in the selected working mode (see modes below)              |
| 1-2    | `OFFMB_TIMER_ON`        | 32-bit timestamp (Low/High) that starts the timer                             |
| 3-4    | `OFFMB_TIMER_OFF`       | 32-bit timestamp (Low/High) that stops the timer (not used)                   |
| 5-6    | `OFFMB_TIMER_PERIOD`    | 32-bit time in seconds between starting points (e.g., daily = 86400)          |
| 7-8    | `OFFMB_TIMER_INTERVAL`  | 32-bit time in seconds that the timer runs when started (e.g., 1 hour = 3600) |
| 9-10   | `OFFMB_TIMER_COUNTDOWN` | 32-bit remaining time in seconds for countdown mode                           |
| 11-12  | `OFFMB_TIMER_FUNCTION`  | Function assigned to this timer (see function codes below)                    |
| 13-14  | `OFFMB_TIMER_WORK_TIME` | Number of seconds the timer has been operating                                |

**Allowed timer working modes:**

| Value | Name                    | Description                                    |
| ----- | ----------------------- | ---------------------------------------------- |
| 0     | `CTIMER_DISABLE`        | Timer disabled                                 |
| 1     | `CTIMER_ENABLED`        | Timer enabled and independent                  |
| 2     | `CTIMER_ENABLED_LINKED` | Timer enabled and linked to relay from timer 0 |
| 3     | `CTIMER_ALWAYS_ON`      | Relay assigned to this timer always on         |
| 4     | `CTIMER_ALWAYS_OFF`     | Relay assigned to this timer always off        |
| 5     | `CTIMER_COUNTDOWN`      | Timer in countdown mode                        |

**Timer function codes:**

| Value  | Name                    | Description                |
| ------ | ----------------------- | -------------------------- |
| 0x0001 | `CTIMER_FCT_FILTRATION` | Filtration function        |
| 0x0002 | `CTIMER_FCT_LIGHTING`   | Lighting function          |
| 0x0004 | `CTIMER_FCT_HEATING`    | Heating function           |
| 0x0100 | `CTIMER_FCT_AUXREL1`    | Auxiliary relay 1 function |
| 0x0200 | `CTIMER_FCT_AUXREL2`    | Auxiliary relay 2 function |
| 0x0400 | `CTIMER_FCT_AUXREL3`    | Auxiliary relay 3 function |
| 0x0800 | `CTIMER_FCT_AUXREL4`    | Auxiliary relay 4 function |
| 0x1000 | `CTIMER_FCT_AUXREL5`    | Auxiliary relay 5 function |
| 0x2000 | `CTIMER_FCT_AUXREL6`    | Auxiliary relay 6 function |
| 0x4000 | `CTIMER_FCT_AUXREL7`    | Auxiliary relay 7 function |

---

### Register 0x04E8 - `MBF_PAR_FILTVALVE_ENABLE`

Enables or disables the filter cleaning (backwash) functionality:

| Value | Description                         |
| ----- | ----------------------------------- |
| 0     | Functionality disabled              |
| 1     | Functionality enabled in Besgo mode |

---

### Register 0x04E9 - `MBF_PAR_FILTVALVE_MODE`

Valve timing mode:

| Value | Name                | Description                                                                                  |
| ----- | ------------------- | -------------------------------------------------------------------------------------------- |
| 1     | `CTIMER_ENABLED`    | Timed system - uses start time and period to schedule cleaning                               |
| 3     | `CTIMER_ALWAYS_ON`  | Cleaning activated manually; remains on for the duration set in `MBF_PAR_FILTVALVE_INTERVAL` |
| 4     | `CTIMER_ALWAYS_OFF` | Filter cleaning is manually disabled and never activates                                     |

---

### Register 0x04EA - `MBF_PAR_FILTVALVE_GPIO`

Relay assigned to the filter cleaning function (default: AUX2 = value 5):

| Value | Description                                               |
| ----- | --------------------------------------------------------- |
| 0     | No relay assigned (filter cleaning function is inhibited) |
| 1     | pH relay                                                  |
| 2     | Filtration relay                                          |
| 3     | Lighting relay                                            |
| 4     | AUX1 relay                                                |
| 5     | AUX2 relay (default)                                      |
| 6     | AUX3 relay                                                |
| 7     | AUX4 relay                                                |

---

### Registers 0x04EB-0x04EC - `MBF_PAR_FILTVALVE_START` (32-bit)

32-bit timestamp (Low/High) marking the scheduled start time of filter cleaning.

---

### Register 0x04ED - `MBF_PAR_FILTVALVE_PERIOD_MINUTES`

Period in minutes between filter cleaning actions. For example, a value of 60 means one cleaning action per hour.

---

### Register 0x04EE - `MBF_PAR_FILTVALVE_INTERVAL`

Duration of the filter cleaning action in seconds.

---

### Register 0x04EF - `MBF_PAR_FILTVALVE_REMAINING`

Remaining time of the current filter cleaning action in seconds. A value of 0 means no cleaning is in progress.

When a cleaning action starts, the value of `MBF_PAR_FILTVALVE_INTERVAL` is copied into this register and then decremented once per second. The display uses this register to show the progress of the cleaning function.

---

### Register 0x04F0 - `MBF_ACTION_COPY_TO_RTC`

Special function register - use with extreme care. Writing to this register forces the values of `MBF_PAR_TIME_LOW` (0x0408) and `MBF_PAR_TIME_HIGH` (0x0409) to be written into the internal RTC microcontroller clock management registers.

---

## 2.4 Factory Page (FACTORY)

> **Warning:** The factory registers marked as "DO NOT MODIFY" must not be changed. Uncontrolled modification of these registers could lead to bad operation of the system, and in some cases to an unrecoverable failure requiring technical assistance.

---

### Register 0x0300 - `MBF_PAR_VERSION`

PowerBox software version. Not used.

---

### Register 0x0301 - `MBF_PAR_MODEL`

Equipment model options bitmask. **DO NOT MODIFY.**

| Bit | Mask   | Name                   | Description                                                 |
| --- | ------ | ---------------------- | ----------------------------------------------------------- |
| 0   | 0x0001 | `MBMSK_MODEL_ION`      | Device includes copper-silver ionization control            |
| 1   | 0x0002 | `MBMSK_MODEL_HIDRO`    | Device includes hydrolysis or electrolysis                  |
| 2   | 0x0004 | `MBMSK_MODEL_UV`       | Device includes UV lamp disinfection control                |
| 3   | 0x0008 | `MBMSK_MODEL_SALINITY` | Device includes salinity measurement (Fanless devices only) |

---

### Register 0x0302 - `MBF_PAR_SERNUM`

Equipment serial number. Not used.

---

### Register 0x0303 - `MBF_PAR_ION_NOM`

Maximum ionization production level. **DO NOT MODIFY.**

---

### Register 0x0306-0x0307 - `MBF_PAR_HIDRO_NOM`

Maximum hydrolysis/electrolysis production level. If the hydrolysis module operates in percent mode, this value is 100. If operating in g/h mode, this value contains the maximum production in g/h units. **DO NOT MODIFY.**

---

### Register 0x030A - `MBF_PAR_SAL_AMPS`

Current setpoint (in regulation) at which voltage is measured for salinity calculation.

---

### Register 0x030B - `MBF_PAR_SAL_CELLK`

Cell constant: the relationship between the measured resistance in the measurement process and its equivalence in g/l (grams per liter).

Salinity formula:
$$\text{Salinity}_{23°C} = \frac{R_{CELL}}{K_{CELL}} \cdot \frac{1}{1 + T_{COMP} \cdot (T - 23°C)}$$

---

### Register 0x030C - `MBF_PAR_SAL_TCOMP`

Temperature deviation coefficient of conductivity for salinity calculation.

---

### Register 0x0322 - `MBF_PAR_HIDRO_MAX_VOLTAGE` _(Fanless devices only)_

Maximum voltage in tenths of a volt that can be reached by the hydrolysis current regulation. Default: 80 (= 8.0 V maximum cell operating voltage).

> To make changes persistent, execute the EEPROM storage procedure described in `MBF_SAVE_TO_EEPROM`.

---

### Register 0x0323 - `MBF_PAR_HIDRO_FLOW_SIGNAL` _(Fanless devices only)_

Flow detection signal configuration for hydrolysis operation:

| Value | Name                                       | Description                                                                                                                        |
| ----- | ------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| 0     | `MBV_PAR_HIDRO_FLOW_SIGNAL_STD`            | Standard detection based on conduction between an auxiliary electrode and either cell electrode                                    |
| 1     | `MBV_PAR_HIDRO_FLOW_SIGNAL_ALWAYS_ON`      | Always connected - forces hydrolysis current generation even without flow detected                                                 |
| 2     | `MBV_PAR_HIDRO_FLOW_SIGNAL_PADDLE`         | Detection based on paddle switch connected to FL1 input                                                                            |
| 3     | `MBV_PAR_HIDRO_FLOW_SIGNAL_PADDLE_AND_STD` | Both paddle switch (FL1) AND standard detection; flow is detected when BOTH detect flow; hydrolysis stops if either opens          |
| 4     | `MBV_PAR_HIDRO_FLOW_SIGNAL_PADDLE_OR_STD`  | Paddle switch (FL1) OR standard detection; flow is detected when EITHER detects flow; hydrolysis stops only if BOTH detect no flow |

Default: 0 (standard detection).

> To make changes persistent, execute the EEPROM storage procedure described in `MBF_SAVE_TO_EEPROM`.

---

### Register 0x0324 - `MBF_PAR_HIDRO_MAX_PWM_STEP_UP` _(Fanless devices only)_

PWM ramp-up rate in pulses per work cycle for hydrolysis. Controls the rate at which power delivered to the cell increases, enabling a gradual power ramp-up so as not to saturate the switching power supply. Default: 150.

> To make changes persistent, execute the EEPROM storage procedure described in `MBF_SAVE_TO_EEPROM`.

---

### Register 0x0325 - `MBF_PAR_HIDRO_MAX_PWM_STEP_DOWN` _(Fanless devices only)_

PWM ramp-down rate in pulses per work cycle for hydrolysis. Controls the rate at which power delivered to the cell decreases gradually, preventing the switching power supply from disconnecting due to lack of load. The ramp-down rate must match the type of cell used, as the cell stores charge after the current stimulus ceases. Default: 20.

> To make changes persistent, execute the EEPROM storage procedure described in `MBF_SAVE_TO_EEPROM`.

---

## 2.5 User Page (USER)

> All user page registers should be made persistent using `MBF_SAVE_TO_EEPROM` after modification.

---

### Register 0x0500 - `MBF_PAR_ION`

Ionization target production level. The value set here must not exceed the factory maximum set in `MBF_PAR_ION_NOM`.

---

### Register 0x0501 - `MBF_PAR_ION_PR`

Time in minutes that the ionization must be active each time filtration starts.

---

### Register 0x0502 - `MBF_PAR_HIDRO`

Hydrolysis target production level. When operating in percent mode, this value is the percentage of production. When operating in g/h mode, this value is the desired production in g/h units.

The value must not exceed the factory maximum set in `MBF_PAR_HIDRO_NOM`.

---

### Register 0x0504 - `MBF_PAR_PH1`

Upper limit (high setpoint) of the pH regulation system, multiplied by 100. Example: to set 7.50, write 750.

This register must always be higher than `MBF_PAR_PH2`.

---

### Register 0x0505 - `MBF_PAR_PH2`

Lower limit (low setpoint) of the pH regulation system, multiplied by 100. Example: to set 7.00, write 700.

This register must always be lower than `MBF_PAR_PH1`.

---

### Register 0x0508 - `MBF_PAR_RX1`

Redox/ORP regulation setpoint. Value must be in the range 0 to 1000.

---

### Register 0x050A - `MBF_PAR_CL1`

Chlorine regulation setpoint, multiplied by 100. Example: to set 1.5 ppm, write 150. Value range: 0 to 1000.

---

### Register 0x051B - `MBF_PAR_FUNCTION_DEPENDENCY`

Function dependency specification - defines dependency of system functions on external events:

| Bits | Mask   | Name                   | Description                 |
| ---- | ------ | ---------------------- | --------------------------- |
| 0-2  | 0x0007 | `MBMSK_FCTDEP_HEATING` | Heating function dependency |

Heating dependency bit values:

| Bit | Mask   | Name                          | Description                          |
| --- | ------ | ----------------------------- | ------------------------------------ |
| 0   | 0x0001 | `MBMSK_DEPENDENCY_FL1_PADDLE` | Heating depends on FL1 paddle switch |
| 1   | 0x0002 | `MBMSK_DEPENDENCY_FL2`        | Heating depends on FL2               |
| 2   | 0x0004 | `MBMSK_DEPENDENCY_SLAVE`      | Heating depends on slave input       |

---

## 2.6 Miscellaneous Page (MISC)

This page contains registers associated with the display configuration and its visualization options.

---

### Register 0x0600 - `MBF_PAR_UICFG_MACHINE`

Machine type, used to determine the title, colors, and units to display for hydrolysis/electrolysis:

| Value | Identifier        | Description                                          |
| ----- | ----------------- | ---------------------------------------------------- |
| 0     | `MACH_NONE`       | No style assigned (default state after EEPROM erase) |
| 1     | `MACH_HIDROLIFE`  | Hidrolife style (yellow)                             |
| 2     | `MACH_AQUASCENIC` | Aquascenic style (blue)                              |
| 3     | `MACH_OXILIFE`    | Oxilife style (green)                                |
| 4     | `MACH_BIONET`     | Bionet style (light blue)                            |
| 5     | `MACH_HIDRONISER` | Hidroniser style (red)                               |
| 6     | `MACH_UVSCENIC`   | UVScenic style (lilac)                               |
| 7     | `MACH_STATION`    | Station style (orange)                               |
| 8     | `MACH_BRILIX`     | Brilix style                                         |
| 9     | `MACH_GENERIC`    | Generic style (configure title and color separately) |
| 10    | `MACH_BAYROL`     | Bayrol style                                         |
| 11    | `MACH_HAY`        | Hay style                                            |

When generic (9) is specified, the title and color registers described below must also be configured.

---

### Register 0x0601 - `MBF_PAR_UICFG_LANGUAGE`

User interface language:

| Value | Language                     |
| ----- | ---------------------------- |
| 0     | Spanish                      |
| 1     | English                      |
| 2     | French                       |
| 3     | German                       |
| 4     | Italian                      |
| 5     | Portuguese (not implemented) |
| 6     | Turkish                      |
| 7     | Czech                        |

---

### Register 0x0602 - `MBF_PAR_UICFG_BACKLIGHT`

Screen backlight configuration, divided into two 8-bit halves:

**Low byte (bits 0-7): screen timeout when no keys are pressed:**

| Value | Timeout         |
| ----- | --------------- |
| 0     | 15 seconds      |
| 1     | 30 seconds      |
| 2     | 60 seconds      |
| 3     | 5 minutes       |
| 4     | Never turns off |

**High byte (bits 8-15):** Backlight brightness percentage (10 to 100%).

---

### Register 0x0603 - `MBF_PAR_UICFG_SOUND`

Sound alert configuration bitmask:

| Bit | Mask   | Description                                                         |
| --- | ------ | ------------------------------------------------------------------- |
| 0   | 0x0001 | CLICK - a click sounds each time a key is pressed                   |
| 1   | 0x0002 | POPUPS - a sound plays each time a popup message appears            |
| 2   | 0x0004 | ALERTS - an alarm sounds when there is an alert on the device (AL3) |
| 3   | 0x0008 | FILTRATION - an audible warning occurs each time filtration starts  |

---

### Register 0x0604 - `MBF_PAR_UICFG_PASSWORD`

Equipment password encoded in BCD format.

---

### Register 0x0605 - `MBF_PAR_UICFG_VISUAL_OPTIONS`

Visual options bitmask for user interface menus. Bits 0-7 hide normally visible options; bits 8-15 show normally hidden options:

| Bit | Mask   | Name                                 | Description                                                                                                                                               |
| --- | ------ | ------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0   | 0x0001 | `HIDE_TEMPERATURE`                   | Hide temperature measurement                                                                                                                              |
| 1   | 0x0002 | `HIDE_FILTRATION`                    | Hide filtration menu in main menu                                                                                                                         |
| 2   | 0x0004 | `HIDE_LIGHTING`                      | Hide lighting menu in main menu                                                                                                                           |
| 3   | 0x0008 | `HIDE_AUX_RELAYS`                    | Hide auxiliary relay adjustment menu in main menu                                                                                                         |
| 4   | 0x0010 | `MBMSK_VO_HIDE_EXTRA_REGS`           | Hide additional register adjustment option in installer menu                                                                                              |
| 5   | 0x0020 | `MBMSK_VO_HIDE_RELAY_CONFIG`         | Hide relay configuration option in installer menu                                                                                                         |
| 6   | 0x0040 | `MBMSK_VO_SLOW_FILTER_HIDRO_LEVEL`   | Enable slow filtering of the hydrolysis level when a pH module is installed (especially important when acid/base dosing is close to the hydrolysis probe) |
| 7   | 0x0080 | `MBMSK_VO_HIDE_SALINITY_MAIN_WINDOW` | Hide salinity measurement on the main screen                                                                                                              |
| 8   | 0x0100 | `MBMSK_VO_SHOW_SPECIAL_REGS`         | Show special registers configuration menu in installer menu                                                                                               |
| 9   | 0x0200 | `SHOW_HID_SHUTDOWN_BY_TEMPERATURE`   | Show hydrolysis shutdown by temperature option                                                                                                            |
| 10  | 0x0400 | `SHOW_CELL_SELECTION`                | Enable access to cell selection menu from the service menu                                                                                                |
| 11  | 0x0800 | `SHOW_PUMP_TYPE`                     | Show filtration pump type selection option (normal, three-speed, etc.)                                                                                    |
| 12  | 0x1000 | `SHOW_QUICK_MENU`                    | Show quick access menu instead of conventional menu when SET is pressed from main display                                                                 |
| 13  | 0x2000 | `SHOW_OXI_MAIN_DATA_SCREEN`          | Show main display screen in OXI style                                                                                                                     |
| 14  | 0x4000 | `SHOW_INSTALLER_MENU`                | Show installer menu in the main menu without requiring a password                                                                                         |
| 15  | 0x8000 | `SHOW_FACTORY_MENU`                  | Show factory menu in the main menu without requiring a password                                                                                           |

---

### Register 0x0606 - `MBF_PAR_UICFG_VISUAL_OPTIONS_EXT`

Extended visual options bitmask:

| Bit  | Mask   | Name                                | Description                                                   |
| ---- | ------ | ----------------------------------- | ------------------------------------------------------------- |
| 0    | 0x0001 | `MBMSK_VOE_SHOW_PNEUMATIC_VALVE`    | Show the pneumatic valve option                               |
| 1    | 0x0002 | `MBMSK_VOE_HIDE_AUX_REL_DEPENDENCY` | Hide auxiliary relay dependency option                        |
| 2    | 0x0004 | `MBMSK_VOE_SHOW_BESGO_NAME`         | Show "Besgo" instead of "Pneumatic" in pneumatic valve titles |
| 3-15 | —      | Reserved                            |

---

### Register 0x0607 - `MBF_PAR_UICFG_MACH_VISUAL_STYLE`

Extension of registers 0x0600 and 0x0605.

**Low byte (bits 0-7):** Color/style for the generic machine type. Uses the same values as `MBF_PAR_UICFG_MACHINE` (0x0600).

**High byte (bits 8-15):** Supplementary configuration for hydrolysis display units:

| Bit  | Mask   | Name                              | Description                                                              |
| ---- | ------ | --------------------------------- | ------------------------------------------------------------------------ |
| 8-12 | —      | Reserved                          |
| 13   | 0x2000 | `MBMSK_VS_FORCE_UNITS_GRH`        | Force display of hydrolysis/electrolysis in grams per hour (g/h)         |
| 14   | 0x4000 | `MBMSK_VS_FORCE_UNITS_PERCENTAGE` | Force display of hydrolysis/electrolysis in percentage (%)               |
| 15   | 0x8000 | `MBMSK_ELECTROLISIS`              | In generic mode, display the word "electrolysis" instead of "hydrolysis" |

**Logic for determining the hydrolysis display units:**

1. If `MBMSK_VS_FORCE_UNITS_PERCENTAGE` is set → display "%"
2. Else if `MBMSK_VS_FORCE_UNITS_GRH` is set → display "gr/h"
3. Otherwise, check machine type:
   - `MACH_HIDROLIFE` (1) or `MACH_BIONET` (4) → "gr/h"
   - `MACH_GENERIC` (9) with `MBMSK_ELECTROLISIS` set → "gr/h"
   - All other cases → "%"

---

### Registers 0x0608-0x060B - `MBF_PAR_UICFG_MACH_NAME_BOLD_0..3`

Four registers storing an ASCIIZ string of up to 8 characters for the **bold** part of the startup title when machine type is set to generic.

> Note: Only lowercase letters (a-z) may be used. Uppercase letters, symbols, and numbers are not allowed.

---

### Registers 0x060C-0x060F - `MBF_PAR_UICFG_MACH_NAME_LIGHT_0..3`

Four registers storing an ASCIIZ string of up to 8 characters for the **normal weight** part of the startup title when machine type is set to generic.

> Note: Only lowercase letters (a-z) may be used. Uppercase letters, symbols, and numbers are not allowed.
