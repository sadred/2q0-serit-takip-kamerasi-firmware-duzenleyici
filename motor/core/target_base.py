"""Architecture-agnostic ECU Target Plugin interface for KSchutz & FeC/SWaP Patcher."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from .i18n import Style
from .pattern import SiteMatch


@dataclass
class PatchOptions:
    """Common & target-configurable patching options."""

    restore_stock: bool = False
    activate_all_fecs: bool = True
    suppress_key_dtcs: bool = False
    enable_xcp_can0: bool = False
    output_bin: Path | None = None
    in_place: bool = False
    build_odx_dir: Path | None = None
    template_odx: Path | None = None
    odx_method: str = "00"
    odx_layout: str = "extern"
    include_part2: bool = True
    frf_key_path: Path | None = None
    ignore_input_crc: bool = False


@dataclass
class TargetInspection:
    """Structured inspection result returned by an ECU target plugin (any CPU / datablock format)."""

    target_id: str
    arch_name: str
    source_path: Path
    format_kind: str
    format_label: str
    slice_name: str
    slice_start: int
    slice_end: int
    unpadded_size: int
    crc32_trimmed: int
    crc32_full: int
    sha256_trimmed: str
    ks_state: str               # "stock", "patched", "partial", "unknown"
    fec_state: str              # "stock", "patched", "partial", "n/a", "unknown"
    key_dtc_state: str          # "stock", "patched", "partial", "n/a", "unknown"
    xcp_state: str = "n/a"      # "stock", "patched", "partial", "n/a", "unknown"
    known_label: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    sites: list[SiteMatch] = field(default_factory=list)
    supported_fecs: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class TargetPatchResult:
    """Outcome of applying a patch or `--restore-stock` via an ECU target plugin."""

    before: TargetInspection
    after: TargetInspection
    actions: list[str]
    written_bin: Path | None = None
    written_odx_files: list[Path] = field(default_factory=list)
    flashing_notes: list[str] = field(default_factory=list)


class EcuTargetPlugin(ABC):
    """Base interface implemented by every dedicated ECU folder in `targets/<module>/`."""

    target_id: str = ""
    ecu_address: str = ""
    arch_name: str = ""         # e.g. "Renesas RH850/P1H-C", "Infineon TriCore", "ARM", "Dataset/EEPROM"
    aliases: tuple[str, ...] = ()
    expected_dump_sizes: tuple[int, ...] = ()
    allowed_extensions: tuple[str, ...] = (".bin", ".odx-f", ".odx", ".pdx", ".frf", ".xml")

    @property
    def supports_fec_unlock(self) -> bool:
        return False

    @property
    def supports_key_dtc_suppress(self) -> bool:
        return False

    @property
    def supports_xcp_unlock(self) -> bool:
        return False

    @property
    def supports_odx_build(self) -> bool:
        return False

    @property
    def supports_container_unpack(self) -> bool:
        return False

    @abstractmethod
    def title(self) -> str:
        """Short localized display name of the ECU target."""

    @abstractmethod
    def subtitle(self) -> str:
        """Hardware / MCU / part-number summary line."""

    @abstractmethod
    def description_lines(self, st: Style) -> list[str]:
        """Multi-line architectural & retrofit summary shown in TUI ECU selector."""

    @abstractmethod
    def input_hint(self) -> str:
        """Localized description of accepted dump/datablock/container files for prompts."""

    @abstractmethod
    def discover_candidates(self, search_roots: list[Path]) -> list[Path]:
        """Auto-discover candidate dumps/datablocks/containers near current working directories."""

    @abstractmethod
    def inspect_file(
        self,
        path: Path,
        *,
        frf_key_path: Path | None = None,
        ignore_input_crc: bool = False,
    ) -> TargetInspection:
        """Inspect an input dump, datablock, or container without modifying it."""

    @abstractmethod
    def render_inspection_lines(
        self,
        insp: TargetInspection,
        st: Style,
        *,
        verbose: bool = False,
    ) -> list[str]:
        """Format `TargetInspection` into ANSI-styled report lines (simple by default, detailed if `verbose`)."""

    @abstractmethod
    def patch_file(self, input_path: Path, opts: PatchOptions) -> TargetPatchResult:
        """Apply KS / FeC patch (or lossless `--restore-stock`) and write requested outputs."""

    @abstractmethod
    def render_patch_result_lines(
        self,
        res: TargetPatchResult,
        st: Style,
        *,
        verbose: bool = False,
    ) -> list[str]:
        """Format `TargetPatchResult` into ANSI-styled report lines (simple by default, detailed if `verbose`)."""

    def unpack_container(
        self,
        input_path: Path,
        output_dir: Path,
        *,
        skip_large_blocks: bool = False,
        frf_key_path: Path | None = None,
        ignore_input_crc: bool = False,
    ) -> list[tuple[str, int, int, int, int, Path]]:
        """Optional container unpacker returning `(name, method, raw_sz, dec_sz, crc32, out_path)`."""
        raise NotImplementedError(f"Target {self.target_id!r} does not support container unpacking")

    @abstractmethod
    def selftest(self) -> list[str]:
        """Run deterministic self-tests for this target's signatures, guards & codecs."""
