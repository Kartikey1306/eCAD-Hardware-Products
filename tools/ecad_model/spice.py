"""A strict reader and writer for the SPICE netlists of the electrical domain.

The netlist is the electrical domain's source of truth, and ngspice never runs
it: the domain writes a deck from the engineering model and runs that. This
module is the format layer between the two. It reads a netlist into elements
with SI values, writes a deck's element lines back from SI values, and reads a
deck back so V2 can compare it with its model. It knows no roles and no
network class; those belong to ecad_model.domains.electrical.

The grammar is an allow-list, not a SPICE parser: R and C elements,
piecewise-linear V and I sources, voltage-controlled switches with one
`.model NAME SW(...)` card each, comments, and `.end`. Everything else is
refused by name, because ngspice reads much that looks inert as something
else. Each of these was observed on ngspice-47 (macOS arm64, 2026-09-27):

- `1M` is milli, not mega; `10uF`, `2kohm` and `1ms` are read by dropping the
  trailing letters; `F` is femto.
- `gnd` is ground, and `pa_00`, `pa_01`, ... are nodes that `par()` in a
  `.meas` creates, so a netlist node of that name is taken over.
- Inside a `.meas`, other names are ngspice's own (2026-09-28): `v(time)`
  reads the time axis, `v(all)` and `v(allv)` another vector, a node
  `temper` crashes ngspice (so does a model `TEMPER`), `limit`, `gauss`,
  `agauss`, `unif` and `aunif` inside `par()` stop it, and a model `GND` is
  not found. Node names therefore start with `n_` and model names with
  `SW_`: of 174 names probed, 12 misread as nodes and 2 as models, and none
  with those prefixes.
- Line 1 is always the title, so a card written there vanishes, and a file
  whose title starts with `*ng_script` is run as a script.
- A `+` line joins the line before it; ngspice reads on past `.end`, accepts a
  file without one, and accepts a node with a single terminal.
- `.control` blocks and `*#` comment lines run front-end commands, including
  `shell`, under `-b`.

Reading is one pass over at most MAX_NETLIST_BYTES, with anchored regular
expressions and no recursion, so its cost is linear in the input.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .importers.base import ExtractionError

VERSION = "1.0.0"

MAX_NETLIST_BYTES = 1 << 20
MAX_LINE_CHARS = 1024
MAX_ELEMENTS = 1000
# A source line written back with repr() of every value is at most
# 103 + 50 * points characters: a 32-character designator and two
# 32-character nodes, and at most 24 characters for each number and one
# separator. Up to 18 points it therefore fits MAX_LINE_CHARS, so a deck
# written from any netlist accepted here reads back.
MAX_PWL_POINTS = 16

_SUFFIXES = {"t": 12, "g": 9, "meg": 6, "k": 3, "m": -3, "u": -6, "n": -9, "p": -12}
_NUMBER = re.compile(r"([+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+))(?:[eE]([+-]?[0-9]+)|("
                     + "|".join(sorted(_SUFFIXES, key=len, reverse=True)) + "))?")
_DESIGNATOR = re.compile(r"[RCVIS][A-Z0-9_]{1,31}")
_MODEL_NAME = re.compile(r"SW_[A-Z0-9_]{1,29}")
_NODE = re.compile(r"0|n_[a-z0-9_]{1,30}")
_PAR_NODE = re.compile(r"pa_[0-9]+")
_NOT_TEXT = re.compile(rb"[^\t\n\x20-\x7e]")
_RESERVED = re.compile(r"[;$'\"{}`!\\]")
_PWL = re.compile(r"(?i:pwl)[ \t]*\((.*)\)")
_MODEL_CARD = re.compile(r"\.model[ \t]+(\S+)[ \t]+([A-Za-z]+)[ \t]*\(([^()]*)\)", re.IGNORECASE)

# The shapes of this grammar's element cards, case-insensitively and with any
# value spelling SPICE reads, so a card placed on the title line is refused
# rather than silently dropped.
_CARD_NODE = r"(?:0|[a-z][a-z0-9_]*)"
_CARD_VALUE = r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:e[+-]?[0-9]+)?[a-z]*"
_TITLE_CARD = re.compile(
    rf"[rc][a-z0-9_]+[ \t]+{_CARD_NODE}[ \t]+{_CARD_NODE}[ \t]+{_CARD_VALUE}"
    rf"|[vi][a-z0-9_]+[ \t]+{_CARD_NODE}[ \t]+{_CARD_NODE}[ \t]+"
    rf"(?:(?:dc[ \t]+)?{_CARD_VALUE}|(?:pwl|pulse|sin|exp|sffm|am)[ \t]*\(.*\))"
    rf"|s[a-z0-9_]+(?:[ \t]+{_CARD_NODE}){{4}}[ \t]+[a-z][a-z0-9_]*(?:[ \t]+(?:on|off))?",
    re.IGNORECASE)

# The deck's own section, exactly as ecad_model.domains.electrical writes it.
_TRAN = re.compile(r"\.tran ([^ ]+) ([^ ]+) ([^ ]+) ([^ ]+)")
_SIGNAL = r"(?:v\([a-z0-9_]+\)|par\('[-+*/().A-Za-z0-9_]+'\))"
_MEASUREMENT = re.compile(
    rf"\.meas tran ([a-z][a-z0-9_]{{0,63}}) (?:(?:MAX|INTEG) {_SIGNAL} FROM=([^ ]+) TO=([^ ]+)"
    rf"|FIND {_SIGNAL} AT=([^ ]+)|WHEN v\([a-z0-9_]+\)=([^ ]+) RISE=[1-9][0-9]{{0,5}})")
_SECTION_START = ".options noacct"

_ELEMENTS = {"R": "resistor", "C": "capacitor", "V": "voltage_source", "I": "current_source",
             "S": "voltage_controlled_switch"}
_LETTERS = {element: letter for letter, element in _ELEMENTS.items()}
_VALUE_FACETS = {"R": "resistance", "C": "capacitance", "V": "waveform_voltage", "I": "waveform_current"}
_SWITCH_KEYS = {"RON": "on_resistance", "ROFF": "off_resistance", "VT": "threshold_voltage",
                "VH": "hysteresis_voltage"}
_REFUSED_LETTERS = {
    "L": "an inductor: PLANNED",
    **dict.fromkeys("BEFGH", "a behavioural or controlled source, which evaluates expressions"),
    "X": "a subcircuit instance: subcircuits are PLANNED",
    **dict.fromkeys("AN", "a code model or OSDI device, which loads a library"),
    **dict.fromkeys("DQMJKTUOWYZP", "a device this domain does not model"),
}
_DIRECTIVES = {
    **dict.fromkeys((".include", ".inc", ".lib", ".endl"), "reads another file"),
    **dict.fromkeys((".control", ".endc"), "runs commands, including shell"),
    **dict.fromkeys((".param", ".func", ".csparam"), "expressions"),
    **dict.fromkeys((".subckt", ".ends"), "subcircuits: PLANNED"),
    **dict.fromkeys((".options", ".option", ".temp", ".ic", ".nodeset", ".global"), "changes simulator state"),
    **dict.fromkeys((".tran", ".ac", ".dc", ".op", ".noise", ".tf", ".sens", ".pz", ".four", ".meas",
                     ".measure", ".print", ".plot", ".save", ".probe"),
                    "the analysis and measurements are written by the adapter"),
}


class NetlistRefused(ExtractionError):
    """A netlist or deck is outside the grammar this module reads.

    Always of kind "rejected": the file was read and refused on its content.
    The message is "<path>:<line>: <reason>", or "<path>: <reason>" when the
    reason belongs to the whole file.

    Example:
        >>> error = NetlistRefused("x.cir:3: '1M' ...")
        >>> error.kind, isinstance(error, ValueError)
        ('rejected', True)
    """

    def __init__(self, message: str):
        super().__init__("rejected", message)


@dataclass(frozen=True)
class Element:
    """One element card, with its values in SI units.

    element is resistor, capacitor, voltage_source, current_source or
    voltage_controlled_switch. terminals maps p and n (and cp and cn for a
    switch) to node names, "0" being ground. values holds resistance,
    capacitance, waveform_time with waveform_voltage or waveform_current, or a
    switch's on_resistance, off_resistance, threshold_voltage and
    hysteresis_voltage, taken from its model. line is the 1-based line number.
    """

    designator: str
    element: str
    terminals: Dict[str, str]
    values: Dict[str, Any]
    model: Optional[str]
    line: int


@dataclass(frozen=True)
class Netlist:
    """A netlist's title, its elements in file order, and its switch models by name."""

    title: str
    elements: Tuple[Element, ...]
    models: Dict[str, Dict[str, float]]


