# -*- coding: utf-8 -*-
"""2Q0 kamera VERİ SETİ (dataset) düzenleyici — saf mantık, Tkinter yok.

Format bilgisi VWHacking 2Q0 Camera Dataset Editor'ün (v0.3.5) çalışma
biçiminden çıkarıldı; uygulama internetten hiçbir şey çekmez, dosya
kullanıcıdan gelir.

Veri seti = 64 KB (0x10000) blok (ODX içinde DB_7100FLASHDATA):
  0x0010  araç uzunluğu            float32 (m)      → mm  = ×1000
  0x0014  araç genişliği            float32 (m)      → mm
  0x0018  araç yüksekliği           float32 (m)      → mm
  0x0028  aks aralığı               float32 (m)      → mm
  0x004C  kamera montaj yüksekliği  float32 (m)      → mm
  0x05B4  KLR uyarısına kadar süre  float32 (s×100)  → sn  = ÷100
  0x0CD8  Lane Assist hızı          float32 (km/h)
  0x0E44  şerit takibi (ALG) hızı   float32 (km/h)
  0x0F28  FLA başlangıç hızı        float32 (km/h)
  0x0F40  FLA bitiş hızı            float32 (km/h)
  0x030C  4 bayt XOR imzası (bölge: 0x0310 .. 0x1A7C)
  0xFFE5  12 bayt proje etiketi (ASCII)
  0xFFF8  4 bayt CRC-32 (bölge: 0x0000 .. son-2-bayttan okunan uzunluk)
  0xFFFE  2 bayt CRC kapsam uzunluğu (big-endian)

İmza kuralı (araç yazılımının beklediği): yeni imza = eski imza XOR
değişen baytların (eski XOR yeni) toplamı — yalnız 0x0310..0x1A7C aralığı.
CRC-32 standart (zlib) ve imza yazıldıktan SONRA hesaplanır.
"""

from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
import tempfile
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

DATASET_SIZE = 0x10000
SIG_OFFSET = 0x030C
SIG_RANGE_START = 0x0310          # imza bölgesi başlangıcı (seed hariç)
SIG_RANGE_END = 6780              # 0x1A7C — bitişik DEĞİL, mutlak bitiş
PROJECT_OFFSET = 0xFFE5
PROJECT_LEN = 12
CRC_OFFSET = 0xFFF8
CRC_LEN_OFFSET = 0xFFFE
DEFAULT_CRC_SPAN = 0xFFF8

DATASET_BLOCK_NAME = "DB_7100FLASHDATA"

ARCHIVE_SUFFIXES = {".zip", ".7z", ".rar", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".cab"}
_SEVENZIP_CANDIDATES = (
    r"C:\Program Files\7-Zip\7z.exe",
    r"C:\Program Files (x86)\7-Zip\7z.exe",
    r"C:\Program Files\NanaZip\NanaZip.exe",
    r"C:\Program Files\WinRAR\WinRAR.exe",
)


# --------------------------------------------------------------------------- #
# Arşiv (zip / 7z / rar) desteği
# --------------------------------------------------------------------------- #
def find_7zip() -> Path | None:
    """7z.exe'yi PATH'te ve bilinen kurulum yerlerinde ara."""
    exe = shutil.which("7z") or shutil.which("7za") or shutil.which("7zz")
    if exe:
        return Path(exe)
    for cand in _SEVENZIP_CANDIDATES:
        p = Path(cand)
        if p.is_file():
            return p
    return None


def find_bsdtar() -> Path | None:
    """Windows'un kendi bsdtar'ı (libarchive: zip, 7z ve rar okur)."""
    for cand in (r"C:\Windows\System32\tar.exe", r"C:\Windows\SysWOW64\tar.exe"):
        p = Path(cand)
        if p.is_file():
            return p
    exe = shutil.which("bsdtar")
    return Path(exe) if exe else None


