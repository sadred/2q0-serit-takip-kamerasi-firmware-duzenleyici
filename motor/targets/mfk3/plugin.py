"""Valeo MFK3 (`2Q0 980 653`, `0x00A5`) ECU Target Plugin — `KS_PASSIVE` + All 9 `FeC`/`SWaP` + `ODX`."""

from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import tempfile
import zlib

from ...core.containers import (
    BUILTIN_FRF_KEY_SHA256,
    OdxBlockEntry,
    get_frf_key,
    lzss_a0_compress,
    lzss_a0_decompress,
    parse_odx_container,
)
from ...core.i18n import Style, tr
from ...core.pattern import PatchSiteSpec, SiteMatch, parse_masked_pattern, scan_masked
from ...core.target_base import (
    EcuTargetPlugin,
    PatchOptions,
    TargetInspection,
    TargetPatchResult,
)
from .constants import (
    DB01_BASE_VA,
    DB01_EXPECTED_HEADER_8B,
    DB01_HEADER_ENTRY,
    DB01_HEADER_MAGIC,
    DB01_MAX_REGION_SIZE,
    DB01_MIN_VALID_APP_SIZE,
    DB01_SW1423_SIZE,
    FBL_UPDATER_DB01_SIZE,
    KNOWN_DB01_CRCS,
    MFK3_EXPECTED_DUMP_SIZES,
    MFK3_SWAP_FECS,
)
from .loader import (
    LoadedMfk3Image,
    build_mfk3_part1_part2_odx,
    find_sibling_mfk3_template_odx,
    format_kind_label,
    load_mfk3_source,
    resolve_mfk3_sw_version,
)
from .signatures import MFK3_PATCH_SITES


def _extract_gp_tp_bases(db01: bytes) -> tuple[int | None, int | None]:
    """Extract RH850 `gp` (`r4`) and `tp` (`r5`) base registers from `_start` (`0x00048200`)."""
    gp_base: int | None = None
    tp_base: int | None = None
    if len(db01) < 0x260:
        return None, None
    # Scan startup window 0x200..0x250 for `mov imm32, r4` (`24 06 <imm32>`) / `mov imm32, r5` (`25 06 <imm32>`)
    # or `movhi hi, r0, r4; movea lo, r4, r4` (`40 26 <hi> 24 26 <lo>`)
    win = db01[0x200:0x258]
    for off in range(0, len(win) - 8, 2):
        h0 = struct.unpack_from("<H", win, off)[0]
        if h0 == 0x0624:
            gp_base = struct.unpack_from("<I", win, off + 2)[0]
        elif h0 == 0x0625:
            tp_base = struct.unpack_from("<I", win, off + 2)[0]
        elif h0 == 0x2640 and struct.unpack_from("<H", win, off + 4)[0] == 0x2624:
            hi = struct.unpack_from("<H", win, off + 2)[0]
            lo = struct.unpack_from("<h", win, off + 6)[0]
            gp_base = ((hi << 16) + lo) & 0xFFFFFFFF
        elif h0 == 0x2E40 and struct.unpack_from("<H", win, off + 4)[0] == 0x2E25:
            hi = struct.unpack_from("<H", win, off + 2)[0]
            lo = struct.unpack_from("<h", win, off + 6)[0]
            tp_base = ((hi << 16) + lo) & 0xFFFFFFFF
    return gp_base, tp_base


def _group_state(sites: list[SiteMatch], group: str) -> str:
    grp = [m for m in sites if m.spec.group == group]
    if not grp:
        return "n/a"
    states = {m.state for m in grp}
    if states == {"stock"}:
        return "stock"
    if states == {"patched"}:
        return "patched"
    if states <= {"stock", "patched"}:
        return "partial"
    return "unknown"


def _inspect_loaded_mfk3(loaded: LoadedMfk3Image) -> TargetInspection:
    db01 = loaded.db01_bytes
    magic, entry = (struct.unpack_from("<II", db01, 0) if len(db01) >= 8 else (0, 0))
    header_ok = len(db01) >= 8 and magic == DB01_HEADER_MAGIC and entry == DB01_HEADER_ENTRY
    gp_base, tp_base = _extract_gp_tp_bases(db01)

    # Compute trimmed length (for 2 MiB / 4 MiB bank dumps where 0x1FFF18..0x1FFFFF is 0xFF flash padding)
    if (
        len(db01) == DB01_MAX_REGION_SIZE
        and db01[DB01_SW1423_SIZE:] == b"\xFF" * (DB01_MAX_REGION_SIZE - DB01_SW1423_SIZE)
    ):
        trimmed = db01[:DB01_SW1423_SIZE]
    else:
        trimmed = db01

    crc_full = zlib.crc32(db01) & 0xFFFFFFFF
    crc_trim = zlib.crc32(trimmed) & 0xFFFFFFFF
    sha_trim = hashlib.sha256(trimmed).hexdigest()
    known = KNOWN_DB01_CRCS.get(crc_trim) or KNOWN_DB01_CRCS.get(crc_full)

    matches: list[SiteMatch] = []
    for spec in MFK3_PATCH_SITES:
        h_stock = scan_masked(db01, spec.stock_pattern, alignment=spec.alignment)
        h_patch = scan_masked(db01, spec.patched_pattern, alignment=spec.alignment)
        h_legacy: list[int] = []
        for lpat in spec.legacy_patched_patterns:
            h_legacy.extend(scan_masked(db01, lpat, alignment=spec.alignment))
        is_legacy = False
        if len(h_stock) == 1 and len(h_patch) == 0 and len(h_legacy) == 0:
            state = "stock"
            off = h_stock[0]
        elif len(h_stock) == 0 and len(h_patch) == 1 and len(h_legacy) == 0:
            state = "patched"
            off = h_patch[0]
        elif len(h_stock) == 0 and len(h_patch) == 0 and len(h_legacy) == 1:
            state = "patched"
            off = h_legacy[0]
            is_legacy = True
        elif len(h_stock) == 0 and len(h_patch) == 0 and len(h_legacy) == 0:
            matches.append(SiteMatch(spec=spec, state="missing", slice_offset=None, va=None))
            continue
        else:
            matches.append(SiteMatch(spec=spec, state="ambiguous", slice_offset=None, va=None))
            continue

        va = DB01_BASE_VA + off
        info: dict[str, str] = {}
        if is_legacy:
            info["legacy_patched"] = "yes"
        if spec.site_id == "cnt_load_from_nvm":
            ep_addr = struct.unpack_from("<I", db01, off + 2)[0]
            cnt_disp = struct.unpack_from("<h", db01, off + 0x10)[0]
            info["nvm3c_buf_ep"] = f"0x{ep_addr:08X}"
            info["did_03de_ram"] = f"0x{(ep_addr + 14) & 0xFFFFFFFF:08X}..0x{(ep_addr + 15) & 0xFFFFFFFF:08X}"
            if gp_base is not None:
                info["counter_ram"] = f"0x{(gp_base + cnt_disp) & 0xFFFFFFFF:08X}"
        elif spec.site_id == "cnt_boot_wait_timer":
            tmr_disp = struct.unpack_from("<h", db01, off + 0x26)[0]
            if gp_base is not None:
                info["timer_run_ram"] = f"0x{(gp_base + tmr_disp) & 0xFFFFFFFF:08X}"
        elif spec.site_id == "ks_get_status":
            bootwait_va = struct.unpack_from("<I", db01, off + 0x0C)[0]
            info["bootwait_fn_va"] = f"0x{bootwait_va:08X}"
        elif spec.site_id == "fec_runtime_gate":
            swap_ram = struct.unpack_from("<I", db01, off + 0x0E)[0]
            info["nvm53_ram"] = f"0x{swap_ram:08X}"

        matches.append(SiteMatch(spec=spec, state=state, slice_offset=off, va=va, details=info))

    meta = dict(loaded.extra_meta)
    meta["header_magic"] = f"0x{magic:08X}"
    meta["header_entry"] = f"0x{entry:08X}"
    meta["header_valid"] = "yes" if header_ok else "no"
    if gp_base is not None:
        meta["gp_r4"] = f"0x{gp_base:08X}"
    if tp_base is not None:
        meta["tp_r5"] = f"0x{tp_base:08X}"

    fecs_localized = [(code, tr(ru_d, en_d)) for code, ru_d, en_d in MFK3_SWAP_FECS]

    return TargetInspection(
        target_id="mfk3",
        arch_name="Renesas RH850/P1H-C (R7F701372A)",
        source_path=loaded.source_path,
        format_kind=loaded.kind,
        format_label=format_kind_label(loaded.kind),
        slice_name="DB_01FLASHDATA (PE1 @ 0x00048000)",
        slice_start=loaded.db01_slice_start,
        slice_end=loaded.db01_slice_end,
        unpadded_size=len(trimmed),
        crc32_trimmed=crc_trim,
        crc32_full=crc_full,
        sha256_trimmed=sha_trim,
        ks_state=_group_state(matches, "ks_core"),
        fec_state=_group_state(matches, "fec_unlock"),
        key_dtc_state=_group_state(matches, "key_dtcs"),
        xcp_state=_group_state(matches, "xcp_can0"),
        known_label=known,
        metadata=meta,
        sites=matches,
        supported_fecs=fecs_localized,
    )