@dataclass
class _Draft:
    title: str
    elements: List[Tuple[str, str, Dict[str, str], Dict[str, Any], Optional[str], int]]
    models: Dict[str, Dict[str, float]]
    model_lines: Dict[str, int]


def parse_value(token: str, where: str) -> float:
    """Read one SPICE number, refusing every spelling ngspice would misread.

    Only lower-case scale suffixes are read (t g meg k m u n p), because
    ngspice folds case and `1M` is then milli. An exponent and a suffix
    together, trailing unit letters, `f`, `mil` and a non-finite result are
    refused. The mantissa and exponent are converted once, as one decimal
    literal, so `470u` is exactly float("470e-6").

    Args:
        token: The number as written.
        where: "<path>:<line>", the location the refusal names.

    Returns:
        The value in SI units, with -0 read as 0.

    Raises:
        NetlistRefused: The token is not a number this grammar reads.

    Example:
        >>> [parse_value(token, "x.cir:4") for token in ("20m", "1g", "1meg", ".5", "5.", "2.5e-3")]
        [0.02, 1000000000.0, 1000000.0, 0.5, 5.0, 0.0025]
        >>> parse_value("30.001m", "x.cir:4") == float("30.001e-3")
        True
        >>> parse_value("1M", "x.cir:4")
        Traceback (most recent call last):
        ...
        ecad_model.spice.NetlistRefused: x.cir:4: '1M' is not a number this netlist grammar reads: ...
    """
    match = _NUMBER.fullmatch(token)
    if match is None:
        raise NetlistRefused(
            f"{where}: {token!r} is not a number this netlist grammar reads: digits with an optional "
            "exponent or one lower-case scale suffix (t g meg k m u n p), and no unit letters")
    mantissa, exponent, suffix = match.groups()
    if exponent is None:
        exponent = str(_SUFFIXES[suffix]) if suffix else "0"
    value = float(f"{mantissa}e{exponent}")
    if not math.isfinite(value):
        raise NetlistRefused(f"{where}: {token!r} is not a finite number")
    return value + 0.0  # -0.0 + 0.0 is 0.0; every other value is unchanged


