"""ECU Target Registry — discovers per-module folders inside `targets/<module>/`."""

from __future__ import annotations

import importlib
from pathlib import Path

from ..core.target_base import EcuTargetPlugin


_BUILTIN_MODULE_ORDER: tuple[str, ...] = (
    "mfk3",
)

_TARGETS_CACHE: list[EcuTargetPlugin] | None = None


def list_targets() -> list[EcuTargetPlugin]:
    """Return all registered `EcuTargetPlugin` instances (one subfolder per ECU module)."""
    global _TARGETS_CACHE
    if _TARGETS_CACHE is not None:
        return list(_TARGETS_CACHE)

    loaded: list[EcuTargetPlugin] = []
    seen_dirs: set[str] = set()
    pkg_dir = Path(__file__).resolve().parent

    # 1. Load built-in modules in canonical display order
    for mod_name in _BUILTIN_MODULE_ORDER:
        sub_init = pkg_dir / mod_name / "__init__.py"
        if sub_init.is_file():
            mod = importlib.import_module(f".{mod_name}", package=__name__)
            tgt = getattr(mod, "TARGET", None)
            if isinstance(tgt, EcuTargetPlugin):
                loaded.append(tgt)
                seen_dirs.add(mod_name)

    # 2. Auto-discover any additional `targets/<folder>/__init__.py` modules added later
    for child in sorted(pkg_dir.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir() or child.name.startswith(("_", ".")) or child.name in seen_dirs:
            continue
        if (child / "__init__.py").is_file():
            mod = importlib.import_module(f".{child.name}", package=__name__)
            tgt = getattr(mod, "TARGET", None)
            if isinstance(tgt, EcuTargetPlugin):
                loaded.append(tgt)
                seen_dirs.add(child.name)

    _TARGETS_CACHE = loaded
    return list(loaded)


def get_target(query: str) -> EcuTargetPlugin:
    """Resolve an `EcuTargetPlugin` by `target_id`, diagnostic address (`A5`/`0x00A5`), or alias."""
    q = query.strip().lower()
    if q.startswith("0x"):
        q_hex = q[2:].lstrip("0") or "0"
    else:
        q_hex = q.lstrip("0") or "0"

    for tgt in list_targets():
        if q == tgt.target_id.lower():
            return tgt
        addr_clean = tgt.ecu_address.lower().replace("0x", "").lstrip("0") or "0"
        if q_hex == addr_clean:
            return tgt
        if any(q == al.lower() for al in tgt.aliases):
            return tgt

    avail = ", ".join(f"{t.target_id} ({t.ecu_address})" for t in list_targets())
    raise ValueError(f"Unknown ECU target {query!r}. Available targets: {avail}")
