"""Position-independent RH850/P1H-C patch signatures for Valeo MFK3 (`KS_PASSIVE` + All 9 `FeC`/`SWaP` + Key DTCs + `XCP` on `CAN0`)."""

from __future__ import annotations

from ...core.pattern import PatchEdit, PatchSiteSpec


MFK3_PATCH_SITES: tuple[PatchSiteSpec, ...] = (
    # =========================================================================
    # Group 1: Core KS_PASSIVE (`group="ks_core"`, 5 sites)
    # =========================================================================
    PatchSiteSpec(
        site_id="cnt_load_from_nvm",
        group="ks_core",
        symbol_name="cnt_LoadFromNvM",
        reference_va=0x0012B3DC,
        alignment=2,
        stock_pattern="3e 06 ?? ?? ?? ??  6e 98 6f 08 c8 9a d3 09  64 0f ?? ??  7f 00",
        patched_pattern="3e 06 ?? ?? ?? ??  8e 03 8f 03 00 00 00 00  64 07 ?? ??  7f 00",
        edits=(
            PatchEdit(0x06, bytes.fromhex("6e986f08c89ad309640f"), bytes.fromhex("8e038f03000000006407")),
        ),
        ru_desc=(
            "Обнуление счётчика KS в ОЗУ (gp+0x38C) и буфере DID 0x03DE (ep+14..15) без порчи r10==1 "
            "-> вход в cnt_StatePassive и активный сброс DTC U110100 (0xEA6100/6200/6400)"
        ),
        en_desc=(
            "Zero KS RAM counter (gp+0x38C) & DID 0x03DE shadow (ep+14..15) without clobbering r10==1 "
            "-> enters cnt_StatePassive & actively clears U110100 Dem DTCs (0xEA6100/6200/6400)"
        ),
    ),
    PatchSiteSpec(
        site_id="cnt_store_counter",
        group="ks_core",
        symbol_name="cnt_StoreCounter",
        reference_va=0x0012B3F0,
        alignment=2,
        stock_pattern="06 08 88 0a  3e 06 ?? ?? ?? ??  64 37 ?? ??  8e 0b 8f 33  7f 00",
        patched_pattern="00 00 00 00  3e 06 ?? ?? ?? ??  64 07 ?? ??  8e 03 8f 03  7f 00",
        edits=(
            PatchEdit(0x00, bytes.fromhex("0608880a"), bytes.fromhex("00000000")),
            PatchEdit(0x0A, bytes.fromhex("6437"), bytes.fromhex("6407")),
            PatchEdit(0x0E, bytes.fromhex("8e0b8f33"), bytes.fromhex("8e038f03")),
        ),
        ru_desc="Запись только 0x0000 при любом сохранении счётчика KS в ОЗУ / теневой буфер NvM 0x3C",
        en_desc="Force 0x0000 on every KS counter store into RAM and NvM 0x3C shadow buffer",
    ),
    PatchSiteSpec(
        site_id="cnt_boot_wait_timer",
        group="ks_core",
        symbol_name="cnt_BootWait+0x24",
        reference_va=0x0012B640,
        alignment=2,
        stock_pattern=(
            "80 07 21 00  ?? ?? ?? ??  61 52 ea 1d  ?? ?? ?? ??  61 52 aa 1d  ?? ?? ?? ??  "
            "e4 9f ?? ??  44 57 ?? ??  44 07 ?? ??  44 57 ?? ??  20 0e 30 75  13 06 e1 ff"
        ),
        patched_pattern=(
            "80 07 21 00  ?? ?? ?? ??  61 52 ea 1d  ?? ?? ?? ??  61 52 aa 1d  ?? ?? ?? ??  "
            "e4 9f ?? ??  44 57 ?? ??  44 07 ?? ??  44 07 ?? ??  20 0e 30 75  13 06 e1 ff"
        ),
        edits=(
            PatchEdit(0x24, bytes.fromhex("4457"), bytes.fromhex("4407")),
        ),
        ru_desc=(
            "Отключение автономного таймера ожидания шлюза (5 мин + 60 мин * 30) в cnt_BootWait "
            "(защита NvM 0x3C от ежечасного износа на стенде / в авто без CP)"
        ),
        en_desc=(
            "Disable standalone 5-min / 60-min no-gateway countdown timer in cnt_BootWait "
            "(prevents hourly NvM 0x3C DataFlash wear on bench or non-CP vehicles)"
        ),
    ),
    PatchSiteSpec(
        site_id="cnt_trigger_error",
        group="ks_core",
        symbol_name="cnt_TriggerError",
        reference_va=0x0012B79E,
        alignment=2,
        stock_pattern=(
            "80 07 61 00  06 e8 dd 00  ?? ?? ?? ??  65 ea f2 05  e0 e9 a2 0d  "
            "04 0f ?? ??  62 0a e2 05  02 0a  64 ef ?? ??  44 0f ?? ??  ?? ?? ?? ??  40 06 7f 00"
        ),
        patched_pattern=(
            "7f 00 00 00  06 e8 dd 00  ?? ?? ?? ??  65 ea f2 05  e0 e9 a2 0d  "
            "04 0f ?? ??  62 0a e2 05  02 0a  64 ef ?? ??  44 0f ?? ??  ?? ?? ?? ??  40 06 7f 00"
        ),
        edits=(
            PatchEdit(0x00, bytes.fromhex("80076100"), bytes.fromhex("7f000000")),
        ),
        ru_desc=(
            "Блокировка всех 9 триггеров ошибок KS (неверный MAC 80 02 от J533, Virgin IKA, NvM, ICUMC) "
            "-> нет перезаписи NvM 0x3C на каждом зажигании и нет блокировки 0x23/0x25"
        ),
        en_desc=(
            "Neutralize all 9 KS error triggers (J533 80 02 MAC mismatch, Virgin IKA, NvM, ICUMC) "
            "-> eliminates per-ignition NvM 0x3C writes and 0x23/0x25 lockouts"
        ),
    ),
    PatchSiteSpec(
        site_id="ks_get_status",
        group="ks_core",
        symbol_name="KS_GetStatus+0x1E",
        reference_va=0x0012B7EC,
        alignment=2,
        stock_pattern=(
            "84 07 ?? ?? ?? ??  e0 09 e2 05  33 06 ?? ?? ?? ??  f3 09 ba 05  02 52 7f 00  "
            "a4 07 ?? ?? ?? ??  01 06 e1 ff  e1 57 00 00  7f 00"
        ),
        patched_pattern=(
            "84 07 ?? ?? ?? ??  e0 09 e2 05  33 06 ?? ?? ?? ??  f3 09 ba 05  02 52 7f 00  "
            "a4 07 ?? ?? ?? ??  00 52 00 00  00 00 00 00  7f 00"
        ),
        edits=(
            PatchEdit(0x1E, bytes.fromhex("0106e1ffe1570000"), bytes.fromhex("0052000000000000")),
        ),
        ru_desc=(
            "Принудительный возврат 0 (KS_PASSIVE) после завершения стартовой инициализации (2 = NOT_READY) "
            "-> KN_Kamera.Kamera_KS_aktiv = 0"
        ),
        en_desc=(
            "Force return 0 (KS_PASSIVE) once boot sync (2 = NOT_READY) completes "
            "-> KN_Kamera.Kamera_KS_aktiv = 0"
        ),
    ),

    # =========================================================================
    # Group 2: Unconditional Activation of All 9 FeC / SWaP Codes (`group="fec_unlock"`, 4 sites)
    # =========================================================================
    PatchSiteSpec(
        site_id="fec_runtime_gate",
        group="fec_unlock",
        symbol_name="SWaP_CheckSlot+0x2C",
        reference_va=0x0004A594,
        alignment=2,
        stock_pattern=(
            "06 0e ff ff  69 0a  b9 fd  e5 37 40 02  21 06 ?? ?? ?? ??  c1 31  a6 57 ff ff  40 06 3f 00"
        ),
        patched_pattern=(
            "06 0e ff ff  69 0a  b9 fd  e5 37 40 02  21 06 ?? ?? ?? ??  c1 31  00 52 00 00  40 06 3f 00"
        ),
        edits=(
            PatchEdit(0x14, bytes.fromhex("a657ffff"), bytes.fromhex("00520000")),
        ),
        ru_desc=(
            "Безусловная разблокировка шлюза FUN_0004A57C(1..9) -> 0 (ENABLED) с первой мс запуска: "
            "включает VZE (100E0F00) и все 6 каналов ADAS/PE2/EyeQ4 (100E1000..100E1700), не трогая XCP (0x81)"
        ),
        en_desc=(
            "Unconditionally return 0 (ENABLED) in FUN_0004A57C(1..9) from boot ms 0: "
            "activates VZE (100E0F00) and all ADAS/PE2/EyeQ4 slots (100E1000..100E1700), keeping XCP (0x81) intact"
        ),
    ),
    PatchSiteSpec(
        site_id="fec_fes_sync_verdict",
        group="fec_unlock",
        symbol_name="FES_IsFecValid+0x26",
        reference_va=0x0013AC92,
        alignment=2,
        stock_pattern=(
            "80 07 e1 10  06 e8 07 e0  ?? ?? ?? ??  ca 0e 4f 00  01 06 b1 ff  e2 df 00 00  "
            "e0 e1 e2 05  1d 30  ?? ?? ?? ??  5c 57 00 00  1b 50  40 06 ff 10"
        ),
        patched_pattern=(
            "80 07 e1 10  06 e8 07 e0  ?? ?? ?? ??  ca 0e 4f 00  01 06 b1 ff  e2 df 00 00  "
            "e0 e1 e2 05  1d 30  ?? ?? ?? ??  5c 57 00 00  01 52  40 06 ff 10"
        ),
        edits=(
            PatchEdit(0x26, bytes.fromhex("1b50"), bytes.fromhex("0152")),
        ),
        ru_desc=(
            "Регистрация всех 9 кодов FeC в таблице FES и возврат 1 (VALID -> 8 ENABLED) в FUN_0013AC92: "
            "штатно синхронизирует зеркало NvM 0x53 (disabled=0) один раз без циклической записи DataFlash"
        ),
        en_desc=(
            "Register all 9 FeC codes in FES RAM and return 1 (VALID -> 8 ENABLED) in FUN_0013AC92: "
            "cleanly syncs NvM 0x53 mirror (disabled=0) once without DataFlash write churn"
        ),
    ),
    PatchSiteSpec(
        site_id="fec_uds_read_status",
        group="fec_unlock",
        symbol_name="FES_ReadUdsList+0x50",
        reference_va=0x0013C5C6,
        alignment=2,
        stock_pattern=(
            "1d f0 70 c8 1c 30 44 ca 80 cc d9 00 da c9  bf ff 7a f4  59 57 00 00  1d f0 70 08 1c 30"
        ),
        patched_pattern=(
            "1d f0 70 c8 1c 30 44 ca 80 cc d9 00 da c9  00 56 ff 00  59 57 00 00  1d f0 70 08 1c 30"
        ),
        legacy_patched_patterns=(
            "1d f0 70 c8 1c 30 44 ca 80 cc d9 00 da c9  00 56 4f 00  59 57 00 00  1d f0 70 08 1c 30",
        ),
        edits=(
            PatchEdit(0x0E, bytes.fromhex("bfff7af4"), bytes.fromhex("0056ff00")),
        ),
        ru_desc=(
            "Отображение полного заводского статуса 0xFF (0xB0 | 0x4F: Configuration OK + Functions available + Valid) "
            "для всех 9 кодов FeC по UDS (DID 0x3C00 в ODIS / VCDS / OBDeleven) без модификации NvM 0x49"
        ),
        en_desc=(
            "Report full factory status 0xFF (0xB0 | 0x4F: Configuration OK + Functions available + Valid) "
            "for all 9 FeCs in UDS SWaP diagnostic list (DID 0x3C00 in ODIS / VCDS / OBDeleven) without altering NvM 0x49"
        ),
    ),
    PatchSiteSpec(
        site_id="fec_suppress_fsc_dtc",
        group="fec_unlock",
        symbol_name="FES_CheckFscDtc+0x12",
        reference_va=0x0013CEE0,
        alignment=2,
        stock_pattern=(
            "dd 39 04 42  ?? ?? ?? ??  a4 07 ?? ?? ?? ??  20 36 00 01  01 3a  "
            "84 07 ?? ?? ?? ??  ?? ?? ?? ??  21 06 ?? ?? ?? ??"
        ),
        patched_pattern=(
            "dd 39 04 42  ?? ?? ?? ??  a4 07 ?? ?? ?? ??  20 36 00 01  00 3a  "
            "84 07 ?? ?? ?? ??  ?? ?? ?? ??  21 06 ?? ?? ?? ??"
        ),
        edits=(
            PatchEdit(0x12, bytes.fromhex("013a"), bytes.fromhex("003a")),
        ),
        ru_desc=(
            "Передача PASSED (0) для события Dem 0x0100 в FUN_0013CE72 (исключает ошибку неверного FSC, "
            "если в б/у камере остались битые записи в NvM 0x49)"
        ),
        en_desc=(
            "Report PASSED (0) for Dem event 0x0100 in FUN_0013CE72 (prevents/clears Invalid FSC fault "
            "if a donor camera had corrupted FSC entries in NvM 0x49)"
        ),
    ),

    # =========================================================================
    # Group 3: Optional Virgin Key DTC Suppression (`group="key_dtcs"`, 1 site)
    # =========================================================================
    PatchSiteSpec(
        site_id="km_report_key_dtcs",
        group="key_dtcs",
        symbol_name="km_ReportKeyDtcs",
        reference_va=0x0012CCA6,
        alignment=2,
        stock_pattern=(
            "80 07 21 00  24 9f ?? ??  21 06 ?? ?? ?? ??  e1 99  ca 05 01 32  ?? ?? ?? ??  "
            "24 9f ?? ??  21 06 ?? ?? ?? ??  e1 99  ca 05 00 32  ?? ?? ?? ??  "
            "a4 0f ?? ??  81 0a  c1 0e 01 00  a1 36 01 00  ?? ?? ?? ??  "
            "a4 0f ?? ??  c1 0e 01 00  a1 36 01 00  ?? ?? ?? ??  40 06 3f 00"
        ),
        patched_pattern=(
            "80 07 21 00  24 9f ?? ??  21 06 ?? ?? ?? ??  e1 99  00 00 00 32  ?? ?? ?? ??  "
            "24 9f ?? ??  21 06 ?? ?? ?? ??  e1 99  ca 05 00 32  ?? ?? ?? ??  "
            "a4 0f ?? ??  81 0a  c1 0e 01 00  00 32 00 00  ?? ?? ?? ??  "
            "a4 0f ?? ??  c1 0e 01 00  00 32 00 00  ?? ?? ?? ??  40 06 3f 00"
        ),
        edits=(
            PatchEdit(0x10, bytes.fromhex("ca050132"), bytes.fromhex("00000032")),
            PatchEdit(0x36, bytes.fromhex("a1360100"), bytes.fromhex("00320000")),
            PatchEdit(0x46, bytes.fromhex("a1360100"), bytes.fromhex("00320000")),
        ),
        ru_desc=(
            "[Опция Virgin] Подавление ключевых DTC 0xD10000 / 0xD20000 / 0xD30000 на новой (неадаптированной) "
            "камере без изменения VCRN и кэша RSA в NvM 0x49"
        ),
        en_desc=(
            "[Virgin Option] Suppress unadapted key DTCs 0xD10000 / 0xD20000 / 0xD30000 on Virgin cameras "
            "without altering VCRN or NvM 0x49 RSA cache"
        ),
    ),

    # =========================================================================
    # Group 4: Optional Engineering XCP Activation on CAN0 (`group="xcp_can0"`, 1 site)
    # =========================================================================
    PatchSiteSpec(
        site_id="xcp_boot_enable_can0",
        group="xcp_can0",
        symbol_name="Xcp_BootControl+0x0C",
        reference_va=0x00064AE8,
        alignment=2,
        stock_pattern=(
            "80 07 21 00  20 36 81 00  ?? ff ?? ??  20 36 aa 00  ?? ff ?? ??  40 06 3f 00"
        ),
        patched_pattern=(
            "80 07 21 00  20 36 81 00  ?? ff ?? ??  20 36 55 00  ?? ff ?? ??  40 06 3f 00"
        ),
        edits=(
            PatchEdit(0x0C, bytes.fromhex("2036aa00"), bytes.fromhex("20365500")),
        ),
        ru_desc=(
            "[Инженерная опция] Активация XCP на шине CAN0 при старте (Xcp_SetControlMode(0x55): "
            "пины 3/4 T12a, 500 кбит/с, Ext ID 0x1BFE7E01 -> 0x1BFE7E00; обычным пользователям не нужно)"
        ),
        en_desc=(
            "[Engineering Option] Enable XCP on CAN0 bus at boot (Xcp_SetControlMode(0x55): "
            "T12a pins 3/4, 500 kbit/s, Ext ID 0x1BFE7E01 -> 0x1BFE7E00; not needed for normal users)"
        ),
    ),
)