def _refuse_unreadable(data: bytes, path: str) -> List[str]:
    if len(data) > MAX_NETLIST_BYTES:
        raise NetlistRefused(f"{path}: {len(data)} bytes exceeds the {MAX_NETLIST_BYTES}-byte netlist limit")
    if not data:
        raise NetlistRefused(f"{path}: is empty")
    if data.startswith(b"version https://git-lfs"):
        raise NetlistRefused(f"{path}: is a Git LFS pointer, not a netlist -- fetch it with git lfs pull")
    bad = _NOT_TEXT.search(data)
    if bad is not None:
        byte, line = data[bad.start()], data.count(b"\n", 0, bad.start()) + 1
        what = {0x0D: "a carriage return: lines end in LF only", 0x00: "a NUL byte"}.get(
            byte, "a byte outside printable ASCII, tab and LF")
        raise NetlistRefused(f"{path}:{line}: {what} (0x{byte:02x})")
    lines = data.decode("ascii").split("\n")
    if lines[-1] == "":
        lines.pop()
    for number, text in enumerate(lines, start=1):
        if len(text) > MAX_LINE_CHARS:
            raise NetlistRefused(
                f"{path}:{number}: {len(text)} characters exceeds the {MAX_LINE_CHARS}-character line limit")
    return lines


