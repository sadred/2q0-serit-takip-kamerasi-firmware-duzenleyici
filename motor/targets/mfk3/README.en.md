<div align="center">

# `0x00A5` • Valeo MFK3 (`2Q0 980 653`)
### Target Module Documentation for **Schutz-Kaput** (`Renesas RH850/P1H-C` • SW `13xx` / `14xx`)

**[← Back to `Schutz-Kaput` Main Page](../../README.en.md)** • **[🇷🇺 Читать на русском (`README.md`)](README.md) | 🇬🇧 English**

</div>

---

> [!CAUTION]
> **RISK REMINDER:**  
> Everything that happens to the camera afterwards is 100% your responsibility. This script only prepares files locally and does NOT control the flashing process. Always save a complete backup of your original Flash and `EEPROM` / `NvM` first. **Bricked units CANNOT be recovered over OBD — recovery is impossible without a hardware bench programmer!** See [`LICENSE.md`](../../LICENSE.md) for full terms.

---

## Supported Hardware & Input Formats

* **Control Unit:** **Valeo MFK3** front driver assistance camera (`2Q0 980 653` across hardware/software suffixes), diagnostic address **`0x00A5`**.
* **Hardware Architecture:** **`Renesas RH850/P1H-C` (`R7F701372A`)** host MCU + **`Mobileye EyeQ4`** vision SoC (`DB_03`).
* **Application Firmware (`MEAPP`):** **`13xx` / `14xx`** release branches.
* **Accepted Input Files:**
  * factory encrypted **`.frf`** and unpacked **`.odx-f` / `.odx` / `.pdx`** containers;
  * standalone extracted **`DB_01FLASHDATA.bin`** (`0x00048000..0x001FFFFF`, `~1.72 MiB`);
  * full bench programmer dumps: **`Bank 0` (`2 MiB`)**, **`Dual-Bank` (`4 MiB`)**, and linear **`9.84 MiB` / `10 MiB`** dumps.

---

## What the Patcher Does on `Valeo MFK3`

### 1. Component Protection Bypass (`KS_PASSIVE`, 5 sites in `DB_01`)
* Switches `Komponentenschutz` into passive mode, removing functional ADAS lockouts on retrofitted vehicles.
* Protects **`NvM 0x3C`** non-volatile memory from repeated CP error-counter write wear.
* **Built-in safety guards:**
  * verifies and preserves the 8-byte cold-boot application header (`0xAA000000` + `0x00048200` @ `0x00048000`);
  * automatically rejects accidental attempts to patch the **`0220_FBL`** bootloader updater (`~222 KB`) as `MEAPP`.

### 2. All 9 `FeC` / `SWaP` Features Unlocked (4 sites in `DB_01`)
* Enables all supported camera features at runtime (enabled by default; pass `--no-fecs` to skip).
* Reports the full factory **`0xFF`** status byte across all 9 slots in **`DID 0x3C00`** (*Status of all SWaP functions* in `ODIS`: `Release code: available`, `Cancellation: no`, `Individualization characteristic: valid`, `Preconditions met: Condition met`, `Configuration: OK`, `Functions: available`, `Authentication: Condition met`):

| `FeC` ID | Feature Description (`Valeo MFK3`) |
| :---: | :--- |
| `100E0F00` | Traffic Sign Recognition (**`VZE`**) |
| `100E1000` | Core Driver Assistants (**`Lane Assist`**, High Beam Assist **`FLA`**, **`pACC`**) |
| `100E1100` | Extended Lane Guidance |
| `100E1200` | Additional ADAS Feature Channel `#1` |
| `100E1300` | Additional ADAS Feature Channel `#2` |
| `100E1400` | Additional ADAS Feature Channel `#3` |
| `100E1500` | Additional ADAS Feature Channel `#4` |
| `100E1600` | Reserved Feature Slot `#1` |
| `100E1700` | Reserved Feature Slot `#2` |

### 3. Unadapted Key DTC Suppression (`--suppress-key-dtcs`, optional)
* Suppresses missing basic/individual CP key DTCs — useful on brand-new Virgin cameras that have never had CP keys adapted.

