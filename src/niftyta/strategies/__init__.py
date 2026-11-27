"""Strategies available in the strategy tester, found automatically from the modules in this folder."""
from __future__ import annotations

import importlib
import pkgutil

from .base import Line, Param, Strategy

__all__ = ["Line", "Param", "Strategy", "all_strategies"]


def all_strategies() -> dict[str, Strategy]:
    found = []
    for m in pkgutil.iter_modules(__path__):
        s = getattr(importlib.import_module(f"{__name__}.{m.name}"), "STRATEGY", None)
        if s is not None:
            found.append(s)
    return {s.key: s for s in sorted(found, key=lambda s: (s.order, s.name))}