def _title_problem(title: str) -> Optional[str]:
    text = title.strip()
    if not text:
        return "line 1 is the title, and it is blank"
    if text[0] in ".+":
        return f"line 1 is the title, so SPICE never reads this {text.split()[0]!r} card"
    if text.lower().startswith("*ng_script"):
        return "line 1 is the title, and ngspice runs a file whose title starts with *ng_script as a script"
    if _TITLE_CARD.fullmatch(text):
        return "line 1 is the title, so SPICE never reads this element card"
    return None


def _node_problem(node: str) -> Optional[str]:
    if node == "gnd":
        return "'gnd' is ground to ngspice; write 0"
    if _PAR_NODE.fullmatch(node):
        return f"{node!r} is a name ngspice's par() gives its own nodes, and a netlist node of that name is taken over"
    if not _NODE.fullmatch(node):
        return (f"{node!r} is not a node name: 0, or n_ and 1 to 30 of a-z 0-9 _; ngspice reads names such as "
                "time, all or temper in a .meas as its own")
    return None


def _terminals(designator: str, names: Tuple[str, ...], nodes: List[str], where: str) -> Dict[str, str]:
    for node in nodes:
        problem = _node_problem(node)
        if problem is not None:
            raise NetlistRefused(f"{where}: {designator}: {problem}")
    if nodes[0] == nodes[1]:
        raise NetlistRefused(f"{where}: {designator}: both terminals are on node {nodes[0]}")
    return dict(zip(names, nodes))


def _pwl(designator: str, spec: str, where: str) -> Tuple[List[float], List[float]]:
    match = _PWL.fullmatch(spec)
    if match is None:
        word = re.match(r"[A-Za-z]+", spec)
        kind = word.group().upper() if word else "a bare (DC) value"
        raise NetlistRefused(f"{where}: {designator}: {kind} source: only PWL(t0 v0 t1 v1 ...) sources are read; "
                             "other source types are PLANNED")
    tokens = match.group(1).split()
    if len(tokens) > 2 * MAX_PWL_POINTS:
        raise NetlistRefused(f"{where}: {designator}: more than {MAX_PWL_POINTS} PWL points")
    if len(tokens) < 4 or len(tokens) % 2:
        raise NetlistRefused(f"{where}: {designator}: a PWL is time-value pairs, at least two of them; "
                             f"found {len(tokens)} numbers")
    numbers = [parse_value(token, where) for token in tokens]
    times, levels = numbers[0::2], numbers[1::2]
    if times[0] != 0.0:
        raise NetlistRefused(f"{where}: {designator}: a PWL starts at time 0, not {tokens[0]}")
    if any(later <= earlier for earlier, later in zip(times, times[1:])):
        raise NetlistRefused(f"{where}: {designator}: PWL times must strictly increase")
    return times, levels


def _element(text: str, where: str) -> Tuple[str, str, Dict[str, str], Dict[str, Any], Optional[str]]:
    tokens = text.split()
    designator, letter = tokens[0], text[0].upper()
    if letter in _REFUSED_LETTERS:
        raise NetlistRefused(f"{where}: {designator}: {_REFUSED_LETTERS[letter]}")
    if letter not in _ELEMENTS:
        raise NetlistRefused(f"{where}: {designator!r} is not an element, a comment or a directive")
    if not _DESIGNATOR.fullmatch(designator):
        raise NetlistRefused(f"{where}: {designator!r} is not a designator: {letter} and 1 to 31 of A-Z 0-9 _, "
                             "in upper case")
    if letter in "RC":
        if len(tokens) != 4:
            raise NetlistRefused(f"{where}: {designator}: a {_ELEMENTS[letter]} is {letter}<id> NODE NODE VALUE, exactly")
        terminals = _terminals(designator, ("p", "n"), tokens[1:3], where)
        return designator, letter, terminals, {_VALUE_FACETS[letter]: parse_value(tokens[3], where)}, None
    if letter in "VI":
        parts = text.split(None, 3)
        if len(parts) != 4:
            raise NetlistRefused(f"{where}: {designator}: a source is {letter}<id> NODE NODE PWL(...)")
        terminals = _terminals(designator, ("p", "n"), parts[1:3], where)
        times, levels = _pwl(designator, parts[3], where)
        return designator, letter, terminals, {"waveform_time": times, _VALUE_FACETS[letter]: levels}, None
    if len(tokens) != 6:
        raise NetlistRefused(f"{where}: {designator}: a switch is S<id> NODE NODE NODE NODE MODEL, exactly")
    if not _MODEL_NAME.fullmatch(tokens[5]):
        raise NetlistRefused(f"{where}: {designator}: {tokens[5]!r} is not a model name: SW_ and 1 to 29 of A-Z 0-9 _")
    return designator, letter, _terminals(designator, ("p", "n", "cp", "cn"), tokens[1:5], where), {}, tokens[5]