def _patch_mfk3_db01_bytes(
    db01: bytes,
    *,
    restore_stock: bool,
    activate_all_fecs: bool,
    suppress_key_dtcs: bool,
    enable_xcp_can0: bool = False,
) -> tuple[bytes, list[str]]:
    if len(db01) < 8:
        raise ValueError(tr("Срез DB_01 слишком мал (< 8 байт)", "DB_01 slice is too small (< 8 bytes)"))
    magic, entry = struct.unpack_from("<II", db01, 0)
    if magic != DB01_HEADER_MAGIC or entry != DB01_HEADER_ENTRY:
        raise ValueError(
            tr(
                f"Некорректный заголовок DB_01 @ 0x00048000: magic=0x{magic:08X}, "
                f"entry=0x{entry:08X} (ожидалось 0xAA000000, 0x00048200)",
                f"Invalid DB_01 header @ 0x00048000: magic=0x{magic:08X}, "
                f"entry=0x{entry:08X} (expected 0xAA000000, 0x00048200)",
            )
        )
    if len(db01) < DB01_MIN_VALID_APP_SIZE:
        raise ValueError(
            tr(
                f"Размер DB_01 ({len(db01):,} Б) меньше минимального размера приложения MEAPP (1 МиБ) — "
                f"это загрузчик 0220_FBL?",
                f"DB_01 size ({len(db01):,} B) is smaller than minimum MEAPP size (1 MiB) — "
                f"is this the 0220_FBL bootloader updater?",
            )
        )

    dummy_loaded = LoadedMfk3Image(
        source_path=Path("<memory>"),
        kind="raw_db01",
        full_dump=db01,
        db01_slice_start=0,
        db01_slice_end=len(db01),
        db01_bytes=db01,
    )
    insp_before = _inspect_loaded_mfk3(dummy_loaded)

    want_by_group = {
        "ks_core": "stock" if restore_stock else "patched",
        "fec_unlock": "stock" if (restore_stock or not activate_all_fecs) else "patched",
        "key_dtcs": "stock" if (restore_stock or not suppress_key_dtcs) else "patched",
        "xcp_can0": "stock" if (restore_stock or not enable_xcp_can0) else "patched",
    }

    for m in insp_before.sites:
        grp = m.spec.group
        want = want_by_group[grp]
        if grp in ("ks_core", "fec_unlock") and m.state in ("missing", "ambiguous"):
            # Allow missing fec_unlock ONLY if activate_all_fecs is False and not restoring a patched file
            if grp == "fec_unlock" and want == "stock" and not restore_stock and m.state == "missing":
                continue
            raise ValueError(
                tr(
                    f"Не удалось однозначно найти сигнатуру {m.spec.symbol_name} [{grp}] (статус: {m.state}). "
                    f"Образ не от камеры Valeo MFK3 2Q0 980 653 или неподдерживаемая сборка.",
                    f"Failed to uniquely locate {m.spec.symbol_name} [{grp}] signature (state: {m.state}). "
                    f"Image is not a supported Valeo MFK3 2Q0 980 653 application.",
                )
            )
        if grp == "key_dtcs" and want == "patched" and m.state in ("missing", "ambiguous"):
            raise ValueError(
                tr(
                    f"Запрошено подавление Virgin DTC, но сигнатура {m.spec.symbol_name} не найдена ({m.state}).",
                    f"Virgin Key DTC suppression requested, but {m.spec.symbol_name} was not found ({m.state}).",
                )
            )
        if grp == "xcp_can0" and want == "patched" and m.state in ("missing", "ambiguous"):
            raise ValueError(
                tr(
                    f"Запрошена инженерная активация XCP на CAN0, но сигнатура {m.spec.symbol_name} не найдена ({m.state}).",
                    f"Engineering XCP on CAN0 activation requested, but {m.spec.symbol_name} was not found ({m.state}).",
                )
            )

    buf = bytearray(db01)
    orig_hdr = bytes(buf[:8])
    actions: list[str] = []

    for m in insp_before.sites:
        if m.slice_offset is None or m.va is None:
            continue
        want_state = want_by_group[m.spec.group]
        is_legacy = m.details.get("legacy_patched") == "yes"
        if m.state == want_state and not (want_state == "patched" and is_legacy):
            actions.append(
                f"[{m.spec.group}] {m.spec.symbol_name} @ 0x{m.va:08X}: "
                + tr(f"уже {want_state.upper()}", f"already {want_state.upper()}")
            )
            continue

        for ed in m.spec.edits:
            pos = m.slice_offset + ed.rel_offset
            cur = bytes(buf[pos : pos + len(ed.stock_bytes)])
            replacement = ed.stock_bytes if want_state == "stock" else ed.patched_bytes
            if not is_legacy:
                expected_cur = ed.patched_bytes if want_state == "stock" else ed.stock_bytes
                if cur != expected_cur:
                    raise RuntimeError(
                        f"Internal byte mismatch at {m.spec.symbol_name}+0x{ed.rel_offset:X}: "
                        f"got {cur.hex()}, expected {expected_cur.hex()}"
                    )
            buf[pos : pos + len(replacement)] = replacement

        src_lbl = "LEGACY_PATCHED" if is_legacy else m.state.upper()
        actions.append(
            f"[{m.spec.group}] {m.spec.symbol_name} @ 0x{m.va:08X}: {src_lbl} -> {want_state.upper()}"
        )

    # Strict cold-boot 8-byte header invariant (0x00048000..0x00048007 must NEVER change!)
    if bytes(buf[:8]) != orig_hdr or bytes(buf[:8]) != DB01_EXPECTED_HEADER_8B:
        raise RuntimeError("CRITICAL: First 8 header bytes at 0x00048000 were altered — aborting!")

    out_bytes = bytes(buf)
    dummy_after = LoadedMfk3Image(
        source_path=Path("<memory>"),
        kind="raw_db01",
        full_dump=out_bytes,
        db01_slice_start=0,
        db01_slice_end=len(out_bytes),
        db01_bytes=out_bytes,
    )
    insp_after = _inspect_loaded_mfk3(dummy_after)
    if insp_after.ks_state != want_by_group["ks_core"]:
        raise RuntimeError(
            f"Post-patch verification failed: ks_state={insp_after.ks_state!r}, expected {want_by_group['ks_core']!r}"
        )
    if insp_after.fec_state != want_by_group["fec_unlock"]:
        raise RuntimeError(
            f"Post-patch verification failed: fec_state={insp_after.fec_state!r}, expected {want_by_group['fec_unlock']!r}"
        )
    if insp_after.key_dtc_state not in (want_by_group["key_dtcs"], "unknown"):
        raise RuntimeError(
            f"Post-patch verification failed: key_dtc_state={insp_after.key_dtc_state!r}, expected {want_by_group['key_dtcs']!r}"
        )
    if insp_after.xcp_state not in (want_by_group["xcp_can0"], "unknown"):
        raise RuntimeError(
            f"Post-patch verification failed: xcp_state={insp_after.xcp_state!r}, expected {want_by_group['xcp_can0']!r}"
        )
    return out_bytes, actions