### 4. Engineering Option: `XCP` on `CAN0` (`--enable-xcp-can0`, OFF by default)
* **Ordinary users do NOT need this option for retrofitting.**
* Switches `Xcp_BootControl` into active mode `0x55` at startup on **`CAN0`**:
  * `T12a` connector: pin **`3 = CAN-H`**, pin **`4 = CAN-L`**, **`500 kbit/s`**;
  * `Extended 29-bit CAN`: master TX **`0x1BFE7E01`** → camera TX **`0x1BFE7E00`**.

### 5. Hardware-Safe `ODIS-E` Package Builder (`PART1` + `PART2`)
* Packs `DB_01` **strictly uncompressed (`method=00`, `<SECURITY-METHOD>SIG_SHA1-RSA1024_S</SECURITY-METHOD>`)**, preventing `0220` bootloader LZSS overlapping-RLE faults (`7F 36 72` / `generalProgrammingFailure`).
* Assigns distinct internal XML IDs (`_KS_FEC_PART1_S` and `_KS_FEC_PART2_S`) so `ODIS-E` (`MCD-3D`) never collides when loading both containers simultaneously.

---

## Two-Step `ODIS-E` Flashing (`PART1` → `PART2`)

When generating ODX containers for `ODIS-E`, two subfolders (`PART1` and `PART2`) are created:

1. **Step 1 (`PART1`):** flash the container inside `PART1`. At the very end (`RoutineControl 31 01 02 02`), `ODIS-E` will report an expected signature verification error on the patched `DB_01` block — **do not panic and do not turn off ignition**; the patched firmware is already written to flash.
2. **Step 2 (`PART2`):** without turning off ignition, immediately flash the container inside `PART2` (containing stock signed `DB_30` + `DB_04`). Flashing will complete **100% green** (`71 01 02 02 01`) and return the camera from bootloader to normal operating mode.

---

## `XCP` on `CAN0` Protocol Reference (Engineering Cheat-Sheet)

When built with `--enable-xcp-can0`, the camera enables its standard **ASAM MCD-1 XCP v1.0** slave stack (`EB tresos Xcp`) at boot on the private **`CAN0`** bus (*Fusion CAN*, `T12a` connector: pin `3 = CAN-H`, pin `4 = CAN-L`, Classical CAN 2.0B `500 kbit/s` — **separate physical pair from the vehicle `CAN1` bus on pins `1`/`2`!**):

* **CAN IDs (`Extended 29-bit`):** master TX **`0x1BFE7E01`** → camera TX **`0x1BFE7E00`**.
* **Framing:** **`Little-Endian` (Intel)** byte order, `MAX_CTO = 8` B, `MAX_DTO = 8` B, *Slave Block Mode* enabled.
* **Authentication (`Seed & Key`):** **none** — `GET_SEED (0xF8)` and `UNLOCK (0xF7)` are compiled out; full 32-bit `RH850` address-space reads (`CodeFlash`, `DataFlash`, `RAM`, `MMIO`) and `RAM` writes are immediately available right after `CONNECT`.

> [!NOTE]
> In **ASAM XCP / CCP** (just like in **UDS** `0x34 RequestDownload` / `0x35 RequestUpload`), transfer direction is defined relative to the Master-above-Slave hierarchy: **`UPLOAD` = READ from ECU up to PC**, whereas **`DOWNLOAD` = WRITE from PC down into ECU RAM**.

### Core Commands & Worked CAN Frames