def _model(text: str, where: str, draft: _Draft) -> Tuple[str, Dict[str, float]]:
    match = _MODEL_CARD.fullmatch(text)
    if match is None:
        raise NetlistRefused(f"{where}: a .model card is .model NAME SW(RON=v ROFF=v VT=v VH=v)")
    name, kind, body = match.groups()
    if not _MODEL_NAME.fullmatch(name):
        raise NetlistRefused(f"{where}: {name!r} is not a model name: SW_ and 1 to 29 of A-Z 0-9 _")
    if name in draft.models:
        raise NetlistRefused(f"{where}: model {name} is already declared on line {draft.model_lines[name]}")
    if kind.upper() != "SW":
        raise NetlistRefused(f"{where}: model {name}: type {kind}: only SW (voltage-controlled switch) models are read")
    params: Dict[str, float] = {}
    for item in body.split():
        key, equals, value = item.partition("=")
        key = key.upper()
        if key not in _SWITCH_KEYS or not equals:
            raise NetlistRefused(f"{where}: model {name}: {item!r} is not one of RON= ROFF= VT= VH=")
        if key in params:
            raise NetlistRefused(f"{where}: model {name}: {key} is given twice")
        params[key] = parse_value(value, where)
    missing = [key for key in _SWITCH_KEYS if key not in params]
    if missing:
        raise NetlistRefused(f"{where}: model {name}: {' '.join(missing)} missing; "
                             "no SPICE default fills a value nobody chose")
    return name, params


def _circuit(lines: List[str], path: str) -> Tuple[_Draft, bool]:
    """Read the title and cards; say whether a .end was reached."""
    problem = _title_problem(lines[0])
    if problem is not None:
        raise NetlistRefused(f"{path}:1: {problem}")
    draft = _Draft(lines[0].strip(), [], {}, {})
    designators: Dict[str, int] = {}
    ended = False
    for number, raw in enumerate(lines[1:], start=2):
        where, text = f"{path}:{number}", raw.strip()
        if ended:
            if text:
                raise NetlistRefused(f"{where}: text after .end, which ngspice still reads")
            continue
        if not text:
            continue
        if text.startswith("*"):
            if text.startswith("*#"):
                raise NetlistRefused(f"{where}: a *# comment, which ngspice runs as a command, including shell")
            continue
        if text.startswith("+"):
            raise NetlistRefused(f"{where}: a '+' continuation, which joins this line to the one before it")
        if text.startswith("."):
            keyword = text.split()[0].lower()
            if keyword == ".end":
                if text.lower() != ".end":
                    raise NetlistRefused(f"{where}: nothing follows .end on its line")
                ended = True
                continue
            if keyword != ".model":
                raise NetlistRefused(f"{where}: {keyword}: {_DIRECTIVES.get(keyword, 'an unknown directive')}")
        reserved = _RESERVED.search(text)
        if reserved is not None:
            raise NetlistRefused(f"{where}: character {reserved.group()!r}: ngspice reads it as an inline "
                                 "comment, an expression, quoting or an escape, which this grammar does not")
        if text.startswith("."):
            name, params = _model(text, where, draft)
            draft.models[name], draft.model_lines[name] = params, number
            continue
        designator, letter, terminals, values, model = _element(text, where)
        if designator in designators:
            raise NetlistRefused(f"{where}: {designator} is already declared on line {designators[designator]}")
        if len(draft.elements) == MAX_ELEMENTS:
            raise NetlistRefused(f"{where}: more than {MAX_ELEMENTS} elements")
        designators[designator] = number
        draft.elements.append((designator, letter, terminals, values, model, number))
    return draft, ended


