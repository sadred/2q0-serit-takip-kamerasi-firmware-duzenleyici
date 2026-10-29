"""Architecture-agnostic masked binary signature scanner (supports byte/16-bit/32-bit instruction & data blocks)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PatchEdit:
    """Single contiguous byte replacement relative to the start of a matched `PatchSiteSpec`."""

    rel_offset: int
    stock_bytes: bytes
    patched_bytes: bytes


@dataclass(frozen=True)
class PatchSiteSpec:
    """Position-independent masked binary signature for any CPU ISA or raw datablock."""

    site_id: str
    group: str                  # e.g. "ks_core", "fec_unlock", "key_dtcs", or target-defined group
    symbol_name: str
    reference_va: int
    stock_pattern: str
    patched_pattern: str
    edits: tuple[PatchEdit, ...]
    ru_desc: str
    en_desc: str
    alignment: int = 1          # 1 = arbitrary byte/datablock/TriCore/x86, 2 = RH850/Thumb-2, 4 = PowerPC/ARM32/AArch64
    legacy_patched_patterns: tuple[str, ...] = ()


@dataclass
class SiteMatch:
    """Inspection result for a single `PatchSiteSpec`."""

    spec: PatchSiteSpec
    state: str                  # "stock", "patched", "missing", "ambiguous"
    slice_offset: int | None
    va: int | None
    details: dict[str, str] = field(default_factory=dict)


def parse_masked_pattern(spec: str) -> tuple[bytes, bytes]:
    """Parse hex pattern string with `??` wildcards into `(pattern_bytes, mask_bytes)`."""
    pat = bytearray()
    mask = bytearray()
    for tok in spec.split():
        if tok == "??":
            pat.append(0)
            mask.append(0)
        else:
            pat.append(int(tok, 16))
            mask.append(0xFF)
    return bytes(pat), bytes(mask)


def scan_masked(buf: bytes, spec: str, *, alignment: int = 1) -> list[int]:
    """Scan `buf` with configurable byte alignment using longest literal anchor acceleration.

    Works identically across CPU architectures and raw datablocks:
      - `alignment=1`: arbitrary data blocks, EEPROM/NvM records, TriCore mixed 16/32-bit, x86
      - `alignment=2`: Renesas RH850/V850, ARM Thumb-2, SuperH
      - `alignment=4`: PowerPC / VLE-32, ARM32 / AArch64, MIPS, RISC-V
    """
    if alignment < 1:
        raise ValueError(f"alignment must be >= 1, got {alignment}")
    pat, mask = parse_masked_pattern(spec)
    n = len(pat)
    if len(buf) < n:
        return []

    best_i = 0
    best_len = 0
    cur_i = 0
    cur_len = 0
    for i, m in enumerate(mask):
        if m == 0xFF:
            if cur_len == 0:
                cur_i = i
            cur_len += 1
            if cur_len > best_len:
                best_i, best_len = cur_i, cur_len
        else:
            cur_len = 0

    if best_len == 0:
        raise ValueError("Masked pattern must contain at least one non-wildcard byte")

    anchor = pat[best_i : best_i + best_len]
    hits: list[int] = []
    pos = 0
    limit = len(buf) - n
    while True:
        idx = buf.find(anchor, pos)
        if idx < 0:
            break
        cand = idx - best_i
        if 0 <= cand <= limit and (alignment == 1 or (cand % alignment) == 0):
            matched = True
            for j in range(n):
                if mask[j] and buf[cand + j] != pat[j]:
                    matched = False
                    break
            if matched:
                hits.append(cand)
        pos = idx + 1
    return hits


def scan_masked_aligned2(buf: bytes, spec: str) -> list[int]:
    """Convenience helper for 16-bit aligned ISAs (Renesas RH850/V850, ARM Thumb-2)."""
    return scan_masked(buf, spec, alignment=2)
