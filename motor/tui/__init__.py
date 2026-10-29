"""Full-screen alternate-screen (`?1049h`) `ncurses`-style TUI engine for Schutz-Kaput."""

from __future__ import annotations

from .app import KsPatcherTuiApp
from .screen import TuiScreen

__all__ = ["KsPatcherTuiApp", "TuiScreen"]