def _refuse_disconnected(elements: List[Element], path: str) -> None:
    first_line: Dict[str, int] = {}
    terminals_at: Dict[str, List[str]] = {}
    paths: Dict[str, List[str]] = {}
    for element in elements:
        for name, node in element.terminals.items():
            first_line.setdefault(node, element.line)
            terminals_at.setdefault(node, []).append(f"{element.designator}.{name}")
        # A capacitor, a current source and a switch's control pair carry no
        # DC current, so only these p-n pairs can fix a node's DC voltage.
        if element.element in ("resistor", "voltage_source", "voltage_controlled_switch"):
            p, n = element.terminals["p"], element.terminals["n"]
            paths.setdefault(p, []).append(n)
            paths.setdefault(n, []).append(p)
    if "0" not in first_line:
        raise NetlistRefused(f"{path}: no element connects to ground, node 0")
    for node, terminals in terminals_at.items():
        if node != "0" and len(terminals) < 2:
            raise NetlistRefused(f"{path}:{first_line[node]}: node {node} has one terminal ({terminals[0]}): "
                                 "nothing else connects to it")
    reached, pending = {"0"}, ["0"]
    while pending:
        for neighbour in paths.get(pending.pop(), []):
            if neighbour not in reached:
                reached.add(neighbour)
                pending.append(neighbour)
    unreached = [node for node in first_line if node not in reached]
    if unreached:
        raise NetlistRefused(f"{path}:{first_line[unreached[0]]}: node {unreached[0]} has no DC path to ground: "
                             "the operating point is singular")


def _finish(draft: _Draft, path: str) -> Netlist:
    users: Dict[str, str] = {}
    elements = []
    for designator, letter, terminals, values, model, line in draft.elements:
        if model is not None:
            if model not in draft.models:
                raise NetlistRefused(f"{path}:{line}: {designator} names model {model}, which no .model card declares")
            if model in users:
                raise NetlistRefused(f"{path}:{line}: {designator} names model {model}, which {users[model]} "
                                     "already uses; each switch has its own .model")
            users[model] = designator
            values = {_SWITCH_KEYS[key]: value for key, value in draft.models[model].items()}
        elements.append(Element(designator, _ELEMENTS[letter], terminals, values, model, line))
    for name, line in draft.model_lines.items():
        if name not in users:
            raise NetlistRefused(f"{path}:{line}: model {name} is used by no switch")
    _refuse_disconnected(elements, path)
    return Netlist(draft.title, tuple(elements), draft.models)


def parse_netlist(data: bytes, path: str) -> Netlist:
    r"""Read a netlist of this module's grammar, or refuse it with the line and the reason.

    Line 1 is the title. Then come element cards, `.model` cards, comments
    and blank lines, and `.end`; only blank lines may follow it. Every node
    other than 0 needs two terminals and a DC path to ground through
    resistors, voltage sources or switches.

    Args:
        data: The netlist's bytes: printable ASCII, tab and LF only.
        path: The name the refusal messages give the file.

    Returns:
        The title, the elements in file order with SI values, and the models.

    Raises:
        NetlistRefused: The file is outside the grammar; the message names
            the line and why.

    Example:
        >>> netlist = parse_netlist(b"rc charge\nV1 n_in 0 PWL(0 0 1u 5)\nR1 n_in n_out 1k\nC1 n_out 0 1u\n.end\n", "rc.cir")
        >>> netlist.title
        'rc charge'
        >>> [(e.designator, e.element, e.terminals, e.values) for e in netlist.elements][1]
        ('R1', 'resistor', {'p': 'n_in', 'n': 'n_out'}, {'resistance': 1000.0})
        >>> netlist.elements[0].values
        {'waveform_time': [0.0, 1e-06], 'waveform_voltage': [0.0, 5.0]}
        >>> parse_netlist(b"rc charge\nV1 n_in 0 PWL(0 0 1u 5)\nR1 n_in n_out 1k\nC1 n_out 0 1u\n", "rc.cir")
        Traceback (most recent call last):
        ...
        ecad_model.spice.NetlistRefused: rc.cir: no .end line; ngspice accepts a netlist without one
        >>> parse_netlist(b"rc charge\nV1 n_in 0 PWL(0 0 1u 5)\nR1 n_in time 1k\nC1 time 0 1u\n.end\n", "rc.cir")
        Traceback (most recent call last):
        ...
        ecad_model.spice.NetlistRefused: rc.cir:3: R1: 'time' is not a node name: 0, or n_ and 1 to 30 of a-z 0-9 _; ...
    """
    lines = _refuse_unreadable(data, path)
    draft, ended = _circuit(lines, path)
    if not ended:
        raise NetlistRefused(f"{path}: no .end line; ngspice accepts a netlist without one")
    return _finish(draft, path)


