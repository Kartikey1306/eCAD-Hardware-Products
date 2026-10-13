"""Read and write the S-expressions KiCad stores its symbols, schematics and boards in.

A node is a Python list whose first item is its keyword (a ``Sym``); atoms are ``Sym``
(bare words), ``str`` (quoted strings), ``int`` or ``float``. ``dumps`` writes quoted
strings back with KiCad's escaping, so a file read and written again keeps its meaning.

>>> loads('(property "Reference" "U" (at 0 1.27 0))')
[Sym('property'), 'Reference', 'U', [Sym('at'), 0, 1.27, 0]]
"""

from __future__ import annotations

from typing import Any, Iterator, List, Optional


class Sym(str):
    """A bare word: a keyword or an unquoted value such as ``yes`` or ``input``."""

    def __repr__(self) -> str:
        return f"Sym({str.__repr__(self)})"


_OPEN, _CLOSE = object(), object()


def _tokens(text: str) -> Iterator[Any]:
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c in "()":
            yield _OPEN if c == "(" else _CLOSE
            i += 1
        elif c == '"':
            j, out = i + 1, []
            while text[j] != '"':
                if text[j] == "\\":
                    nxt = text[j + 1]
                    out.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(nxt, nxt))
                    j += 2
                else:
                    out.append(text[j])
                    j += 1
            yield "".join(out)
            i = j + 1
        else:
            j = i
            while j < n and text[j] not in ' \t\r\n()"':
                j += 1
            word = text[i:j]
            try:
                yield int(word) if word.lstrip("-").isdigit() else float(word)
            except ValueError:
                yield Sym(word)
            i = j


def loads(text: str) -> List[Any]:
    """Parse one S-expression (a whole KiCad file is one)."""
    stack: List[List[Any]] = [[]]
    for tok in _tokens(text):
        if tok is _OPEN:
            stack.append([])
        elif tok is _CLOSE:
            node = stack.pop()
            stack[-1].append(node)
        else:
            stack[-1].append(tok)
    return stack[0][0]


def _atom(value: Any) -> str:
    if isinstance(value, Sym):
        return str(value)
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        text = f"{value:.6f}".rstrip("0").rstrip(".")
        return "0" if text in ("-0", "") else text
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def dumps(node: Any, indent: int = 0) -> str:
    """Write a node the way KiCad does: leading atoms inline, then one item per line.

    Order is preserved, so an atom that follows a child list stays after it.
    """
    if not isinstance(node, list):
        return _atom(node)
    first_list = next((i for i, x in enumerate(node) if isinstance(x, list)), len(node))
    line = "(" + " ".join(_atom(x) for x in node[:first_list])
    rest = node[first_list:]
    if not rest:
        return line + ")"
    pad = "\t" * (indent + 1)
    inner = "\n".join(pad + dumps(k, indent + 1) for k in rest)
    return f"{line}\n{inner}\n{chr(9) * indent})"


def find(node: List[Any], key: str) -> Optional[List[Any]]:
    """The first child list whose keyword is ``key``."""
    for child in node:
        if isinstance(child, list) and child and child[0] == key:
            return child
    return None


def find_all(node: List[Any], key: str) -> List[List[Any]]:
    """Every child list whose keyword is ``key``."""
    return [c for c in node if isinstance(c, list) and c and c[0] == key]