def is_archive(path: str | Path) -> bool:
    p = Path(path)
    if p.suffix.lower() in ARCHIVE_SUFFIXES:
        return True
    try:
        with p.open("rb") as fh:
            magic = fh.read(8)
    except OSError:
        return False
    return magic[:2] == b"PK" or magic[:6] == b"7z\xbc\xaf\x27\x1c" or magic[:4] == b"Rar!"


def extract_archive(path: str | Path, dest: str | Path | None = None) -> tuple[Path, list[Path]]:
    """Arşivi geçici klasöre açar; (hedef klasör, dosya listesi) döndürür."""
    src = Path(path)
    out_dir = Path(dest) if dest else Path(tempfile.mkdtemp(prefix="2q0_ds_"))
    out_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []

    if zipfile.is_zipfile(src):
        try:
            with zipfile.ZipFile(src) as zf:
                zf.extractall(out_dir)
            return out_dir, [p for p in out_dir.rglob("*") if p.is_file()]
        except Exception as exc:  # noqa: BLE001
            errors.append(f"zipfile: {exc}")

    seven = find_7zip()
    if seven is not None:
        try:
            proc = subprocess.run([str(seven), "x", "-y", f"-o{out_dir}", str(src)],
                                  capture_output=True, timeout=180)
            if proc.returncode == 0:
                files = [p for p in out_dir.rglob("*") if p.is_file()]
                if files:
                    return out_dir, files
            errors.append(f"7z rc={proc.returncode}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"7z: {exc}")

    tar = find_bsdtar()
    if tar is not None:
        try:
            proc = subprocess.run([str(tar), "-xf", str(src), "-C", str(out_dir)],
                                  capture_output=True, timeout=180)
            if proc.returncode == 0:
                files = [p for p in out_dir.rglob("*") if p.is_file()]
                if files:
                    return out_dir, files
            errors.append(f"bsdtar rc={proc.returncode}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"bsdtar: {exc}")

    raise ValueError(
        "Arşiv açılamadı (" + src.name + "). " + "; ".join(errors) +
        "\nÇözüm: 7-Zip kurulu olsun (C:\\Program Files\\7-Zip\\7z.exe) "
        "veya arşivi elle çıkarıp dosyayı doğrudan seç.")


def _looks_like_dataset_xml(p: Path) -> bool:
    if p.suffix.lower() not in (".odx-f", ".odx", ".xml"):
        return False
    try:
        with p.open("rb") as fh:
            head = fh.read(4096)
            if b"DB_7100" in head or b"FLASHDATA" in head:
                return True
            fh.seek(0)
            chunk = fh.read(2_000_000)
            return b"DB_7100" in chunk
    except OSError:
        return False


def pick_dataset_file(files: Iterable[Path]) -> tuple[Path | None, list[Path]]:
    """Açılan arşivdeki dosyalardan veri setini seçer; (seçilen, adaylar)."""
    files = [f for f in files if f.is_file()]
    candidates: list[Path] = []
    for f in files:
        if _looks_like_dataset_xml(f):
            candidates.append(f)
    if not candidates:
        for f in files:
            if f.suffix.lower() == ".bin":
                try:
                    if f.stat().st_size == DATASET_SIZE:
                        candidates.append(f)
                except OSError:
                    pass
    if not candidates:
        for f in files:
            try:
                if f.stat().st_size == DATASET_SIZE:
                    candidates.append(f)
            except OSError:
                pass
    if not candidates:
        return None, files
    # en büyük ODX önce, yoksa ilk .bin
    candidates.sort(key=lambda p: (p.suffix.lower() != ".bin", -p.stat().st_size))
    return candidates[0], candidates


# --------------------------------------------------------------------------- #
# Alan tanımları
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Field:
    key: str
    offset: int
    label: str
    unit: str
    decode: float = 1.0      # ham → gösterim çarpanı
    encode: float = 1.0      # gösterim → ham çarpanı
    minimum: float | None = None
    maximum: float | None = None
    digits: int = 0
    advanced: bool = False

    def show(self, raw_value: float) -> float:
        return raw_value * self.decode

    def store(self, shown: float) -> float:
        return shown * self.encode


_MM = dict(decode=1000.0, encode=0.001, minimum=500.0, maximum=8000.0, digits=0)
_S = dict(decode=0.01, encode=100.0, minimum=5.0, maximum=600.0, digits=2)
_KMH = dict(decode=1.0, encode=1.0, minimum=0.0, maximum=300.0, digits=0)

FIELDS: list[Field] = [
    Field("carLength", 0x0010, "Araç uzunluğu", "mm", **_MM),
    Field("carWidth", 0x0014, "Araç genişliği", "mm", **_MM),
    Field("carHeight", 0x0018, "Araç yüksekliği", "mm", **_MM),
    Field("wheelbaseLength", 0x0028, "Aks aralığı (dingil mesafesi)", "mm", **_MM),
    Field("cameraInstallHeight", 0x004C, "Kamera montaj yüksekliği", "mm", **_MM),
    Field("timeToKlrWarning", 0x05B4, "KLR uyarısına kadar süre", "sn", **_S),
    Field("laneAssistActivationSpeed", 0x0CD8, "Lane Assist devreye girme hızı", "km/h", **_KMH),
    Field("laneGuidanceActivationSpeed", 0x0E44, "Şerit takibi (ALG) devreye girme hızı", "km/h", **_KMH),
    Field("flaStartNo4B", 0x0F28, "FLA başlangıç hızı (no 4B)", "km/h", **_KMH),
    Field("flaStopNo4B", 0x0F40, "FLA bitiş hızı (no 4B)", "km/h", **_KMH),
]

ADVANCED_FIELDS: list[Field] = [
    Field("laneKeepingSpeedNoAcc", 0x0E68, "Lane Keeping hızı (ACC yok)", "km/h",
          decode=1.0, encode=1.0, minimum=0.0, maximum=300.0, digits=0, advanced=True),
    Field("fusionDefault30", 0x06AC, "Füzyon varsayılanı 0x6AC", "", advanced=True),
    Field("fusionDefault502", 0x06D4, "Füzyon varsayılanı 0x6D4", "", advanced=True),
    Field("fusionDefault50", 0x07A4, "Füzyon varsayılanı 0x7A4", "", advanced=True),
]

ALL_FIELDS: list[Field] = FIELDS + ADVANCED_FIELDS

FIELD_BY_KEY = {f.key: f for f in ALL_FIELDS}


def f32(raw: bytes, offset: int) -> float:
    return struct.unpack_from("<f", raw, offset)[0]


def put_f32(buf: bytearray, offset: int, value: float) -> None:
    struct.pack_into("<f", buf, offset, float(value))


# --------------------------------------------------------------------------- #
# İmza / CRC
# --------------------------------------------------------------------------- #
def stored_signature(raw: bytes) -> bytes:
    return bytes(raw[SIG_OFFSET:SIG_OFFSET + 4])


def fix_signature(original: bytes, edited: bytearray) -> bytes:
    """Eski imzayı, değişen baytların deltasıyla günceller (araç yazılımının kuralı)."""
    sig = bytearray(original[SIG_OFFSET:SIG_OFFSET + 4])
    for i in range(SIG_RANGE_START, min(SIG_RANGE_END, len(edited), len(original))):
        old, new = original[i], edited[i]
        if old != new:
            sig[i & 3] ^= old ^ new
    return bytes(sig)


def crc_span(raw: bytes) -> int:
    """CRC kapsam uzunluğu: son 2 bayt (big-endian); 0 ise varsayılan 0xFFF8."""
    if len(raw) < CRC_LEN_OFFSET + 2:
        return min(DEFAULT_CRC_SPAN, max(0, len(raw) - 8))
    span = int.from_bytes(raw[CRC_LEN_OFFSET:CRC_LEN_OFFSET + 2], "big")
    if span == 0 or span > len(raw) - 2:
        return DEFAULT_CRC_SPAN
    return span


def stored_crc(raw: bytes) -> int:
    return int.from_bytes(raw[CRC_OFFSET:CRC_OFFSET + 4], "big")


def computed_crc(raw: bytes) -> int:
    span = crc_span(raw)
    return zlib.crc32(raw[:span]) & 0xFFFFFFFF


def finalize(original: bytes, edited: bytearray) -> bytes:
    """İmza + CRC'yi yeniden yazar, doğrulanmış 64 KB bloğu döndürür."""
    if len(edited) != len(original):
        raise ValueError("Veri seti boyutu değişmemeli")
    sig = fix_signature(original, edited)
    edited[SIG_OFFSET:SIG_OFFSET + 4] = sig
    span = crc_span(bytes(edited))
    crc = zlib.crc32(bytes(edited[:span])) & 0xFFFFFFFF
    edited[CRC_OFFSET:CRC_OFFSET + 4] = crc.to_bytes(4, "big")
    out = bytes(edited)
    if stored_crc(out) != computed_crc(out):
        raise RuntimeError("CRC-32 doğrulaması tutmadı (iç hata)")
    return out


def diff_bytes(a: bytes, b: bytes) -> list[int]:
    return [i for i in range(min(len(a), len(b))) if a[i] != b[i]]


def project_tag(raw: bytes) -> str:
    chunk = raw[PROJECT_OFFSET:PROJECT_OFFSET + PROJECT_LEN]
    return chunk.split(b"\x00")[0].decode("latin-1", "replace")


def set_project_tag(buf: bytearray, tag: str) -> None:
    if len(tag) > PROJECT_LEN:
        raise ValueError(f"Proje etiketi en fazla {PROJECT_LEN} karakter")
    padded = tag.encode("ascii", "replace")[:PROJECT_LEN].ljust(PROJECT_LEN, b"\x00")
    buf[PROJECT_OFFSET:PROJECT_OFFSET + PROJECT_LEN] = padded


# --------------------------------------------------------------------------- #
# Yükleme / kaydetme
# --------------------------------------------------------------------------- #
@dataclass
class Dataset:
    raw: bytes
    kind: str                       # "odx" | "bin"
    source: Path | None = None
    xml_text: str | None = None
    method: int = 0x00              # dosyadaki sıkıştırma yöntemi
    block_name: str = DATASET_BLOCK_NAME
    part_number: str = ""
    archive: Path | None = None     # arşivden geldiyse kaynak arşiv
    archive_member: str = ""        # arşiv içindeki göreli yol
    extract_dir: Path | None = None # arşivin açıldığı klasör
    extracted: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def size_ok(self) -> bool:
        return len(self.raw) == DATASET_SIZE

    def values(self) -> dict[str, float]:
        return {f.key: f.show(f32(self.raw, f.offset)) for f in ALL_FIELDS}

    def raw_values(self) -> dict[str, float]:
        return {f.key: f32(self.raw, f.offset) for f in ALL_FIELDS}

    def crc_ok(self) -> bool:
        return stored_crc(self.raw) == computed_crc(self.raw)


def _pick_dataset_block(root: ET.Element) -> tuple[ET.Element, ET.Element | None, str]:
    """(FLASHDATA, DATABLOCK|None, blok adı) döndürür."""
    flashdata = {fd.get("ID"): fd for fd in root.iter("FLASHDATA")}
    blocks = list(root.iter("DATABLOCK"))
    for db in blocks:
        name = (db.findtext("SHORT-NAME") or "").strip()
        if not (name.startswith("DB_7100") or "DB_7100" in (db.get("ID") or "")):
            continue
        ref = db.find("FLASHDATA-REF")
        fd = flashdata.get(ref.get("ID-REF")) if ref is not None else None
        if fd is not None:
            return fd, db, name or DATASET_BLOCK_NAME
    # site davranışı: ikinci FLASHDATA
    fds = list(root.iter("FLASHDATA"))
    if len(fds) < 2:
        raise ValueError("ODX içinde en az 2 FLASHDATA olmalı (veri seti ikincisidir)")
    return fds[1], None, (fds[1].findtext("SHORT-NAME") or "FLASHDATA#2").strip()


def load(path: str | Path) -> Dataset:
    """Veri setini yükler; .zip/.7z/.rar arşivleri otomatik açılır."""
    p = Path(path)
    if is_archive(p):
        extract_dir, files = extract_archive(p)
        chosen, candidates = pick_dataset_file(files)
        if chosen is None:
            listing = ", ".join(f.name for f in files[:12]) or "(boş)"
            raise ValueError(
                f"{p.name} içinde 2Q0 veri seti bulunamadı.\n"
                f"Arşivdeki dosyalar: {listing}\n"
                "Aranan: DB_7100 içeren .odx-f/.xml veya 65536 baytlık .bin")
        ds = _load_file(chosen)
        ds.archive = p
        ds.archive_member = str(chosen.relative_to(extract_dir))
        ds.extract_dir = extract_dir
        ds.extracted = files
        if len(candidates) > 1:
            others = ", ".join(c.name for c in candidates[1:4])
            ds.warnings.append(f"Arşivde {len(candidates)} aday vardı, ilki seçildi ({chosen.name}). "
                               f"Diğerleri: {others}")
        return ds
    return _load_file(p)


def _load_file(path: str | Path) -> Dataset:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".bin":
        raw = p.read_bytes()
        return Dataset(raw=raw, kind="bin", source=p)

    text = p.read_text(encoding="utf-8", errors="replace")
    if suffix == ".frf":
        raise ValueError("FRF konteyneri veri seti değil — dataset .odx-f/.xml veya 64 KB .bin ver")
    root = ET.fromstring(text)
    fd, db, block_name = _pick_dataset_block(root)
    method_txt = (fd.findtext("ENCRYPT-COMPRESS-METHOD") or "00").strip().upper()
    method = int(method_txt, 16) if re.fullmatch(r"[0-9A-F]{2}", method_txt) else 0x00

    data_el = fd.find("DATA")
    if data_el is not None and (data_el.text or "").strip():
        payload = bytes.fromhex("".join((data_el.text or "").split()))
    else:
        datafile = (fd.findtext("DATAFILE") or "").strip()
        if not datafile:
            raise ValueError("Veri seti FLASHDATA içinde DATA veya DATAFILE yok")
        payload = (p.parent / datafile).read_bytes()

    if method == 0xA0:
        payload = _lzss_decompress(payload)
    elif method != 0x00:
        raise ValueError(f"Desteklenmeyen ENCRYPT-COMPRESS-METHOD 0x{method:02X}")

    warnings: list[str] = []
    if len(payload) != DATASET_SIZE:
        warnings.append(
            f"Beklenen 65536 bayt, bulunan {len(payload)} bayt — bu bir 2Q0 dataset'i olmayabilir")

    part = ""
    for el in root.iter("PARTNUMBER"):
        if (el.text or "").strip():
            part = el.text.strip()
            break

    return Dataset(raw=payload, kind="odx", source=p, xml_text=text,
                   method=method, block_name=block_name, part_number=part,
                   warnings=warnings)


def _lzss_decompress(payload: bytes) -> bytes:
    """Projedeki motor (ks_patcher) LZSS-A0 çözücüsünü kullanır."""
    try:
        from motor.core.containers import lzss_a0_decompress  # type: ignore
    except Exception:  # noqa: BLE001
        from core.containers import lzss_a0_decompress  # type: ignore
    return lzss_a0_decompress(payload)


def apply_values(ds: Dataset, shown: dict[str, float], *, project: str | None = None) -> tuple[bytes, list[int]]:
    """Gösterim değerlerini yazar, imza+CRC'yi düzeltir; (yeni baytlar, fark listesi)."""
    buf = bytearray(ds.raw)
    for key, value in shown.items():
        f = FIELD_BY_KEY.get(key)
        if f is None:
            continue
        put_f32(buf, f.offset, f.store(float(value)))
    if project:
        set_project_tag(buf, project)
    new_raw = finalize(ds.raw, buf)
    return new_raw, diff_bytes(ds.raw, new_raw)


def _replace_hex_data(xml_text: str, fd_id: str | None, hex_body: str) -> str:
    """Verilen FLASHDATA'nın <DATA> içeriğini değiştirir (kimliğe göre, yoksa 2.)"""
    if fd_id:
        pat = re.compile(
            r"(<FLASHDATA\b[^>]*\bID=\"" + re.escape(fd_id) + r"\"[^>]*>.*?<DATA[^>]*>)(.*?)(</DATA>)",
            re.DOTALL)
        m = pat.search(xml_text)
        if m:
            return xml_text[:m.start(2)] + hex_body + xml_text[m.end(2):]
    # kimlik bulunamadı: ikinci FLASHDATA'nın DATA'sı
    count = 0
    for m in re.finditer(r"(<FLASHDATA\b[^>]*>.*?<DATA[^>]*>)(.*?)(</DATA>)", xml_text, re.DOTALL):
        count += 1
        if count == 2:
            return xml_text[:m.start(2)] + hex_body + xml_text[m.end(2):]
    raise ValueError("ODX içinde değiştirilecek <DATA> bulunamadı")


def _set_method_no_compression(xml_text: str, fd_id: str | None) -> str:
    def _sub(m: re.Match[str]) -> str:
        return m.group(1) + "00" + m.group(3)

    if fd_id:
        pat = re.compile(
            r"(<FLASHDATA\b[^>]*\bID=\"" + re.escape(fd_id) +
            r"\"[^>]*>.*?<ENCRYPT-COMPRESS-METHOD[^>]*>)([^<]*)(</ENCRYPT-COMPRESS-METHOD>)",
            re.DOTALL)
        if pat.search(xml_text):
            return pat.sub(_sub, xml_text, count=1)
    out, count = [], 0
    for m in re.finditer(r"(<FLASHDATA\b[^>]*>.*?<ENCRYPT-COMPRESS-METHOD[^>]*>)([^<]*)(</ENCRYPT-COMPRESS-METHOD>)",
                         xml_text, re.DOTALL):
        count += 1
        if count == 2:
            return xml_text[:m.start(2)] + "00" + xml_text[m.end(2):]
    return xml_text


def _drop_compressed_size(xml_text: str) -> str:
    return re.sub(r"[ \t]*<COMPRESSED-SIZE>[^<]*</COMPRESSED-SIZE>[ \t]*\r?\n?", "", xml_text)


def _drop_dataset_security(xml_text: str) -> str:
    """Yalnız DB_7100 (dataset) DATABLOCK'u içindeki FW-CHECKSUM'lu SECURITY'leri kaldırır."""
    block_re = re.compile(r"<DATABLOCK\b[^>]*DB_7100[^>]*>.*?</DATABLOCK>", re.DOTALL)
    sec_re = re.compile("<SECURITY>.*?</SECURITY>", re.DOTALL)

    def _clean_block(m: re.Match[str]) -> str:
        block = m.group(0)

        def _sub(sec: re.Match[str]) -> str:
            return "" if "FW-CHECKSUM" in sec.group(0) else sec.group(0)

        return sec_re.sub(_sub, block)

    if not block_re.search(xml_text):
        return xml_text
    return block_re.sub(_clean_block, xml_text)


def _render_odx_text(ds: Dataset, new_raw: bytes) -> str:
    """Veri setini ODX metnine gömer (sıkıştırmasız, dataset imzası kaldırılmış)."""
    if not ds.xml_text:
        raise ValueError("Kaynak ODX metni yok")
    root = ET.fromstring(ds.xml_text)
    fd, _db, _name = _pick_dataset_block(root)
    fd_id = fd.get("ID")

    hex_body = new_raw.hex().upper()
    text = _replace_hex_data(ds.xml_text, fd_id, hex_body)
    text = _set_method_no_compression(text, fd_id)
    text = _drop_compressed_size(text)
    text = _drop_dataset_security(text)
    text = re.sub(r"(<UNCOMPRESSED-SIZE>)(\d+)(</UNCOMPRESSED-SIZE>)",
                  lambda m: m.group(1) + str(len(new_raw)) + m.group(3), text, count=1)

    # sağlama: yeni XML gerçekten istediğimiz baytları taşıyor mu?
    check_root = ET.fromstring(text)
    fd2, _db2, _n2 = _pick_dataset_block(check_root)
    payload = bytes.fromhex("".join((fd2.findtext("DATA") or "").split()))
    if payload != new_raw:
        raise RuntimeError("Yazılan ODX doğrulanamadı (DATA içeriği uyuşmuyor)")
    return text


def _save_archive(ds: Dataset, new_raw: bytes, out: Path) -> Path:
    """Arşivden gelen veri setini, diğer dosyaları koruyarak yeni bir .zip'e yazar."""
    if out.suffix.lower() != ".zip":
        out = out.with_suffix(".zip")
    if ds.extract_dir is None or not ds.extracted:
        raise ValueError("Arşiv içeriği bellekte yok")
    member = ds.archive_member or (ds.source.name if ds.source else "dataset.bin")
    payload = (_render_odx_text(ds, new_raw).encode("utf-8") if ds.kind == "odx" else new_raw)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in ds.extracted:
            try:
                rel = str(f.relative_to(ds.extract_dir))
            except ValueError:
                continue
            if rel.replace("\\", "/").lower() == member.replace("\\", "/").lower():
                zf.writestr(rel, payload)
            else:
                zf.write(f, rel)
    return out


def save(ds: Dataset, out_path: str | Path, new_raw: bytes, *, project: str | None = None) -> Path:
    """Yeni veri setini yazar: .bin → ham, ODX → sıkıştırmasız konteyner, arşiv → .zip."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if ds.archive is not None:
        return _save_archive(ds, new_raw, out)
    if ds.kind == "bin" or out.suffix.lower() == ".bin":
        out.write_bytes(new_raw)
        return out

    out.write_text(_render_odx_text(ds, new_raw), encoding="utf-8")
    return out


def summary(ds: Dataset) -> dict[str, object]:
    kaynak = ds.source.name if ds.source else "—"
    if ds.archive is not None:
        kaynak = f"{ds.archive.name} → {ds.archive_member}"
    return {
        "dosya": kaynak,
        "tür": "ODX-F (konteyner)" if ds.kind == "odx" else "ham .bin",
        "boyut": len(ds.raw),
        "blok": ds.block_name,
        "sıkıştırma": "yok (00)" if ds.method == 0x00 else "LZSS (A0) → yazarken 00",
        "parça_no": ds.part_number or "—",
        "proje_etiketi": project_tag(ds.raw) or "—",
        "crc": f"0x{stored_crc(ds.raw):08X}",
        "crc_durum": "DOĞRU" if ds.crc_ok() else "HATALI",
        "imza": stored_signature(ds.raw).hex().upper(),
        "arşiv": ds.archive.name if ds.archive else "—",
        "arşiv_dosya": ds.archive_member or "—",
        "uyarılar": list(ds.warnings),
    }


def restore_stock(ds: Dataset) -> bytes:
    """Kaynak dosyadaki baytları döndürür (değişiklikleri geri al)."""
    return ds.raw