def _number(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{value!r} is not a finite number")
    return repr(float(value))


def _values(element: Element, facet: str) -> Any:
    if facet not in element.values:
        raise ValueError(f"{element.designator}: has no {facet}")
    return element.values[facet]


def write_elements(netlist: Netlist) -> List[str]:
    r"""Write the element and `.model` lines of a deck from SI values.

    Every number is written with repr(), which reads back as the same float,
    so the lines carry exactly the model's values. Each switch's `.model` card
    is written from its own values, after all elements, in element order;
    netlist.models is not read. The title is the caller's to write.

    Args:
        netlist: Its elements are written; one built from an engineering
            model needs no title or models of its own.

    Returns:
        The lines, without line ends.

    Raises:
        ValueError: A designator, node or model name this module's reader
            would refuse, a missing terminal or value, or a value that is not
            a finite number.

    Example:
        >>> netlist = parse_netlist(b"rc charge\nV1 n_in 0 PWL(0 0 1u 5)\nR1 n_in n_out 1k\nC1 n_out 0 1u\n.end\n", "rc.cir")
        >>> write_elements(netlist)
        ['V1 n_in 0 PWL(0.0 0.0 1e-06 5.0)', 'R1 n_in n_out 1000.0', 'C1 n_out 0 1e-06']
    """
    lines: List[str] = []
    models: List[str] = []
    for element in netlist.elements:
        letter = _LETTERS.get(element.element)
        if letter is None or not _DESIGNATOR.fullmatch(element.designator) or element.designator[0] != letter:
            raise ValueError(f"{element.designator!r} as a {element.element}: not an element this module writes")
        names = ("p", "n", "cp", "cn") if letter == "S" else ("p", "n")
        if set(element.terminals) != set(names):
            raise ValueError(f"{element.designator}: terminals {sorted(element.terminals)}, expected {list(names)}")
        for name in names:
            problem = _node_problem(element.terminals[name])
            if problem is not None:
                raise ValueError(f"{element.designator}: {problem}")
        card = " ".join([element.designator] + [element.terminals[name] for name in names])
        if letter in "RC":
            lines.append(f"{card} {_number(_values(element, _VALUE_FACETS[letter]))}")
        elif letter in "VI":
            times, levels = _values(element, "waveform_time"), _values(element, _VALUE_FACETS[letter])
            if len(times) != len(levels):
                raise ValueError(f"{element.designator}: {len(times)} PWL times but {len(levels)} values")
            points = " ".join(f"{_number(time)} {_number(level)}" for time, level in zip(times, levels))
            lines.append(f"{card} PWL({points})")
        else:
            if element.model is None or not _MODEL_NAME.fullmatch(element.model):
                raise ValueError(f"{element.designator}: {element.model!r} is not a model name")
            lines.append(f"{card} {element.model}")
            models.append(f".model {element.model} SW("
                          + " ".join(f"{key}={_number(_values(element, facet))}" for key, facet in _SWITCH_KEYS.items())
                          + ")")
    return lines + models


def _deck_section(lines: List[str], start: int, path: str) -> List[str]:
    last = len(lines) - 1
    if lines[last] != ".end":
        raise NetlistRefused(f"{path}:{last + 1}: a deck ends with its .end line, and nothing follows it")
    if last - start < 3:
        raise NetlistRefused(f"{path}:{last + 1}: the deck's section is {_SECTION_START}, one .tran, "
                             "at least one .meas, and .end")
    names: Dict[str, int] = {}
    for index in range(start + 1, last):
        text, where = lines[index], f"{path}:{index + 1}"
        if index == start + 1:
            tran = _TRAN.fullmatch(text)
            if tran is None:
                raise NetlistRefused(f"{where}: the line after {_SECTION_START} is the adapter's "
                                     ".tran TSTEP TSTOP TSTART TMAX")
            for token in tran.groups():
                parse_value(token, where)
            continue
        measurement = _MEASUREMENT.fullmatch(text)
        if measurement is None:
            if text.startswith(".tran"):
                raise NetlistRefused(f"{where}: a second .tran; the deck runs one analysis")
            if text == ".end":
                raise NetlistRefused(f"{where}: .end is the deck's last line, and ngspice reads past an earlier one")
            raise NetlistRefused(f"{where}: not a .meas line the adapter writes, so not part of its section")
        name = measurement.group(1)
        if name in names:
            raise NetlistRefused(f"{where}: measurement {name} is already declared on line {names[name]}, "
                                 "and ngspice would print both")
        names[name] = index + 1
        for token in measurement.groups()[1:]:
            if token is not None:
                parse_value(token, where)
    return lines[start:last]


def read_deck(data: bytes, path: str) -> Tuple[Netlist, List[str]]:
    r"""Read a deck the electrical domain wrote: its circuit, and its own analysis lines.

    The deck is split at its `.options noacct` line. The circuit before it is
    read with parse_netlist()'s grammar, except that `.end` comes last in the
    deck. After it only the adapter's own lines may follow, in this order:
    `.options noacct`, one `.tran TSTEP TSTOP TSTART TMAX`, `.meas tran` lines
    of the forms the adapter writes (MAX or INTEG with FROM= TO=, FIND with
    AT=, WHEN with RISE=), each name once, and `.end` as the last line.
    Whether those lines are the ones the model calls for is the caller's
    comparison.

    Args:
        data: The deck's bytes.
        path: The name the refusal messages give the file.

    Returns:
        The circuit, and the adapter's lines from `.options noacct` up to but
        not including `.end`.

    Raises:
        NetlistRefused: The circuit is outside the netlist grammar, or the
            adapter's section holds anything else.

    Example:
        >>> netlist = parse_netlist(b"rc charge\nV1 n_in 0 PWL(0 0 1u 5)\nR1 n_in n_out 1k\nC1 n_out 0 1u\n.end\n", "rc.cir")
        >>> own = [".options noacct", ".tran 1e-07 1e-05 0.0 1e-07", ".meas tran v_out FIND v(n_out) AT=1e-05"]
        >>> deck = "\n".join(["* rc charge", *write_elements(netlist), *own, ".end", ""]).encode("ascii")
        >>> circuit, section = read_deck(deck, "rc.deck.cir")
        >>> [e.values for e in circuit.elements] == [e.values for e in netlist.elements], section == own
        (True, True)
        >>> read_deck(deck.replace(b".end", b".control\n.end"), "rc.deck.cir")
        Traceback (most recent call last):
        ...
        ecad_model.spice.NetlistRefused: rc.deck.cir:8: not a .meas line the adapter writes, so not part of its section
    """
    lines = _refuse_unreadable(data, path)
    if _SECTION_START not in lines:
        raise NetlistRefused(f"{path}: no {_SECTION_START!r} line, where the adapter's section begins")
    start = lines.index(_SECTION_START)
    if start == 0:
        raise NetlistRefused(f"{path}:1: line 1 is the title, so SPICE never reads this '.options' card")
    draft, ended = _circuit(lines[:start], path)
    if ended:
        raise NetlistRefused(f"{path}: .end comes before the adapter's section, and ngspice reads past it")
    return _finish(draft, path), _deck_section(lines, start, path)
