"""Load symbols from KiCad's own symbol libraries, ready to place in a schematic.

A schematic embeds a copy of every symbol it uses (``lib_symbols``), flattened: a symbol
that ``extends`` another is written with the parent's drawing and pins under its own name
and properties. ``Library.symbol`` returns that flattened copy, and ``pins`` lists each
pin's connection point and the direction a wire leaves it, in library coordinates (y up).
"""

from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .sexpr import Sym, find, find_all, loads


@dataclass(frozen=True)
class Pin:
    number: str
    name: str
    etype: str          # KiCad electrical type: power_in, passive, bidirectional, ...
    x: float            # connection point, library coordinates (y up)
    y: float
    outward: Tuple[int, int]  # unit vector a wire leaves the pin in, library coordinates
    unit: int
    hidden: bool


def _outward(angle: float) -> Tuple[int, int]:
    """A pin's ``at`` angle points from its connection point into the body; a wire leaves
    the opposite way."""
    rad = math.radians((angle + 180) % 360)
    return int(round(math.cos(rad))), int(round(math.sin(rad)))


class Library:
    """Every ``*.kicad_sym`` file in KiCad's symbol directory, and in any local directories
    given (searched first), loaded on first use."""

    def __init__(self, symbol_dir: Path, local_dirs: Tuple[Path, ...] = ()) -> None:
        self.dir = symbol_dir
        self.local_dirs = tuple(local_dirs)
        self._libs: Dict[str, Dict[str, List[Any]]] = {}

    def path(self, name: str) -> Optional[Path]:
        """The file of library ``name``, local directories first; None if there is none."""
        for d in (*self.local_dirs, self.dir):
            if (d / f"{name}.kicad_sym").is_file():
                return d / f"{name}.kicad_sym"
        return None

    def is_local(self, name: str) -> bool:
        path = self.path(name)
        return path is not None and path.parent != self.dir

    def _lib(self, name: str) -> Dict[str, List[Any]]:
        if name not in self._libs:
            path = self.path(name)
            if path is None:
                raise KeyError(f"no symbol library {name!r} in {self.dir} or {list(self.local_dirs)}")
            tree = loads(path.read_text(encoding="utf-8"))
            self._libs[name] = {str(s[1]): s for s in find_all(tree, "symbol")}
        return self._libs[name]

    def symbol(self, lib_id: str) -> List[Any]:
        """The flattened symbol ``lib_id`` (``Library:Name``), named as a schematic embeds it."""
        lib, _, name = lib_id.partition(":")
        symbols = self._lib(lib)
        if name not in symbols:
            raise KeyError(f"no symbol {name!r} in library {lib!r}")
        node = copy.deepcopy(symbols[name])
        parent_ref = find(node, "extends")
        if parent_ref is not None:
            parent = copy.deepcopy(self.symbol(f"{lib}:{parent_ref[1]}"))
            parent_name = str(parent[1]).split(":", 1)[1]
            props = {str(p[1]): p for p in find_all(node, "property")}
            merged: List[Any] = [Sym("symbol"), f"{lib}:{name}"]
            for child in parent[2:]:
                if isinstance(child, list) and child[0] == "property" and str(child[1]) in props:
                    merged.append(props.pop(str(child[1])))
                elif isinstance(child, list) and child[0] == "symbol":
                    sub = copy.deepcopy(child)
                    sub[1] = re.sub(rf"^{re.escape(parent_name)}_", f"{name}_", str(sub[1]))
                    merged.append(sub)
                else:
                    merged.append(child)
            merged[2:2] = list(props.values())
            return merged
        node[1] = f"{lib}:{name}"
        return node


def pins(symbol: List[Any]) -> List[Pin]:
    """Every pin of a flattened symbol, with the unit it belongs to (0: all units)."""
    out: List[Pin] = []
    for sub in find_all(symbol, "symbol"):
        m = re.search(r"_(\d+)_(\d+)$", str(sub[1]))
        unit = int(m.group(1)) if m else 0
        for pin in find_all(sub, "pin"):
            at = find(pin, "at")
            name = find(pin, "name")
            number = find(pin, "number")
            hidden = Sym("hide") in pin or any(isinstance(x, list) and x[:1] == ["hide"] and
                                               (len(x) == 1 or x[1] in ("yes", True)) for x in pin)
            out.append(Pin(str(number[1]), str(name[1]), str(pin[1]), float(at[1]), float(at[2]),
                           _outward(float(at[3]) if len(at) > 3 else 0.0), unit, hidden))
    return out


def property_value(symbol: List[Any], key: str) -> Optional[str]:
    for prop in find_all(symbol, "property"):
        if str(prop[1]) == key:
            return str(prop[2])
    return None
