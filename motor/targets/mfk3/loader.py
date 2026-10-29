"""Image/container loader and ODIS-E `PART1`+`PART2` ODX builder for Valeo MFK3 (`2Q0 980 653`)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import zlib

from ...core.containers import (
    OdxBlockEntry,
    build_catalog_index_xml,
    build_single_odx_xml,
    parse_odx_container,
)
from ...core.i18n import tr
from .constants import (
    BANK0_DB01_OFF,
    BANK0_DB04_OFF,
    BANK0_DUMP_SIZE,
    BANK0_FBL_VER_OFF,
    DB01_END_VA_EXCL,
    DB01_EXPECTED_HEADER_8B,
    DB01_MAX_REGION_SIZE,
    DUAL_BANK_DUMP_SIZE,
    FBL_UPDATER_DB01_SIZE,
    LINEAR_9D8_DUMP_SIZE,
    LINEAR_10M_DUMP_SIZE,
    MFK3_DB_TO_FD_MAP,
    STOCK_DB01_1423_SIGNATURE_HEX,
)


@dataclass
class LoadedMfk3Image:
    """Normalized representation of an MFK3 input file (`DB_01`, programmer dump, or ODX/FRF container)."""

    source_path: Path
    kind: str                   # "raw_db01", "bank0_2m", "dual_bank_4m", "linear_dump", "odx_container"
    full_dump: bytes | None
    db01_slice_start: int
    db01_slice_end: int
    db01_bytes: bytes
    extra_meta: dict[str, str] = field(default_factory=dict)
    odx_xml_text: str | None = None
    odx_blocks: dict[str, OdxBlockEntry] = field(default_factory=dict)


def format_kind_label(kind: str) -> str:
    labels = {
        "raw_db01": tr(
            "Блок программы камеры (DB_01)",
            "Camera program block (DB_01)",
        ),
        "bank0_2m": tr(
            "Дамп флеш-памяти (2 МБ)",
            "Flash memory dump (2 MB)",
        ),
        "dual_bank_4m": tr(
            "Полный дамп флеш-памяти (4 МБ)",
            "Full flash memory dump (4 MB)",
        ),
        "linear_dump": tr(
            "Линейный дамп памяти (10 МБ)",
            "Linear flash dump (10 MB)",
        ),
        "odx_container": tr(
            "Заводской файл прошивки (.frf / .odx-f / .odx)",
            "Factory firmware file (.frf / .odx-f / .odx)",
        ),
    }
    return labels.get(kind, kind)


def load_mfk3_source(
    path: Path,
    *,
    frf_key_path: Path | None = None,
    ignore_input_crc: bool = False,
) -> LoadedMfk3Image:
    """Auto-detect and load `DB_01FLASHDATA.bin`, RH850 Bank0/DualBank dumps, or `.odx`/`.odx-f`/`.frf`."""
    if not path.is_file():
        raise FileNotFoundError(tr(f"Файл не найден: {path}", f"File not found: {path}"))

    suffix = path.suffix.lower()
    with path.open("rb") as fh:
        head64 = fh.read(64)

    if (
        suffix in (".odx", ".odx-f", ".pdx", ".frf", ".xml")
        or head64.lstrip().startswith(b"<")
        or head64[:4] == b"PK\x03\x04"
    ):
        # Skip decoding the 64 MiB EyeQ4 DB_03 block during inspect/patch for instant loading!
        needed = {"DB_01FLASHDATA", "DB_30ERASEPROGRROUTI", "DB_04FLASHDATA"}
        xml_text, blocks, meta = parse_odx_container(
            path,
            frf_key_path=frf_key_path,
            only_blocks=needed,
            verify_crc=not ignore_input_crc,
        )
        if "DB_01FLASHDATA" not in blocks:
            raise ValueError(
                tr(
                    f"В контейнере {path.name} отсутствует блок DB_01FLASHDATA (это параметрия 7100 или PART2?)",
                    f"Container {path.name} does not contain DB_01FLASHDATA (is it a 7100 dataset or PART2?)",
                )
            )
        b01 = blocks["DB_01FLASHDATA"]
        meta["db01_odx_method"] = f"{b01.method:02X}"
        meta["db01_packed_size"] = str(len(b01.raw_payload))
        return LoadedMfk3Image(
            source_path=path,
            kind="odx_container",
            full_dump=None,
            db01_slice_start=0,
            db01_slice_end=len(b01.uncompressed),
            db01_bytes=b01.uncompressed,
            extra_meta=meta,
            odx_xml_text=xml_text,
            odx_blocks=blocks,
        )

    raw = path.read_bytes()
    size = len(raw)
    meta: dict[str, str] = {}

    # Case 1: Bank 0 (2 MiB), Dual-Bank 0+1 (4 MiB), or Linear 10 MiB / 0x9D8000 programmer dump
    if size in (BANK0_DUMP_SIZE, DUAL_BANK_DUMP_SIZE, LINEAR_10M_DUMP_SIZE, LINEAR_9D8_DUMP_SIZE):
        if raw[BANK0_DB01_OFF : BANK0_DB01_OFF + 8] == DB01_EXPECTED_HEADER_8B:
            fbl_ver_raw = raw[BANK0_FBL_VER_OFF : BANK0_FBL_VER_OFF + 4]
            if all(0x20 <= b <= 0x7E for b in fbl_ver_raw):
                meta["resident_fbl_version"] = fbl_ver_raw.decode("ascii")
            db04_hdr = raw[BANK0_DB04_OFF : BANK0_DB04_OFF + 4]
            meta["db04_present"] = (
                "yes" if db04_hdr in (b"\x2a\x00\x00\x00", b"\x00\x00\x00\x2a") else f"0x{db04_hdr.hex().upper()}"
            )

            if size == BANK0_DUMP_SIZE:
                kind = "bank0_2m"
            elif size == DUAL_BANK_DUMP_SIZE:
                kind = "dual_bank_4m"
                sw_ver = raw[0x200000:0x200004]
                if all(0x20 <= b <= 0x7E for b in sw_ver):
                    meta["db02_sw_version"] = sw_ver.decode("ascii")
            else:
                kind = "linear_dump"
                sw_ver = raw[0x800000:0x800004]
                if all(0x20 <= b <= 0x7E for b in sw_ver):
                    meta["db02_sw_version"] = sw_ver.decode("ascii")

            db01_slice = raw[BANK0_DB01_OFF:DB01_END_VA_EXCL]
            return LoadedMfk3Image(
                source_path=path,
                kind=kind,
                full_dump=raw,
                db01_slice_start=BANK0_DB01_OFF,
                db01_slice_end=DB01_END_VA_EXCL,
                db01_bytes=db01_slice,
                extra_meta=meta,
            )

    # Case 2: Standalone unpacked DB_01FLASHDATA.bin (e.g. 1,802,008 B or 1,802,240 B, or 0220_FBL for inspection)
    if size >= 8 and raw[:8] == DB01_EXPECTED_HEADER_8B and size <= DB01_MAX_REGION_SIZE:
        return LoadedMfk3Image(
            source_path=path,
            kind="raw_db01",
            full_dump=raw,
            db01_slice_start=0,
            db01_slice_end=size,
            db01_bytes=raw,
            extra_meta=meta,
        )

    # Guard against 0220_FBL updater raw DB_01 if header differs
    if size == FBL_UPDATER_DB01_SIZE:
        raise ValueError(
            tr(
                f"{path.name} ({size:,} байт) — это пакет обновления бутлоадера 0220_FBL, а не приложение MEAPP (DB_01)!",
                f"{path.name} ({size:,} bytes) is the 0220_FBL bootloader updater, not the MEAPP application (DB_01)!",
            )
        )

    # Helpful diagnostic if someone accidentally passed DB_02FLASHDATA.bin or BF_01 compressed file!
    if size >= 4 and all(0x30 <= b <= 0x39 for b in raw[:4]):
        raise ValueError(
            tr(
                f"{path.name} выглядит как DB_02FLASHDATA.bin (ASCII '{raw[:4].decode()}', PE2 @ 0x00800000). "
                f"Система KS и таблица FeC находятся в DB_01FLASHDATA.bin (PE1 @ 0x00048000)!",
                f"{path.name} looks like DB_02FLASHDATA.bin (ASCII '{raw[:4].decode()}', PE2 @ 0x00800000). "
                f"KS and FeC logic live inside DB_01FLASHDATA.bin (PE1 @ 0x00048000)!",
            )
        )
    if path.name.upper().startswith("BF_") and "_01_" in path.name.upper():
        raise ValueError(
            tr(
                f"{path.name} — это сжатый LZSS файл данных BF_*.bin без XML-обёртки. "
                f"Передайте сам контейнер FL_..._MEAPP_V001_S.odx-f (лежащий рядом) или распакованный DB_01FLASHDATA.bin!",
                f"{path.name} is a standalone compressed BF_*.bin datafile. "
                f"Pass the sibling FL_..._MEAPP_V001_S.odx-f container or unpacked DB_01FLASHDATA.bin instead!",
            )
        )

    raise ValueError(
        tr(
            f"Не удалось распознать формат {path.name} ({size:,} байт). Поддерживаются: "
            f"распакованный DB_01FLASHDATA.bin, дамп Bank 0 (2 МиБ) / Bank 0+1 (4 МиБ) / 10 МиБ, либо .odx-f / .odx / .frf.",
            f"Unrecognized input format {path.name} ({size:,} bytes). Supported inputs: "
            f"unpacked DB_01FLASHDATA.bin, RH850 Bank 0 (2 MiB) / Dual-Bank (4 MiB) / 10 MiB dump, or .odx-f / .odx / .frf.",
        )
    )


def find_sibling_mfk3_template_odx(source_path: Path) -> Path | None:
    """Auto-locate a sibling factory `MEAPP` `.odx-f`/`.odx`/`.frf` container near `source_path`."""
    base = source_path.resolve().parent
    search_dirs: list[Path] = [base]
    for up in (base.parent, base.parent.parent):
        if up.is_dir():
            search_dirs.append(up)
            swdl = up / "packed" / "swdl"
            if swdl.is_dir():
                search_dirs.insert(0, swdl)

    seen: set[Path] = set()
    for d in search_dirs:
        if d in seen or not d.is_dir():
            continue
        seen.add(d)
        try:
            for item in sorted(d.iterdir(), key=lambda p: p.name.lower()):
                if not item.is_file():
                    continue
                low = item.name.lower()
                if "fbl" in low or "part1" in low or "part2" in low or low == "index.xml":
                    continue
                if low.endswith((".odx-f", ".odx", ".pdx", ".frf")) and ("2q0980653" in low or "meapp" in low):
                    return item
        except OSError:
            continue
    return None


def resolve_mfk3_sw_version(
    loaded_meta: dict[str, str],
    tmpl_meta: dict[str, str],
    fallback_filename: str = "",
) -> str:
    """Resolve 4-character MFK3 SW version (`13xx` / `14xx`) dynamically without hardcoding `1423`."""
    db02_ver = (loaded_meta.get("db02_sw_version") or "").strip()
    if re.fullmatch(r"[0-9A-Za-z]{4}", db02_ver):
        return db02_ver

    for rev in (tmpl_meta.get("revision"), loaded_meta.get("revision")):
        if rev:
            m_rev = re.match(r"^([0-9A-Za-z]{4})(?:_|$)", rev.strip())
            if m_rev:
                return m_rev.group(1)

    for sn in (tmpl_meta.get("flash_short_name"), loaded_meta.get("flash_short_name"), fallback_filename):
        if sn:
            m_sn = re.search(r"FL_[0-9A-Za-z]+_([0-9A-Za-z]{4})(?:_|\b)", sn)
            if m_sn:
                return m_sn.group(1)

    return "0000"


def build_mfk3_part1_part2_odx(
    patched_db01: bytes,
    template_xml: str,
    template_blocks: dict[str, OdxBlockEntry],
    out_dir: Path,
    *,
    odx_layout: str = "extern",
    include_part2: bool = True,
    part_number_prefix: str = "2Q0980653J",
    sw_version: str = "1423",
    rev_label: str | None = None,
    stem_tag: str = "KS_FEC",
) -> list[Path]:
    """Generate ODIS-E 17/18 `PART1` (and optional `PART2`) ODX packages from `patched_db01` (method `00` only)."""
    if "DB_30ERASEPROGRROUTI" not in template_blocks:
        raise ValueError("Template ODX is missing required DB_30ERASEPROGRROUTI block!")
    b30 = template_blocks["DB_30ERASEPROGRROUTI"]
    if not b30.signature_hex:
        raise ValueError("Template ODX DB_30ERASEPROGRROUTI is missing <FW-SIGNATURE>!")

    b01_tmpl = template_blocks.get("DB_01FLASHDATA")
    if b01_tmpl and b01_tmpl.signature_hex:
        sig01 = b01_tmpl.signature_hex
    elif sw_version == "1423":
        sig01 = STOCK_DB01_1423_SIGNATURE_HEX
    else:
        raise ValueError(f"Template ODX DB_01FLASHDATA is missing <FW-SIGNATURE> for SW {sw_version}!")

    # Trim 0xFF tail padding if patched_db01 came from a 2 MiB / 4 MiB bank dump (0x1B8000 -> DB_01 UNCOMPRESSED-SIZE)
    if (
        b01_tmpl is not None
        and len(patched_db01) > b01_tmpl.uncompressed_size
        and patched_db01[b01_tmpl.uncompressed_size :] == b"\xFF" * (len(patched_db01) - b01_tmpl.uncompressed_size)
    ):
        patched_db01 = patched_db01[: b01_tmpl.uncompressed_size]

    crc01 = zlib.crc32(patched_db01) & 0xFFFFFFFF
    crc01_hex = f"{crc01:08X}"
    # MFK3 DB_01 is strictly emitted uncompressed (method 00, SIG_SHA1-RSA1024_S)
    db01_payload = patched_db01
    db01_csize: int | None = None

    layout_norm = odx_layout.strip().lower()
    if layout_norm not in ("extern", "intern", "both"):
        raise ValueError(f"Unsupported --odx-layout {odx_layout!r} (expected 'extern', 'intern', or 'both')")

    crc30 = zlib.crc32(b30.uncompressed) & 0xFFFFFFFF
    bf30_name = b30.datafile_name or f"BF_{part_number_prefix}_30_0000_{crc30:08X}.bin"
    bf01_name = f"BF_{part_number_prefix}_01_0000_{crc01_hex}.bin"

    p1_overrides: dict[str, dict[str, object]] = {
        "DB_30ERASEPROGRROUTI": {
            "method_hex": f"{b30.method:02X}",
            "uncompressed_size": b30.uncompressed_size,
            "compressed_size": len(b30.raw_payload) if b30.method == 0xA0 else None,
            "crc32_hex": f"{crc30:08X}",
            "signature_hex": b30.signature_hex,
            "payload_bytes": b30.raw_payload,
            "datafile_name": bf30_name,
        },
        "DB_01FLASHDATA": {
            "method_hex": "00",
            "uncompressed_size": len(patched_db01),
            "compressed_size": db01_csize,
            "crc32_hex": crc01_hex,
            "signature_hex": sig01,
            "payload_bytes": db01_payload,
            "datafile_name": bf01_name,
        },
    }

    written: list[Path] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    stem_base = f"FL_{part_number_prefix}_{sw_version}_{stem_tag}"
    eff_rev_label = rev_label or f"{sw_version}_V001"
    p1_ident = f"{part_number_prefix}_{sw_version}_{stem_tag}_PART1_S"
    p2_ident = f"{part_number_prefix}_{sw_version}_{stem_tag}_PART2_S"

    if layout_norm in ("extern", "both"):
        p1_dir = out_dir / "PART1"
        p1_dir.mkdir(parents=True, exist_ok=True)
        odxf_p1_name = f"{stem_base}_PART1_S.odx-f"
        xml_p1_ext = build_single_odx_xml(
            template_xml,
            ("DB_30ERASEPROGRROUTI", "DB_01FLASHDATA"),
            MFK3_DB_TO_FD_MAP,
            p1_overrides,
            intern_flashdata=False,
            container_ident=p1_ident,
            long_name_suffix=f"{stem_tag}_PART1_S",
        )
        p1_odxf = p1_dir / odxf_p1_name
        p1_odxf.write_text(xml_p1_ext, encoding="utf-8")
        (p1_dir / bf30_name).write_bytes(b30.raw_payload)
        (p1_dir / bf01_name).write_bytes(db01_payload)
        idx_p1 = p1_dir / "index.xml"
        idx_p1.write_text(
            build_catalog_index_xml(
                f"{stem_base}_PART1_E",
                odxf_p1_name,
                [bf30_name, bf01_name],
                rev_label=eff_rev_label,
            ),
            encoding="utf-8",
        )
        written.extend([p1_odxf, p1_dir / bf30_name, p1_dir / bf01_name, idx_p1])

    if layout_norm in ("intern", "both"):
        xml_p1_int = build_single_odx_xml(
            template_xml,
            ("DB_30ERASEPROGRROUTI", "DB_01FLASHDATA"),
            MFK3_DB_TO_FD_MAP,
            p1_overrides,
            intern_flashdata=True,
            container_ident=p1_ident,
            long_name_suffix=f"{stem_tag}_PART1_S",
        )
        p1_odx = out_dir / f"{stem_base}_PART1_S.odx"
        p1_odx.write_text(xml_p1_int, encoding="utf-8")
        written.append(p1_odx)

    if include_part2 and "DB_04FLASHDATA" in template_blocks:
        b04 = template_blocks["DB_04FLASHDATA"]
        if not b04.signature_hex:
            raise ValueError("Template ODX DB_04FLASHDATA is missing <FW-SIGNATURE>!")
        crc04 = zlib.crc32(b04.uncompressed) & 0xFFFFFFFF
        bf04_name = b04.datafile_name or f"BF_{part_number_prefix}_04_0000_{crc04:08X}.bin"
        p2_overrides: dict[str, dict[str, object]] = {
            "DB_30ERASEPROGRROUTI": p1_overrides["DB_30ERASEPROGRROUTI"],
            "DB_04FLASHDATA": {
                "method_hex": f"{b04.method:02X}",
                "uncompressed_size": b04.uncompressed_size,
                "compressed_size": len(b04.raw_payload) if b04.method == 0xA0 else None,
                "crc32_hex": f"{crc04:08X}",
                "signature_hex": b04.signature_hex,
                "payload_bytes": b04.raw_payload,
                "datafile_name": bf04_name,
            },
        }
        if layout_norm in ("extern", "both"):
            p2_dir = out_dir / "PART2"
            p2_dir.mkdir(parents=True, exist_ok=True)
            odxf_p2_name = f"{stem_base}_PART2_S.odx-f"
            xml_p2_ext = build_single_odx_xml(
                template_xml,
                ("DB_30ERASEPROGRROUTI", "DB_04FLASHDATA"),
                MFK3_DB_TO_FD_MAP,
                p2_overrides,
                intern_flashdata=False,
                container_ident=p2_ident,
                long_name_suffix=f"{stem_tag}_PART2_S",
            )
            p2_odxf = p2_dir / odxf_p2_name
            p2_odxf.write_text(xml_p2_ext, encoding="utf-8")
            (p2_dir / bf30_name).write_bytes(b30.raw_payload)
            (p2_dir / bf04_name).write_bytes(b04.raw_payload)
            idx_p2 = p2_dir / "index.xml"
            idx_p2.write_text(
                build_catalog_index_xml(
                    f"{stem_base}_PART2_E",
                    odxf_p2_name,
                    [bf30_name, bf04_name],
                    rev_label=eff_rev_label,
                ),
                encoding="utf-8",
            )
            written.extend([p2_odxf, p2_dir / bf30_name, p2_dir / bf04_name, idx_p2])

        if layout_norm in ("intern", "both"):
            xml_p2_int = build_single_odx_xml(
                template_xml,
                ("DB_30ERASEPROGRROUTI", "DB_04FLASHDATA"),
                MFK3_DB_TO_FD_MAP,
                p2_overrides,
                intern_flashdata=True,
                container_ident=p2_ident,
                long_name_suffix=f"{stem_tag}_PART2_S",
            )
            p2_odx = out_dir / f"{stem_base}_PART2_S.odx"
            p2_odx.write_text(xml_p2_int, encoding="utf-8")
            written.append(p2_odx)

    return written