| Command (`PID`) | Request (`0x1BFE7E01`) | Response (`0x1BFE7E00`) | Description |
| :--- | :--- | :--- | :--- |
| **`CONNECT` (`0xFF`)** | `FF 00` | `FF 04 40 08 08 00 01 01` | Open session (`Mode = 00`; `0x40` = Intel LE + Slave Block Mode, `CTO/DTO = 8`, XCP `1.0`) |
| **`GET_STATUS` (`0xFD`)** | `FD` | `FF <sess> 00 00 <cfg_LE>` | Query session status (`prot = 0x00` — all resources unlocked) |
| **`SHORT_UPLOAD` (`0xF4`)** | `F4 04 00 00 00 80 04 00` | `FF 00 00 00 AA` | **Read (`ECU → PC`):** single-frame read of `1..7` B from `0x00048000` (`LE: 00 80 04 00`) |
| **`SET_MTA` (`0xF6`)** | `F6 00 00 00 2C 07 E9 FE` | `FF` | Set `MTA` pointer (example: `0xFEE9072C` = `Xcp_ControlMode`) |
| **`UPLOAD` (`0xF5`)** | `F5 10` | Stream of `FF <up to 7 B>...` | **Read (`ECU → PC`):** block-read `1..255` B starting at `MTA` (auto-incrementing) |
| **`DOWNLOAD` (`0xF0`)** | `F0 04 <4 bytes>` | `FF` | **Write (`PC → ECU`):** write `1..6` B to `RAM` at `MTA` (up to `12` B with `0xEF`) |
| **`DOWNLOAD_MAX` (`0xEE`)** | `EE <7 bytes>` | `FF` | **Write (`PC → ECU`):** write `7` B to `RAM` at `MTA` (auto-incrementing) |
| **`SYNCH` (`0xFC`)** | `FC` | `FE 00` | Resynchronize command processor (`ERR_CMD_SYNCH`) |
| **`DISCONNECT` (`0xFE`)** | `FE` | `FF` | Cleanly close the `XCP` session |

* **Also supported:** `GET_COMM_MODE_INFO (0xFB)`, `GET_ID (0xFA)`, `TRANSPORT_LAYER_CMD (0xF2)`, and full **`Dynamic DAQ`** cyclic measurement allocation (`FREE_DAQ 0xD6`, `ALLOC_DAQ 0xD5`, `ALLOC_ODT 0xD4`, `ALLOC_ODT_ENTRY 0xD3`, `SET_DAQ_PTR 0xE2`, `WRITE_DAQ 0xE1`, `SET_DAQ_LIST_MODE 0xE0`, `GET_DAQ_LIST_MODE 0xDF`, `START_STOP_DAQ_LIST 0xDE`, `START_STOP_SYNCH 0xDD`, `GET_DAQ_CLOCK 0xDC`, `GET_DAQ_PROCESSOR_INFO 0xDA`, `GET_DAQ_RESOLUTION_INFO 0xD9`, `GET_DAQ_EVENT_INFO 0xD7`). Flash programming XCP commands (`PROGRAM_* 0xCF..0xD2`) are disabled.
* **Protocol Specifications & Open-Source Client:**
  * [ASAM MCD-1 XCP Official Wiki](https://www.asam.net/standards/detail/mcd-1-xcp/wiki/)
  * [Vector — XCP Reference Book](https://www.vector.com/int/en/know-how/protocols/xcp-measurement-and-calibration-protocol/xcp-book/)
  * [pyXCP — Python XCP Master Library (`christoph2/pyxcp`)](https://github.com/christoph2/pyxcp)

---

## CLI Examples for `mfk3`

```bash
# Inspect a factory container (.frf / .odx-f) or bench dump
python3 ks_patcher.py -l en -t mfk3 inspect FL_2Q0980653J_1423_MEAPP_V001_S.frf

# Build two-step ODIS-E PART1 + PART2 packages (KS_PASSIVE + all 9 FeCs)
python3 ks_patcher.py -l en -t mfk3 patch FL_2Q0980653J_1423_MEAPP_V001_S.frf --build-odx ./ODIS_MFK3_READY

# Build ODX from raw DB_01 using a factory .frf / .odx-f template
python3 ks_patcher.py -l en -t mfk3 patch DB_01FLASHDATA.bin --template-odx FL_2Q0980653J_1423_MEAPP_V001_S.frf --build-odx ./ODIS_MFK3_READY

# Patch a bench programmer dump (Bank 0 / Dual-Bank)
python3 ks_patcher.py -l en -t mfk3 patch Bank0_dump.bin -o Bank0_patched.bin

# Losslessly revert a patched dump back to 100% factory stock
python3 ks_patcher.py -l en -t mfk3 patch Bank0_patched.bin --restore-stock -o Bank0_restored.bin
```
