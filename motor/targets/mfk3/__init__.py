"""Valeo MFK3 Front Camera (`2Q0 980 653 xx`, UDS `0x00A5`, Renesas RH850/P1H-C) target module."""

from __future__ import annotations

from .plugin import Mfk3Target

TARGET = Mfk3Target()

__all__ = ["Mfk3Target", "TARGET"]