def _state_badge(state: str, st: Style, *, positive_label_ru: str, positive_label_en: str) -> str:
    if state == "stock":
        return st.yellow(tr("● Заводской сток (включена)", "● Factory stock (active)"))
    if state == "patched":
        return st.green(tr(positive_label_ru, positive_label_en))
    if state == "partial":
        return st.red(tr("⚠ Частично изменён", "⚠ Partially modified"))
    if state == "n/a":
        return st.dim("—")
    return st.red(tr("✗ Не распознано", "✗ Unrecognized"))


class Mfk3Target(EcuTargetPlugin):
    """Valeo MFK3 Front Camera (`2Q0 980 653 xx`, UDS `0x00A5`, Renesas RH850/P1H-C)."""

    target_id = "mfk3"
    ecu_address = "A5"
    arch_name = "Renesas RH850"
    aliases = ("2q0980653", "a5", "00a5", "0x00a5", "valeo_mfk3", "mkf3")
    expected_dump_sizes = MFK3_EXPECTED_DUMP_SIZES
    allowed_extensions = (".bin", ".odx-f", ".odx", ".pdx", ".frf", ".xml")

    @property
    def supports_fec_unlock(self) -> bool:
        return True

    @property
    def supports_key_dtc_suppress(self) -> bool:
        return True

    @property
    def supports_xcp_unlock(self) -> bool:
        return True

    @property
    def supports_odx_build(self) -> bool:
        return True

    @property
    def supports_container_unpack(self) -> bool:
        return True

    def title(self) -> str:
        return tr(
            "Valeo MFK3 — Камера ассистентов (2Q0 980 653)",
            "Valeo MFK3 — Front ADAS Camera (2Q0 980 653)",
        )

    def subtitle(self) -> str:
        return tr(
            "Блок A5 • Отключение защиты компонентов + активация всех функций (FeC / SWaP)",
            "Unit A5 • Component Protection off + full feature activation (FeC / SWaP)",
        )

    def description_lines(self, st: Style) -> list[str]:
        return [
            st.bold(tr("Что делает модуль:", "What this module does:")),
            tr(
                "• Навсегда отключает защиту компонентов (CP / KS) и убирает ошибку U110100.",
                "• Permanently disables Component Protection (CP / KS) and clears U110100.",
            ),
            tr(
                "• Сразу открывает все платные функции камеры: знаки (VZE), полоса, автодальний, pACC.",
                "• Immediately unlocks all paid camera features: VZE signs, Lane Assist, HBA, pACC.",
            ),
            tr(
                "• Принимает обычные прошивки (.frf / .odx-f) и дампы программатора (.bin).",
                "• Accepts standard firmware files (.frf / .odx-f) and programmer dumps (.bin).",
            ),
        ]

    def input_hint(self) -> str:
        return tr(
            "Выберите файл прошивки (.frf, .odx-f, .odx) или дамп памяти (.bin)",
            "Select a firmware file (.frf, .odx-f, .odx) or flash dump (.bin)",
        )

    def discover_candidates(self, search_roots: list[Path]) -> list[Path]:
        found: list[Path] = []
        seen: set[Path] = set()
        skip_dirs = {".git", "__pycache__", ".venv", "venv", "node_modules", ".idea", ".vscode"}

        def _consider(p: Path) -> None:
            try:
                rp = p.resolve()
                if rp in seen or not p.is_file():
                    return
                sz = p.stat().st_size
            except OSError:
                return
            low = p.name.lower()
            if low == "index.xml" or low.startswith("bf_") or "0220_fbl" in low or "db_02" in low or "db_03" in low or "db_04" in low or "db_30" in low:
                return
            ext = p.suffix.lower()
            is_cand = False
            if sz in self.expected_dump_sizes and ext == ".bin":
                is_cand = True
            elif "db_01" in low and ext == ".bin" and sz >= DB01_MIN_VALID_APP_SIZE:
                is_cand = True
            elif ext in (".odx-f", ".odx", ".pdx", ".frf") and ("2q0980653" in low or "mfk3" in low or "meapp" in low or "ks_" in low):
                is_cand = True
            if is_cand:
                seen.add(rp)
                found.append(p)

        for root in search_roots:
            if not root.is_dir():
                continue
            try:
                for p in sorted(root.iterdir(), key=lambda x: x.name.lower()):
                    if p.is_file():
                        _consider(p)
                    elif p.is_dir() and p.name not in skip_dirs and not p.name.startswith("."):
                        for sub in sorted(p.iterdir(), key=lambda x: x.name.lower()):
                            if sub.is_file():
                                _consider(sub)
            except OSError:
                continue
        return found

    def inspect_file(
        self,
        path: Path,
        *,
        frf_key_path: Path | None = None,
        ignore_input_crc: bool = False,
    ) -> TargetInspection:
        loaded = load_mfk3_source(path, frf_key_path=frf_key_path, ignore_input_crc=ignore_input_crc)
        return _inspect_loaded_mfk3(loaded)

    def render_inspection_lines(
        self,
        insp: TargetInspection,
        st: Style,
        *,
        verbose: bool = False,
    ) -> list[str]:
        ks_badge = _state_badge(
            insp.ks_state,
            st,
            positive_label_ru="✓ Отключена (пассивный режим)",
            positive_label_en="✓ Disabled (passive mode)",
        )
        if insp.fec_state == "stock":
            fec_badge = st.yellow(tr("● Закрыты (требуются заводские ключи)", "● Locked (factory keys required)"))
        else:
            fec_badge = _state_badge(
                insp.fec_state,
                st,
                positive_label_ru="✓ Все функции активированы",
                positive_label_en="✓ All features activated",
            )
        dtc_badge = (
            st.green(tr("✓ Подавлены (для новой камеры)", "✓ Suppressed (Virgin mode)"))
            if insp.key_dtc_state == "patched"
            else st.dim(tr("— Штатно", "— Standard"))
        )
        xcp_badge = (
            st.cyan(tr("✓ Включён на CAN0 (пины 3/4, инж. опция)", "✓ Enabled on CAN0 (pins 3/4, eng. option)"))
            if insp.xcp_state == "patched"
            else st.dim(tr("— Выключен (штатно)", "— Disabled (factory default)"))
        )

        lines: list[str] = [
            st.bold(st.cyan(f"◆ {self.title()}")),
            "",
            f"  {st.dim(tr('Файл           :', 'File           :'))}  {st.bold(insp.source_path.name)}",
            f"  {st.dim(tr('Папка          :', 'Folder         :'))}  {st.dim(str(insp.source_path.parent))}",
            f"  {st.dim(tr('Тип файла      :', 'File type      :'))}  {insp.format_label}",
        ]
        if insp.known_label:
            lines.append(f"  {st.dim(tr('Версия ПО      :', 'SW Version     :'))}  {st.cyan(insp.known_label)}")
        elif "part_number" in insp.metadata or "revision" in insp.metadata:
            pn = insp.metadata.get("part_number", "")
            rev = insp.metadata.get("revision", "")
            lines.append(f"  {st.dim(tr('Версия ПО      :', 'SW Version     :'))}  {st.cyan(f'{pn} ({rev})'.strip())}")

        lines.extend([
            "",
            st.bold(tr("  Текущее состояние:", "  Current Status:")),
            f"    • {st.bold(tr('Защита компонентов (KS) :', 'Component Protection    :'))}  {ks_badge}",
            f"    • {st.bold(tr('Платные функции (FeC)   :', 'Paid Features (FeC)     :'))}  {fec_badge}",
            f"    • {st.bold(tr('Ошибки новой камеры     :', 'Virgin Camera DTCs      :'))}  {dtc_badge}",
            f"    • {st.bold(tr('Инженерный XCP (CAN0)   :', 'Engineering XCP (CAN0)  :'))}  {xcp_badge}",
            "",
            st.bold(tr("  Функции камеры (SWaP / FeC):", "  Camera Features (SWaP / FeC):")),
        ])
        fec_icon = (
            st.green("✓")
            if insp.fec_state == "patched"
            else st.yellow("○")
            if insp.fec_state == "stock"
            else st.red("?")
        )
        for code, fdesc in insp.supported_fecs:
            if not verbose and code in ("100E1600", "100E1700", "100E1200", "100E1300", "100E1400", "100E1500"):
                continue
            lines.append(f"    {fec_icon}  {fdesc}  {st.dim(f'[{code}]')}")
        if not verbose:
            lines.append(
                f"    {fec_icon}  "
                + st.dim(
                    tr(
                        "+ ещё 6 внутренних каналов и слотов камеры (100E1200..100E1700)",
                        "+ 6 internal camera feature channels & slots (100E1200..100E1700)",
                    )
                )
            )

        if verbose:
            hdr_ok = insp.metadata.get("header_valid") == "yes"
            hdr_txt = (
                st.green(f"{insp.metadata.get('header_magic')} / entry {insp.metadata.get('header_entry')} (OK)")
                if hdr_ok
                else st.red(f"{insp.metadata.get('header_magic')} / entry {insp.metadata.get('header_entry')} (INVALID!)")
            )
            lines.extend([
                "",
                st.dim("  ── " + tr("Технические подробности", "Technical Details") + " ──"),
                f"    CRC-32 : 0x{insp.crc32_trimmed:08X}   |   Header : {hdr_txt}",
                f"    SHA-256: {insp.sha256_trimmed}",
            ])
            for idx, m in enumerate(insp.sites, 1):
                st_tok = st.green("PATCHED") if m.state == "patched" else st.yellow(m.state.upper().ljust(7))
                loc = f"0x{m.va:08X}" if m.va is not None else "N/A"
                lines.append(f"    {idx:2d}. [{st_tok}] {m.spec.symbol_name:<22} @ {loc}")

        return lines

    def patch_file(self, input_path: Path, opts: PatchOptions) -> TargetPatchResult:
        loaded = load_mfk3_source(
            input_path,
            frf_key_path=opts.frf_key_path,
            ignore_input_crc=opts.ignore_input_crc,
        )
        before_insp = _inspect_loaded_mfk3(loaded)

        patched_db01, actions = _patch_mfk3_db01_bytes(
            loaded.db01_bytes,
            restore_stock=opts.restore_stock,
            activate_all_fecs=opts.activate_all_fecs,
            suppress_key_dtcs=opts.suppress_key_dtcs,
            enable_xcp_can0=opts.enable_xcp_can0,
        )

        xcp_sfx = "_xcp" if (opts.enable_xcp_can0 and not opts.restore_stock) else ""
        xcp_stm = "_XCP" if (opts.enable_xcp_can0 and not opts.restore_stock) else ""
        suffix_tag = (
            "stock"
            if opts.restore_stock
            else (f"ks_fec{xcp_sfx}_passive" if opts.activate_all_fecs else f"ks{xcp_sfx}_passive")
        )
        stem_tag = (
            "STOCK"
            if opts.restore_stock
            else (f"KS_FEC{xcp_stm}" if opts.activate_all_fecs else f"KS_PASSIVE{xcp_stm}")
        )

        written_bin: Path | None = None
        if loaded.kind == "odx_container":
            if opts.in_place:
                raise ValueError(
                    tr(
                        "--in-place не поддерживается для контейнеров .odx-f/.frf (укажите -o <файл.bin> или --build-odx <папка>)",
                        "--in-place is not supported for .odx-f/.frf containers (use -o <out.bin> or --build-odx <dir>)",
                    )
                )
            out_bin_target = opts.output_bin
            if out_bin_target is None and opts.build_odx_dir is None:
                cand_dir = input_path.parent
                if not cand_dir.exists() or not _is_dir_writable(cand_dir):
                    cand_dir = Path.cwd()
                out_bin_target = cand_dir / f"{input_path.stem}_DB_01_{suffix_tag}.bin"
            if out_bin_target is not None:
                out_bin_target.parent.mkdir(parents=True, exist_ok=True)
                out_bin_target.write_bytes(patched_db01)
                written_bin = out_bin_target
            final_full_dump = None
        else:
            assert loaded.full_dump is not None
            rebuilt = bytearray(loaded.full_dump)
            rebuilt[loaded.db01_slice_start : loaded.db01_slice_end] = patched_db01
            final_full_dump = bytes(rebuilt)

            if opts.in_place:
                out_bin_target = input_path
            elif opts.output_bin is not None:
                out_bin_target = opts.output_bin
            elif opts.build_odx_dir is None:
                cand_dir = input_path.parent
                if not cand_dir.exists() or not _is_dir_writable(cand_dir):
                    cand_dir = Path.cwd()
                out_bin_target = cand_dir / f"{input_path.stem}_{suffix_tag}{input_path.suffix or '.bin'}"
            else:
                out_bin_target = None

            if out_bin_target is not None:
                out_bin_target.parent.mkdir(parents=True, exist_ok=True)
                out_bin_target.write_bytes(final_full_dump)
                written_bin = out_bin_target

        written_odx: list[Path] = []
        if opts.build_odx_dir is not None:
            if opts.odx_method.strip().upper() != "00":
                raise ValueError(
                    tr(
                        "Для камеры Valeo MFK3 сжатие LZSS A0 при сборке отключено — поддерживается только метод 00 (без сжатия).",
                        "LZSS A0 compression during MFK3 ODX generation is disabled — only uncompressed method 00 is supported.",
                    )
                )
            tmpl_src_name = input_path.name
            if opts.template_odx is not None:
                tmpl_src_name = opts.template_odx.name
                tmpl_xml, tmpl_blocks, tmpl_meta = parse_odx_container(
                    opts.template_odx,
                    frf_key_path=opts.frf_key_path,
                    only_blocks={"DB_01FLASHDATA", "DB_30ERASEPROGRROUTI", "DB_04FLASHDATA"},
                    verify_crc=not opts.ignore_input_crc,
                )
            elif loaded.kind == "odx_container" and loaded.odx_xml_text is not None:
                tmpl_xml = loaded.odx_xml_text
                tmpl_blocks = loaded.odx_blocks
                tmpl_meta = loaded.extra_meta
            else:
                auto_tmpl = find_sibling_mfk3_template_odx(input_path)
                if auto_tmpl is None:
                    raise ValueError(
                        tr(
                            "Для сборки ODX из сырого дампа/DB_01 укажите шаблонный заводской контейнер (--template-odx FL_2Q0980653x_xxxx_MEAPP_V001_S.odx-f / .frf)!",
                            "To build ODX from a raw dump/DB_01, pass a factory template container (--template-odx FL_2Q0980653x_xxxx_MEAPP_V001_S.odx-f / .frf)!",
                        )
                    )
                tmpl_src_name = auto_tmpl.name
                tmpl_xml, tmpl_blocks, tmpl_meta = parse_odx_container(
                    auto_tmpl,
                    frf_key_path=opts.frf_key_path,
                    only_blocks={"DB_01FLASHDATA", "DB_30ERASEPROGRROUTI", "DB_04FLASHDATA"},
                    verify_crc=not opts.ignore_input_crc,
                )

            pn_prefix = (tmpl_meta.get("part_number") or "2Q0980653J").replace(" ", "").strip() or "2Q0980653J"
            sw_ver = resolve_mfk3_sw_version(loaded.extra_meta, tmpl_meta, tmpl_src_name)
            if sw_ver == "0000" and before_insp.crc32_trimmed == 0x0E6C1A8A:
                sw_ver = "1423"
            written_odx = build_mfk3_part1_part2_odx(
                patched_db01,
                tmpl_xml,
                tmpl_blocks,
                opts.build_odx_dir,
                odx_layout=opts.odx_layout,
                include_part2=opts.include_part2,
                part_number_prefix=pn_prefix,
                sw_version=sw_ver,
                rev_label=tmpl_meta.get("revision"),
                stem_tag=stem_tag,
            )

        after_loaded = LoadedMfk3Image(
            source_path=written_bin or input_path,
            kind=loaded.kind,
            full_dump=final_full_dump,
            db01_slice_start=loaded.db01_slice_start,
            db01_slice_end=loaded.db01_slice_end,
            db01_bytes=patched_db01,
            extra_meta=dict(loaded.extra_meta),
        )
        after_insp = _inspect_loaded_mfk3(after_loaded)

        notes: list[str] = []
        if written_odx:
            notes.extend([
                tr(
                    "Как прошить через ODIS-E (в 2 шага):",
                    "How to flash in ODIS-E (2 simple steps):",
                ),
                tr(
                    "  1. Прошейте файл из папки PART1 — в самом конце ODIS покажет ошибку подписи "
                    "(не пугайтесь: основная прошивка уже записана в камеру).",
                    "  1. Flash the file inside PART1 — at the very end ODIS will report a signature error "
                    "(this is expected: the patched firmware is already written).",
                ),
                tr(
                    "  2. Не выключая зажигание, сразу прошейте файл из папки PART2 — он пройдёт на 100% зелёным "
                    "и выведет камеру в штатный рабочий режим.",
                    "  2. Without turning off ignition, immediately flash PART2 — it will finish 100% green "
                    "and return the camera to normal operating mode.",
                ),
            ])
        elif written_bin is not None:
            notes.append(
                tr(
                    "Готовый .bin файл можно записывать программатором на столе обратно во флеш-память камеры.",
                    "The generated .bin file is ready to be written back to camera flash memory with a bench programmer.",
                )
            )

        return TargetPatchResult(
            before=before_insp,
            after=after_insp,
            actions=actions,
            written_bin=written_bin,
            written_odx_files=written_odx,
            flashing_notes=notes,
        )

    def render_patch_result_lines(
        self,
        res: TargetPatchResult,
        st: Style,
        *,
        verbose: bool = False,
    ) -> list[str]:
        ks_after = _state_badge(
            res.after.ks_state,
            st,
            positive_label_ru="✓ Отключена (пассивный режим)",
            positive_label_en="✓ Disabled (passive mode)",
        )
        if res.after.fec_state == "stock":
            fec_after = st.yellow(tr("● Заводской сток", "● Factory stock"))
        else:
            fec_after = _state_badge(
                res.after.fec_state,
                st,
                positive_label_ru="✓ Все 9 функций открыты",
                positive_label_en="✓ All 9 features unlocked",
            )

        is_restore = (
            res.after.ks_state == "stock"
            and res.after.fec_state == "stock"
            and res.after.key_dtc_state in ("stock", "n/a")
            and res.after.xcp_state in ("stock", "n/a")
        )
        header_txt = (
            tr("✓ Заводской сток успешно восстановлен!", "✓ Factory Stock Restored Successfully!")
            if is_restore
            else tr("✓ Готово! Прошивка успешно подготовлена", "✓ Done! Firmware Prepared Successfully")
        )

        lines: list[str] = [
            st.bold(st.green(header_txt)),
            "",
            f"  {st.dim(tr('Исходный файл           :', 'Source file             :'))}  {res.before.source_path.name}",
            f"  {st.dim(tr('Защита компонентов (KS) :', 'Component Protection    :'))}  {ks_after}",
            f"  {st.dim(tr('Платные функции (FeC)   :', 'Paid Features (FeC)     :'))}  {fec_after}",
        ]
        if res.after.xcp_state == "patched":
            lines.append(
                f"  {st.dim(tr('Инженерный XCP (CAN0)   :', 'Engineering XCP (CAN0)  :'))}  "
                + st.cyan(
                    tr(
                        "✓ Включён на CAN0 (пины 3=CAN-H / 4=CAN-L, 500 кбит/с, ID 0x1BFE7E01/00)",
                        "✓ Enabled on CAN0 (pins 3=CAN-H / 4=CAN-L, 500 kbit/s, ID 0x1BFE7E01/00)",
                    )
                )
            )

        if res.written_odx_files:
            odx_main = [p for p in res.written_odx_files if p.suffix.lower() in (".odx-f", ".odx")]
            lines.append("")
            lines.append(st.bold(tr("  Созданные пакеты для ODIS-E:", "  Created ODIS-E Packages:")))
            for fp in odx_main:
                rel_hint = f"{fp.parent.name}/{fp.name}" if fp.parent.name in ("PART1", "PART2") else fp.name
                lines.append(f"    • {st.cyan(st.bold(rel_hint))}  {st.dim(f'({fp.parent})')}")
        elif res.written_bin is not None:
            sz_mb = res.written_bin.stat().st_size / (1024 * 1024)
            lines.extend([
                "",
                st.bold(tr("  Сохранённый файл:", "  Saved File:")),
                f"    • {st.green(st.bold(res.written_bin.name))}  ({sz_mb:.2f} MB)",
                f"      {st.dim(str(res.written_bin.parent))}",
            ])

        if res.flashing_notes:
            lines.append("")
            for note in res.flashing_notes:
                lines.append(st.bold(st.yellow(note)) if not note.startswith("  ") else note)

        if verbose:
            lines.extend([
                "",
                st.dim("  ── " + tr("Технические подробности", "Technical Details") + " ──"),
                f"    CRC-32 : 0x{res.before.crc32_trimmed:08X} -> 0x{res.after.crc32_trimmed:08X}",
                f"    SHA-256: {res.after.sha256_trimmed}",
            ])
            if res.written_odx_files:
                lines.append(
                    "    "
                    + tr(
                        "UDS    : DB_01 method=00 (SIG_SHA1-RSA1024_S), CheckMemory -> 71 01 02 02 01, SWaP DID 0x3C00 -> 0xFF",
                        "UDS    : DB_01 method=00 (SIG_SHA1-RSA1024_S), CheckMemory -> 71 01 02 02 01, SWaP DID 0x3C00 -> 0xFF",
                    )
                )
            for act in res.actions:
                lines.append(f"    • {act}")

        return lines

    def unpack_container(
        self,
        input_path: Path,
        output_dir: Path,
        *,
        skip_large_blocks: bool = False,
        frf_key_path: Path | None = None,
        ignore_input_crc: bool = False,
    ) -> list[tuple[str, int, int, int, int, Path]]:
        only = (
            {"DB_30ERASEPROGRROUTI", "DB_01FLASHDATA", "DB_02FLASHDATA", "DB_04FLASHDATA"}
            if skip_large_blocks
            else None
        )
        _, blocks, _ = parse_odx_container(
            input_path,
            frf_key_path=frf_key_path,
            only_blocks=only,
            verify_crc=not ignore_input_crc,
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        results: list[tuple[str, int, int, int, int, Path]] = []
        for name, blk in blocks.items():
            out_fp = output_dir / f"{name}.bin"
            out_fp.write_bytes(blk.uncompressed)
            crc = zlib.crc32(blk.uncompressed) & 0xFFFFFFFF
            results.append((name, blk.method, len(blk.raw_payload), len(blk.uncompressed), crc, out_fp))
        return results

    def selftest(self) -> list[str]:
        report: list[str] = []

        # 1. Verify built-in 4095B frf.key
        key = get_frf_key(None)
        key_sha = hashlib.sha256(key).hexdigest()
        if len(key) != 4095 or key_sha != BUILTIN_FRF_KEY_SHA256:
            raise AssertionError(f"Built-in frf.key mismatch: len={len(key)}, sha256={key_sha}")
        report.append(f"[OK] Built-in frf.key verified (4,095 B, SHA-256 {key_sha[:16]}…)")

        # 2. Verify hardware-strict LZSS A0 codec (0220 FBL rule: dist >= length on 0xFF / 0x00 runs)
        sample = (
            DB01_EXPECTED_HEADER_8B
            + b"\xFF" * 504
            + b"\x00" * 512
            + b"\x20" * 128
            + b"Valeo_MFK3_2Q0980653J_KS_PASSIVE_ALL_9_FEC_100E0F00_100E1000!" * 40
            + bytes(range(256)) * 8
        )
        comp = lzss_a0_compress(sample)
        decomp = lzss_a0_decompress(comp, strict_hw=True)
        if decomp != sample or len(comp) >= len(sample):
            raise AssertionError("LZSS A0 hardware-strict round-trip failed")
        report.append(
            f"[OK] LZSS A0 codec hardware-strict round-trip (dist >= length verified, "
            f"{len(sample):,} B -> {len(comp):,} B)"
        )

        # 3. Build synthetic 1.8 MiB DB_01 image embedding all 11 RH850 sites (5 KS + 4 FeC + 1 KeyDTC + 1 XCP_CAN0)
        synth = bytearray(b"\xFF" * DB01_SW1423_SIZE)
        synth[0:8] = DB01_EXPECTED_HEADER_8B
        # _start gp/tp setup at 0x208
        synth[0x208:0x20E] = struct.pack("<HI", 0x0624, 0xFEE8F300)
        synth[0x20E:0x214] = struct.pack("<HI", 0x0625, 0x00049000)

        for spec in MFK3_PATCH_SITES:
            off = spec.reference_va - DB01_BASE_VA
            pat_b, mask_b = parse_masked_pattern(spec.stock_pattern)
            concrete = bytearray(len(pat_b))
            for i, (pb, mb) in enumerate(zip(pat_b, mask_b)):
                concrete[i] = pb if mb else ((0x5A + i + (off & 0x1F)) & 0xFF)
            synth[off : off + len(concrete)] = concrete

        orig_bytes = bytes(synth)
        orig_sha = hashlib.sha256(orig_bytes).hexdigest()

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            in_bin = td_path / "synth_db01.bin"
            out_bin = td_path / "synth_db01_patched.bin"
            rest_bin = td_path / "synth_db01_restored.bin"
            in_bin.write_bytes(orig_bytes)

            insp0 = self.inspect_file(in_bin)
            if (insp0.ks_state, insp0.fec_state, insp0.key_dtc_state, insp0.xcp_state) != (
                "stock",
                "stock",
                "stock",
                "stock",
            ):
                raise AssertionError(
                    f"Unexpected initial states: {insp0.ks_state}, {insp0.fec_state}, "
                    f"{insp0.key_dtc_state}, {insp0.xcp_state}"
                )

            res_patch = self.patch_file(
                in_bin,
                PatchOptions(
                    activate_all_fecs=True,
                    suppress_key_dtcs=True,
                    enable_xcp_can0=True,
                    output_bin=out_bin,
                ),
            )
            if (
                res_patch.after.ks_state,
                res_patch.after.fec_state,
                res_patch.after.key_dtc_state,
                res_patch.after.xcp_state,
            ) != (
                "patched",
                "patched",
                "patched",
                "patched",
            ):
                raise AssertionError("Synthetic patch did not transition all 4 groups to 'patched'")

            res_restore = self.patch_file(
                out_bin,
                PatchOptions(
                    restore_stock=True,
                    output_bin=rest_bin,
                ),
            )
            if res_restore.after.sha256_trimmed != orig_sha or rest_bin.read_bytes() != orig_bytes:
                raise AssertionError("Lossless --restore-stock SHA-256 mismatch!")

            # Verify legacy 0x4F DID 0x3C00 recognition, upgrade to 0xFF, and lossless --restore-stock
            leg_buf = bytearray(out_bin.read_bytes())
            leg_off = (0x0013C5C6 - DB01_BASE_VA) + 0x0E
            leg_buf[leg_off : leg_off + 4] = bytes.fromhex("00564f00")
            leg_fp = td_path / "synth_legacy_0x4f.bin"
            leg_upg_fp = td_path / "synth_legacy_upgraded.bin"
            leg_rst_fp = td_path / "synth_legacy_restored.bin"
            leg_fp.write_bytes(leg_buf)
            insp_leg = self.inspect_file(leg_fp)
            if insp_leg.fec_state != "patched":
                raise AssertionError(f"Legacy 0x4F DID 0x3C00 not recognized as patched: {insp_leg.fec_state!r}")
            self.patch_file(
                leg_fp,
                PatchOptions(
                    activate_all_fecs=True,
                    suppress_key_dtcs=True,
                    enable_xcp_can0=True,
                    output_bin=leg_upg_fp,
                ),
            )
            if leg_upg_fp.read_bytes() != out_bin.read_bytes():
                raise AssertionError("Legacy 0x4F -> 0xFF upgrade mismatch!")
            self.patch_file(leg_fp, PatchOptions(restore_stock=True, output_bin=leg_rst_fp))
            if leg_rst_fp.read_bytes() != orig_bytes:
                raise AssertionError("Legacy 0x4F --restore-stock mismatch!")
            report.append(
                f"[OK] Synthetic DB_01 (5 KS + 4 FeC + 1 KeyDTC + 1 XCP_CAN0 = 11 sites) patch & bit-exact --restore-stock "
                f"(SHA-256 {orig_sha[:16]}…)"
            )

            # 4. Guard checks: cold-boot 0xA5000000 header & 0220_FBL size rejection
            bad_hdr = bytearray(orig_bytes)
            struct.pack_into("<I", bad_hdr, 0, 0xA5000000)
            bad_fp = td_path / "bad_hdr.bin"
            bad_fp.write_bytes(bad_hdr)
            try:
                self.patch_file(bad_fp, PatchOptions(output_bin=td_path / "never.bin"))
                raise AssertionError("Expected rejection of 0xA5000000 header")
            except ValueError:
                report.append("[OK] Cold-boot 0xA5000000 header guard verified")

            fbl_fp = td_path / "fbl_0220.bin"
            fbl_buf = bytearray(b"\xFF" * FBL_UPDATER_DB01_SIZE)
            fbl_buf[:8] = DB01_EXPECTED_HEADER_8B
            fbl_fp.write_bytes(fbl_buf)
            try:
                self.patch_file(fbl_fp, PatchOptions(output_bin=td_path / "never2.bin"))
                raise AssertionError("Expected rejection of 222 KB 0220_FBL updater")
            except ValueError:
                report.append("[OK] 0220_FBL bootloader updater size guard verified")

            # 5. PART1 + PART2 ODX builder round-trip (method 00 only, unique PART1/PART2 XML IDs, SW 1304 + SIG_SHA1-RSA1024_S)
            synth_id = "2Q0980653G_1304_MEAPP_V002_S"
            synth_tmpl_xml = (
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<ODX xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
                f'  <FLASH ID="FL_{synth_id}">\n'
                f'    <SHORT-NAME>FL_{synth_id}</SHORT-NAME>\n'
                '    <LONG-NAME>2Q0 980 653G _1304 _MEAP P _V002 _S</LONG-NAME>\n'
                '    <ADMIN-DATA><DOC-REVISIONS><DOC-REVISION><REVISION-LABEL>1304_V002</REVISION-LABEL></DOC-REVISION></DOC-REVISIONS></ADMIN-DATA>\n'
                f'    <ECU-MEMS><ECU-MEM ID="EMEM_{synth_id}"><SHORT-NAME>EMEM_{synth_id}</SHORT-NAME><MEM>\n'
                f'      <SESSIONS><SESSION ID="EMEM_{synth_id}.SES_{synth_id}"><SHORT-NAME>SES_{synth_id}</SHORT-NAME>\n'
                '        <DATABLOCK-REFS>\n'
                f'          <DATABLOCK-REF ID-REF="EMEM_{synth_id}.DB_30ERASEPROGRROUTI"/>\n'
                f'          <DATABLOCK-REF ID-REF="EMEM_{synth_id}.DB_01FLASHDATA"/>\n'
                f'          <DATABLOCK-REF ID-REF="EMEM_{synth_id}.DB_04FLASHDATA"/>\n'
                '        </DATABLOCK-REFS>\n'
                '      </SESSION></SESSIONS>\n'
                '      <DATABLOCKS>\n'
                f'        <DATABLOCK ID="EMEM_{synth_id}.DB_30ERASEPROGRROUTI">\n'
                '          <SHORT-NAME>DB_30ERASEPROGRROUTI</SHORT-NAME>\n'
                f'          <FLASHDATA-REF ID-REF="EMEM_{synth_id}.FD_30ERASEPROGRROUTI"/>\n'
                '          <SEGMENTS><SEGMENT><COMPRESSED-SIZE>32</COMPRESSED-SIZE><UNCOMPRESSED-SIZE>64</UNCOMPRESSED-SIZE></SEGMENT></SEGMENTS>\n'
                '          <SECURITYS><SECURITY><SECURITY-METHOD TYPE="A_ASCIISTRING">SIG_SHA1-RSA1024_with_CRC32_S</SECURITY-METHOD>'
                f'<FW-SIGNATURE>{"AA" * 128}</FW-SIGNATURE><FW-CHECKSUM>00000000</FW-CHECKSUM></SECURITY></SECURITYS>\n'
                '        </DATABLOCK>\n'
                f'        <DATABLOCK ID="EMEM_{synth_id}.DB_01FLASHDATA">\n'
                '          <SHORT-NAME>DB_01FLASHDATA</SHORT-NAME>\n'
                f'          <FLASHDATA-REF ID-REF="EMEM_{synth_id}.FD_01FLASHDATA"/>\n'
                '          <SEGMENTS><SEGMENT><COMPRESSED-SIZE>100</COMPRESSED-SIZE><UNCOMPRESSED-SIZE>4096</UNCOMPRESSED-SIZE></SEGMENT></SEGMENTS>\n'
                '          <SECURITYS><SECURITY><SECURITY-METHOD TYPE="A_ASCIISTRING">SIG_SHA1-RSA1024_with_CRC32_S</SECURITY-METHOD>'
                f'<FW-SIGNATURE>{"BB" * 128}</FW-SIGNATURE><FW-CHECKSUM>00000000</FW-CHECKSUM></SECURITY></SECURITYS>\n'
                '        </DATABLOCK>\n'
                f'        <DATABLOCK ID="EMEM_{synth_id}.DB_04FLASHDATA">\n'
                '          <SHORT-NAME>DB_04FLASHDATA</SHORT-NAME>\n'
                f'          <FLASHDATA-REF ID-REF="EMEM_{synth_id}.FD_04FLASHDATA"/>\n'
                '          <SEGMENTS><SEGMENT><COMPRESSED-SIZE>40</COMPRESSED-SIZE><UNCOMPRESSED-SIZE>296</UNCOMPRESSED-SIZE></SEGMENT></SEGMENTS>\n'
                '          <SECURITYS><SECURITY><SECURITY-METHOD TYPE="A_ASCIISTRING">SIG_SHA1-RSA1024_with_CRC32_S</SECURITY-METHOD>'
                f'<FW-SIGNATURE>{"CC" * 128}</FW-SIGNATURE><FW-CHECKSUM>00000000</FW-CHECKSUM></SECURITY></SECURITYS>\n'
                '        </DATABLOCK>\n'
                '      </DATABLOCKS>\n'
                '      <FLASHDATAS>\n'
                f'        <FLASHDATA ID="EMEM_{synth_id}.FD_30ERASEPROGRROUTI" xsi:type="EXTERN-FLASHDATA"><ENCRYPT-COMPRESS-METHOD>A0</ENCRYPT-COMPRESS-METHOD><DATAFILE>bf30.bin</DATAFILE></FLASHDATA>\n'
                f'        <FLASHDATA ID="EMEM_{synth_id}.FD_01FLASHDATA" xsi:type="EXTERN-FLASHDATA"><ENCRYPT-COMPRESS-METHOD>A0</ENCRYPT-COMPRESS-METHOD><DATAFILE>bf01.bin</DATAFILE></FLASHDATA>\n'
                f'        <FLASHDATA ID="EMEM_{synth_id}.FD_04FLASHDATA" xsi:type="EXTERN-FLASHDATA"><ENCRYPT-COMPRESS-METHOD>A0</ENCRYPT-COMPRESS-METHOD><DATAFILE>bf04.bin</DATAFILE></FLASHDATA>\n'
                '      </FLASHDATAS>\n'
                '    </MEM></ECU-MEM></ECU-MEMS>\n'
                f'    <ECU-MEM-CONNECTORS><ECU-MEM-CONNECTOR ID="EMC_{synth_id}"><SHORT-NAME>EMC_{synth_id}</SHORT-NAME>'
                f'<SESSION-DESCS><SESSION-DESC DIRECTION="DOWNLOAD"><SHORT-NAME>SESD_{synth_id}</SHORT-NAME>'
                '<PARTNUMBER>2Q0980653G </PARTNUMBER>'
                f'<SESSION-SNREF SHORT-NAME="SES_{synth_id}"/></SESSION-DESC></SESSION-DESCS>'
                f'<ECU-MEM-REF ID-REF="EMEM_{synth_id}"/></ECU-MEM-CONNECTOR></ECU-MEM-CONNECTORS>\n'
                '  </FLASH>\n'
                '</ODX>\n'
            )
            b30_raw = b"DB30_RAM_DRIVER_" * 4
            b04_raw = b"\x2a\x00\x00\x00" + b"\x00" * 292
            mini_db01 = out_bin.read_bytes()[:4096]
            tmpl_blocks = {
                "DB_30ERASEPROGRROUTI": OdxBlockEntry(
                    "DB_30ERASEPROGRROUTI", 0xA0, lzss_a0_compress(b30_raw), b30_raw, len(b30_raw),
                    zlib.crc32(b30_raw) & 0xFFFFFFFF, "AA" * 128, "SIG_SHA1-RSA1024_with_CRC32_S", "BF_30.bin",
                ),
                "DB_01FLASHDATA": OdxBlockEntry(
                    "DB_01FLASHDATA", 0xA0, lzss_a0_compress(mini_db01), mini_db01, len(mini_db01),
                    zlib.crc32(mini_db01) & 0xFFFFFFFF, "BB" * 128, "SIG_SHA1-RSA1024_with_CRC32_S", "BF_01.bin",
                ),
                "DB_04FLASHDATA": OdxBlockEntry(
                    "DB_04FLASHDATA", 0xA0, lzss_a0_compress(b04_raw), b04_raw, len(b04_raw),
                    zlib.crc32(b04_raw) & 0xFFFFFFFF, "CC" * 128, "SIG_SHA1-RSA1024_with_CRC32_S", "BF_04.bin",
                ),
            }
            odx_out = td_path / "odx_rt"
            sw_resolved = resolve_mfk3_sw_version({}, {"revision": "1304_V002", "flash_short_name": f"FL_{synth_id}"})
            if sw_resolved != "1304":
                raise AssertionError(f"Expected sw_version '1304', got {sw_resolved!r}")
            written_odx = build_mfk3_part1_part2_odx(
                mini_db01,
                synth_tmpl_xml,
                tmpl_blocks,
                odx_out,
                odx_layout="both",
                include_part2=True,
                part_number_prefix="2Q0980653G",
                sw_version=sw_resolved,
                rev_label="1304_V002",
            )
            p1_xml, p1_blks, p1_meta = parse_odx_container(
                odx_out / "PART1" / "FL_2Q0980653G_1304_KS_FEC_PART1_S.odx-f"
            )
            p2_xml, p2_blks, p2_meta = parse_odx_container(
                odx_out / "PART2" / "FL_2Q0980653G_1304_KS_FEC_PART2_S.odx-f"
            )
            if p1_blks["DB_01FLASHDATA"].method != 0x00 or p1_blks["DB_01FLASHDATA"].uncompressed != mini_db01:
                raise AssertionError("ODX PART1 DB_01 must be uncompressed method 00!")
            if p1_blks["DB_01FLASHDATA"].security_method != "SIG_SHA1-RSA1024_S":
                raise AssertionError(
                    f"Expected SIG_SHA1-RSA1024_S for method 00 DB_01, got {p1_blks['DB_01FLASHDATA'].security_method!r}"
                )
            if p2_blks["DB_04FLASHDATA"].uncompressed != b04_raw:
                raise AssertionError("ODX PART2 DB_04 mismatch!")
            if (
                p1_meta.get("flash_short_name") == p2_meta.get("flash_short_name")
                or "_MEAPP_" in p1_xml
                or "_MEAPP_" in p2_xml
            ):
                raise AssertionError("ODX PART1 and PART2 XML IDs / SHORT-NAMEs were not uniquely rewritten!")
            report.append(
                f"[OK] ODIS-E PART1 + PART2 ODX builder verified ({len(written_odx)} files, method=00, "
                f"unique XML IDs, SIG_SHA1-RSA1024_S)"
            )

        return report


def _is_dir_writable(d: Path) -> bool:
    try:
        probe = d / ".ks_write_test.tmp"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False
