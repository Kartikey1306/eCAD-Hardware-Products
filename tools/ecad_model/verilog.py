"""A strict reader for the Verilog sources of the digital domain.

The committed Verilog is the digital domain's source of truth, and Icarus
never compiles it directly: the domain writes one simulation file from the
engineering model (each leaf module's text verbatim, then a harness) and
compiles that. This module is the format layer. It reads a source into a
leaf module or a declarative top, resolves the top's instances against the
leaves, and reads a written harness back by form so V2 can compare it with
its model. It knows no roles and no network class; those belong to
ecad_model.domains.digital.

The grammar is an allow-list, not a Verilog parser. A file is one
`` `timescale 1ns / 1ps `` line, before which only comments may stand, and one
module of one of two forms:

- synchronous RTL: `module NAME [#(parameter P = <decimal>, ...)]
  (input [wire] ..., output reg ...);` with localparams, regs and
  `always @(posedge <input>)` blocks of begin, if, case and nonblocking
  assignments only; no instance, no wire, no continuous assignment;
- a declarative top: `module NAME;` with literal localparams, one reg or wire
  per declaration and no initial value, and instances whose parameters and
  ports are all given by name.

Everything else is refused by name, with the file and line, because much of
Verilog reaches outside the simulation. Each of these was observed on Icarus
Verilog 13.0 (macOS arm64, 2026-09-27): `` `include `` read a file outside the
sources and printed its identifiers; `$fopen` wrote a file; `$readmemh`
opened /etc/hosts; `defparam u.P = 7` and `u.secret = 1` changed another
module; `$stop` stops to read commands from stdin. Names starting `ecad_` and
the text `ECAD_METRIC` are reserved for the harness and its metric markers.

Reading is one pass over at most MAX_SOURCE_BYTES, with anchored regular
expressions and no recursion: statements and expressions are read with an
explicit stack bounded by MAX_DEPTH, so the cost is linear in the input and a
deep nesting is a refusal, never a RecursionError.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from .importers.base import ExtractionError

VERSION = "1.0.0"

MAX_SOURCE_BYTES = 1 << 20
MAX_LINE_CHARS = 1024
MAX_NAME_CHARS = 64
MAX_WIDTH = 64
MAX_DEPTH = 32
MAX_MODULES = 16
# Verilog guarantees an unsized decimal at least 32 bits and reads it as a
# signed integer (IEEE 1364-2005, 3.5.1); a larger one is implementation-defined.
MAX_DECIMAL = (1 << 31) - 1

TIMESCALE = "`timescale 1ns / 1ps"
RTL_KEYWORDS = frozenset(
    "module endmodule parameter localparam input output wire reg always posedge begin end if else case endcase default"
    .split())
TOP_KEYWORDS = frozenset("module endmodule localparam reg wire".split())
HARNESS_MODULE = "ecad_harness"
HARNESS_TASKS = frozenset({"$display", "$finish", "$realtime"})
HARNESS_KEYWORDS = TOP_KEYWORDS | frozenset(
    "always initial begin end repeat posedge negedge while if else integer realtime for".split())

# Every other reserved word of Verilog-2005 and SystemVerilog-2012, and the three more Icarus Verilog 13.0
# reserves under -g2012 (wone from -g2005 on; bool and wreal with its extended types), by why it is refused.
_KEYWORD_CLASSES = {
    "calls C code": "import export chandle bind",
    "outside the synchronous RTL subset (PLANNED)": (
        "assign initial negedge function endfunction task endtask generate endgenerate genvar for while repeat "
        "forever integer real time realtime event signed unsigned inout casex casez wait fork join disable "
        "automatic or edge macromodule scalared vectored"),
    "changes another scope or the simulator": (
        "defparam force release deassign specify endspecify specparam primitive endprimitive table endtable "
        "config endconfig library design cell instance liblist use incdir include ifnone showcancelled "
        "noshowcancelled pulsestyle_onevent pulsestyle_ondetect"),
    "SystemVerilog (PLANNED)": (
        "accept_on alias always_comb always_ff always_latch assert assume before bins binsof bit break byte "
        "checker class clocking const constraint context continue cover covergroup coverpoint cross dist do "
        "endchecker endclass endclocking endgroup endinterface endpackage endprogram endproperty endsequence "
        "enum eventually expect extends extern final first_match foreach forkjoin global iff ignore_bins "
        "illegal_bins implements implies inside int interconnect interface intersect join_any join_none let "
        "local logic longint matches modport nettype new nexttime null package packed priority program "
        "property protected pure rand randc randcase randsequence ref reject_on restrict return s_always "
        "s_eventually s_nexttime s_until s_until_with sequence shortint shortreal soft solve static string "
        "strong struct super sync_accept_on sync_reject_on tagged this throughout timeprecision timeunit type "
        "typedef union unique unique0 until until_with untyped var virtual void wait_order weak wildcard with "
        "within"),
    "gate-level primitive (PLANNED)": (
        "and nand nor xor xnor not buf bufif0 bufif1 notif0 notif1 cmos nmos pmos rcmos rnmos rpmos tran "
        "tranif0 tranif1 rtran rtranif0 rtranif1 pullup pulldown pull0 pull1 supply0 supply1 strong0 strong1 "
        "weak0 weak1 highz0 highz1 small medium large tri tri0 tri1 triand trior trireg wand wor uwire wone"),
    "an Icarus Verilog extended type (its -gxtypes, on by default)": "bool wreal",
}
_KEYWORDS = {word: reason for reason, words in _KEYWORD_CLASSES.items() for word in words.split()}

_DIRECTIVES = {
    "`include": "reads another file",
    **dict.fromkeys(("`define", "`undef", "`undefineall", "`__FILE__", "`__LINE__"), "text substitution"),
    **dict.fromkeys(("`ifdef", "`ifndef", "`elsif", "`else", "`endif"), "conditional compilation"),
    **dict.fromkeys(("`timescale", "`resetall", "`default_nettype", "`celldefine", "`endcelldefine", "`line",
                     "`pragma", "`unconnected_drive", "`nounconnected_drive", "`begin_keywords", "`end_keywords",
                     "`default_decay_time", "`default_trireg_strength", "`delay_mode_distributed",
                     "`delay_mode_path", "`delay_mode_unit", "`delay_mode_zero"), "compiler directive"),
}
_FILE_TASKS = frozenset(
    "fopen fclose fdisplay fdisplayb fdisplayh fdisplayo fwrite fwriteb fwriteh fwriteo fstrobe fstrobeb fstrobeh "
    "fstrobeo fmonitor fmonitorb fmonitorh fmonitoro fgetc ungetc fgets fscanf fread fseek ftell rewind fflush feof "
    "ferror".split())
_RUN_CONTROL = frozenset("finish stop fatal error warning info exit".split())

_TOKEN = re.compile(r"""
    (?P<space>[ \t\n]+)
  | (?P<comment>//[^\n]*)
  | (?P<block>/\*)
  | (?P<directive>`[A-Za-z_][A-Za-z0-9_]*|`)
  | (?P<string>")
  | (?P<system>\$[A-Za-z0-9_$]*)
  | (?P<based>[0-9]*'[A-Za-z0-9_?]*)
  | (?P<real>[0-9][0-9_]*(?:\.[0-9_]*)?[eE][+-]?[0-9_]*|[0-9][0-9_]*\.[0-9_]*)
  | (?P<number>[0-9][0-9_]*)
  | (?P<name>[A-Za-z_][A-Za-z0-9_$]*)
  | (?P<operator>===|!==|<<<|>>>|<<=|>>=|\*\*|->|::|\+\+|--|\+:|-:|[-+*/%&|^]=|\(\*
                 |<=|>=|==|!=|&&|\|\||<<|>>|[{}()\[\],;:.\#@=<>+\-*/%!~&|^?])
""", re.VERBOSE)
_REFUSED_OPERATORS = frozenset("=== !== <<< >>> <<= >>= ** -> :: ++ -- +: -: -= += *= /= %= &= |= ^= { }".split())
_HARNESS_OPERATORS = frozenset({"===", "!=="})
_SIZED = re.compile(r"([1-9][0-9]*)'(?:b([01][01_]*)|d([0-9][0-9_]*)|h([0-9a-fA-F][0-9a-fA-F_]*))")
_SIZED_UNKNOWN = re.compile(r"([1-9][0-9]*)'b([01xz][01xz_]*)")
_STRING = re.compile(r'"[^"\\\n]*"')
_METRIC_STRING = re.compile(r'"ECAD_METRIC ([a-z][a-z0-9_]*) %(?:0d|\.17g)"')
_CONTROL = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f]")
# Unicode's Bidi_Control characters reorder how text is displayed, so a comment could hide code from a reviewer.
_BIDI = re.compile("[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]")
_MARKER = "ECAD_METRIC"

_UNARY = frozenset("! ~ -".split())
_BINARY = frozenset("|| && | ^ & == != < <= > >= << >> + - * / %".split())
_CONSTANT_BINARY = frozenset("+ - * /".split())
_NOT_CONSTANT = (_BINARY - _CONSTANT_BINARY) | {"?"}
_CLOSING = {"(": ")", "[": "]", "?": ":"}

# The harness's value-bearing lines, as ecad_model.domains.digital writes them (read after strip()).
_NAME = r"[A-Za-z_][A-Za-z0-9_]*"
_CLOCK_LINE = re.compile(rf"always #([0-9]+) ({_NAME}) = ~\2;")
_RESET_LINE = re.compile(rf"repeat \(([0-9]+)\) @\(posedge ({_NAME})\);")
_BYTE_LINE = re.compile(rf"({_NAME}) <= 8'd([0-9]+);")
_EXPECTED_ARRAY = re.compile(r"reg +\[7:0\] ecad_expected \[0:([0-9]+)\];")
_EXPECTED_LINE = re.compile(r"ecad_expected\[([0-9]+)\] = 8'd([0-9]+);")
_COMPARED_LINE = re.compile(r"if \(ecad_received < ([0-9]+)\) begin")
_AWAITED_LINE = re.compile(r"if \(ecad_received < ([0-9]+)\) ecad_missing = \1 - ecad_received;")
_END_LINE = re.compile(r"if \(ecad_cycle == ([0-9]+)\) begin")

# A token: (kind, text, line, value). kind is timescale, keyword, name, number,
# sized (value (width, int or None)), real, string (value the metric name),
# system, op or eof.
_Token = Tuple[str, str, int, Any]


class HdlRefused(ExtractionError):
    """A Verilog source or harness is outside the grammar this module reads.

    Always of kind "rejected": the file was read and refused on its content.
    The message is "<path>:<line>: <reason>", or "<path>: <reason>" when the
    reason belongs to the whole file or design.

    Example:
        >>> error = HdlRefused("x.v:3: $fopen: opens, reads or writes files")
        >>> error.kind, isinstance(error, ValueError)
        ('rejected', True)
    """

    def __init__(self, message: str):
        super().__init__("rejected", message)


@dataclass(frozen=True)
class Port:
    """One port of a leaf's header: its direction (input or output), width in bits and line."""

    name: str
    direction: str
    width: int
    line: int


@dataclass(frozen=True)
class Leaf:
    """A synchronous RTL module: the file's text verbatim, its header and its literal localparams.

    parameters maps each header parameter to its decimal default.
    literal_localparams maps each localparam whose expression is one decimal
    literal to (value, line); other localparams are read, not evaluated.
    """

    name: str
    path: str
    text: str
    parameters: Dict[str, int]
    ports: Tuple[Port, ...]
    literal_localparams: Dict[str, Tuple[int, int]]


@dataclass(frozen=True)
class Instance:
    """One instance in a top: each override is a top localparam's name or a decimal; each port names a signal."""

    module: str
    name: str
    overrides: Dict[str, Union[int, str]]
    connections: Dict[str, str]
    line: int


@dataclass(frozen=True)
class Top:
    """A declarative top.

    localparams maps a name to (value, 8 for a [7:0] localparam else None,
    line); signals maps a name to (reg or wire, width, line); instances are in
    file order.
    """

    name: str
    path: str
    localparams: Dict[str, Tuple[int, Optional[int], int]]
    signals: Dict[str, Tuple[str, int, int]]
    instances: Tuple[Instance, ...]


@dataclass(frozen=True)
class Design:
    """One top and the leaves it instantiates, each exactly once, by module name in source order."""

    top: Top
    leaves: Dict[str, Leaf]


@dataclass(frozen=True)
class HarnessView:
    """What a written harness states, read back by form.

    signals, initial_values and instances come from the declarations before
    the first `always`: the top's grammar with a sized literal initialising a
    reg and decimal-literal overrides. The rest comes from the lines of the
    fixed forms that carry a value: `always #N clk = ~clk;` (clock and
    half_period, in the 1 ns time unit), `repeat (N) @(posedge clk);`
    (reset_cycles), each `NAME <= 8'dV;` (stimulus), the `ecad_expected`
    array's `[0:N-1]` (expected_size) and assignments (expected, in index
    order), `if (ecad_received < N) begin` (compared),
    `if (ecad_received < N) ecad_missing = N - ecad_received;` (awaited: the
    bytes a missing one is counted against) and `if (ecad_cycle == N) begin`
    (end_cycle). metrics are the names of the
    `$display("ECAD_METRIC <name> %0d"|"%.17g", ...)` declarations in order;
    system_identifiers are the distinct `$` names used, sorted.
    """

    signals: Dict[str, Tuple[str, int, int]]
    initial_values: Dict[str, int]
    instances: Tuple[Instance, ...]
    clock: str
    half_period: int
    reset_cycles: int
    stimulus: Tuple[Tuple[str, int], ...]
    expected: Tuple[int, ...]
    expected_size: int
    compared: int
    awaited: int
    end_cycle: int
    metrics: Tuple[str, ...]
    system_identifiers: Tuple[str, ...]


def _decode(data: bytes, path: str) -> Tuple[str, List[str]]:
    if len(data) > MAX_SOURCE_BYTES:
        raise HdlRefused(f"{path}: {len(data)} bytes exceeds the {MAX_SOURCE_BYTES}-byte source limit")
    if not data:
        raise HdlRefused(f"{path}: is empty")
    if data.startswith(b"version https://git-lfs"):
        raise HdlRefused(f"{path}: is a Git LFS pointer, not Verilog -- fetch it with git lfs pull")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        line = data.count(b"\n", 0, error.start) + 1
        raise HdlRefused(f"{path}:{line}: not UTF-8 (byte 0x{data[error.start]:02x})") from None
    for pattern, what in ((_CONTROL, "a control character"), (_BIDI, "a bidirectional control character")):
        bad = pattern.search(text)
        if bad is not None:
            char, line = bad.group(), text.count("\n", 0, bad.start()) + 1
            what = {"\r": "a carriage return: lines end in LF only", "\x00": "a NUL character"}.get(char, what)
            raise HdlRefused(f"{path}:{line}: {what} (U+{ord(char):04X})")
    if not text.endswith("\n"):
        raise HdlRefused(f"{path}:{text.count(chr(10)) + 1}: no final LF: the last line ends in LF")
    lines = text.split("\n")[:-1]
    for number, line_text in enumerate(lines, start=1):
        if len(line_text) > MAX_LINE_CHARS:
            raise HdlRefused(f"{path}:{number}: {len(line_text)} characters exceeds the {MAX_LINE_CHARS}-character "
                             "line limit")
    return text, lines


def _system_reason(name: str) -> str:
    bare = name[1:]
    if not bare:
        return "a $ outside a system task or function name: outside the lexical subset"
    if bare == "system":
        return "runs a shell command"
    if bare.endswith("plusargs"):
        return "reads the simulator's command line (plusargs)"
    if bare in _FILE_TASKS or bare.startswith(("readmem", "writemem", "sreadmem", "dump", "sdf_", "vcd")):
        return "opens, reads or writes files"
    if bare in ("random", "urandom", "urandom_range") or bare.startswith("dist_"):
        return "randomness"
    if bare.startswith(("display", "write", "strobe", "monitor")):
        return "prints, and only the harness prints"
    if bare in _RUN_CONTROL:
        return "run control, and only the harness ends a run ($stop waits for commands on stdin)"
    return "a system task or function outside the subset (PLANNED); a VPI module can define any $name"


def _based(value: str, where: str, harness: bool) -> Tuple[int, Optional[int]]:
    """A sized literal's (width, value); the value is None for a harness's x or z digits."""
    match = _SIZED.fullmatch(value)
    base, digits = 0, None
    if match is not None:
        base, digits = next((base, text) for base, text in zip((2, 10, 16), match.groups()[1:]) if text is not None)
    elif harness:
        match = _SIZED_UNKNOWN.fullmatch(value)
    if match is None:
        if value.startswith("'"):
            raise HdlRefused(f"{where}: {value}: an unsized based literal: outside the lexical subset")
        if re.search(r"[xXzZ?]", value.partition("'")[2][1:]):
            raise HdlRefused(f"{where}: {value}: x, z and ? digits are outside the lexical subset")
        raise HdlRefused(f"{where}: {value}: outside the lexical subset: a sized literal is W'b, W'd or W'h "
                         "with its digits, in lower case")
    width = int(match.group(1))
    if width > MAX_WIDTH:
        raise HdlRefused(f"{where}: {value}: wider than {MAX_WIDTH} bits")
    if digits is None:
        return width, None
    number = int(digits.replace("_", ""), base)
    if number >= 1 << width:
        raise HdlRefused(f"{where}: {value} does not fit in {width} bits")
    return width, number


def _word(value: str, where: str, harness: bool) -> str:
    """The kind of token a name is, keyword or name, refusing a name outside the lexical subset."""
    if "$" in value:
        raise HdlRefused(f"{where}: {value}: a $ inside an identifier: outside the lexical subset")
    if len(value) > MAX_NAME_CHARS:
        raise HdlRefused(f"{where}: {value[:24]}...: {len(value)} characters exceeds the {MAX_NAME_CHARS}-character "
                         "name limit")
    if _MARKER in value:
        raise HdlRefused(f"{where}: {value}: {_MARKER} is reserved for the harness's metric markers")
    if value in (HARNESS_KEYWORDS if harness else RTL_KEYWORDS):
        return "keyword"
    if value in _KEYWORDS:
        raise HdlRefused(f"{where}: {value}: {_KEYWORDS[value]}")
    if value in RTL_KEYWORDS:
        raise HdlRefused(f"{where}: {value}: not in the harness, which declares signals and instances, then measures")
    if value.startswith("ecad_") and not harness:
        raise HdlRefused(f"{where}: {value}: names starting ecad_ are reserved for the harness")
    return "name"


def _tokens(text: str, lines: List[str], path: str, harness: bool) -> List[_Token]:
    """Every token of a file, refusing on the way whatever is outside the lexical subset."""
    tokens: List[_Token] = []
    position, line, end = 0, 1, len(text)
    while position < end:
        match = _TOKEN.match(text, position)
        where = f"{path}:{line}"
        if match is None:
            char = text[position]
            if char == "\\":
                raise HdlRefused(f"{where}: an escaped identifier (\\): outside the lexical subset")
            if ord(char) > 0x7F:
                raise HdlRefused(f"{where}: non-ASCII outside a comment (U+{ord(char):04X})")
            raise HdlRefused(f"{where}: character {char!r} is outside the lexical subset")
        kind, value = match.lastgroup, match.group()
        if kind == "space":
            line += value.count("\n")
        elif kind == "comment":
            if _MARKER in value:
                raise HdlRefused(f"{where}: {_MARKER}: reserved for the harness's metric markers")
        elif kind == "block":
            close = text.find("*/", position + 2)
            if close < 0:
                raise HdlRefused(f"{where}: an unterminated /* comment")
            if _MARKER in text[position:close]:
                raise HdlRefused(f"{where}: {_MARKER}: reserved for the harness's metric markers")
            line += text.count("\n", position, close)
            position = close + 2
            continue
        elif kind == "directive":
            if value == "`timescale" and not tokens and lines[line - 1] == TIMESCALE:
                tokens.append(("timescale", TIMESCALE, line, None))
                position += len(lines[line - 1])
                continue
            if value == "`":
                raise HdlRefused(f"{where}: a backtick outside a directive: outside the lexical subset")
            reason = _DIRECTIVES.get(value, "text substitution (a macro use)")
            if value == "`timescale":
                reason += f": only one, {TIMESCALE} exactly, as the first line that is not a comment"
            raise HdlRefused(f"{where}: {value}: {reason}")
        elif kind == "string":
            if not harness:
                raise HdlRefused(f"{where}: a string: outside the lexical subset (file names and import "
                                 "\"DPI-C\" are strings)")
            string = _STRING.match(text, position)
            if string is None:
                raise HdlRefused(f"{where}: an unterminated string, or one with a backslash escape")
            metric = _METRIC_STRING.fullmatch(string.group())
            if metric is None:
                raise HdlRefused(f"{where}: {string.group()}: a string other than an {_MARKER} declaration")
            tokens.append(("string", string.group(), line, metric.group(1)))
            position = string.end()
            continue
        elif kind == "system":
            if not (harness and value in HARNESS_TASKS):
                suffix = "; the harness uses only $display, $finish and $realtime" if harness else ""
                raise HdlRefused(f"{where}: {value}: {_system_reason(value)}{suffix}")
            tokens.append(("system", value, line, None))
        elif kind == "based":
            tokens.append(("sized", value, line, _based(value, where, harness)))
        elif kind == "real":
            if not harness:
                raise HdlRefused(f"{where}: {value}: a real literal: outside the lexical subset")
            tokens.append(("real", value, line, None))
        elif kind == "number":
            number = int(value.replace("_", ""))
            if number > MAX_DECIMAL:
                raise HdlRefused(f"{where}: {value} does not fit a 32-bit signed integer, the only width Verilog "
                                 "guarantees an unsized decimal")
            tokens.append(("number", value, line, number))
        elif kind == "name":
            tokens.append((_word(value, where, harness), value, line, None))
        else:
            if value == "(*":
                raise HdlRefused(f"{where}: (*: an attribute: outside the lexical subset")
            if value in _REFUSED_OPERATORS and not (harness and value in _HARNESS_OPERATORS):
                raise HdlRefused(f"{where}: {value}: an operator outside the subset (PLANNED)")
            tokens.append(("op", value, line, None))
        position = match.end()
    tokens.append(("eof", "", len(lines), None))  # the file's last line: it ends in LF
    return tokens


def _shown(token: _Token) -> str:
    return "the end of the file" if token[0] == "eof" else repr(token[1])


class _Cursor:
    def __init__(self, tokens: List[_Token], path: str):
        self.tokens, self.index, self.path = tokens, 0, path

    def peek(self, ahead: int = 0) -> _Token:
        return self.tokens[min(self.index + ahead, len(self.tokens) - 1)]

    def take(self) -> _Token:
        token = self.peek()
        if token[0] != "eof":
            self.index += 1
        return token

    def at(self, text: str, ahead: int = 0) -> bool:
        token = self.peek(ahead)
        return token[1] == text and token[0] in ("keyword", "op")

    def refuse(self, token: _Token, reason: str) -> HdlRefused:
        return HdlRefused(f"{self.path}:{token[2]}: {reason}")

    def expect(self, text: str, context: str) -> _Token:
        token = self.take()
        if token[1] != text or token[0] not in ("keyword", "op"):
            raise self.refuse(token, f"expected {text!r} {context}, found {_shown(token)}")
        return token

    def name(self, context: str) -> _Token:
        token = self.take()
        if token[0] != "name":
            raise self.refuse(token, f"expected a name {context}, found {_shown(token)}")
        return token


def _declare(cursor: _Cursor, scope: Dict[str, Tuple[str, int]], kind: str, context: str) -> _Token:
    token = cursor.name(context)
    if token[1] in scope:
        raise cursor.refuse(token, f"{token[1]} is already declared on line {scope[token[1]][1]}")
    scope[token[1]] = (kind, token[2])
    return token


def _range(cursor: _Cursor) -> int:
    """The width of an optional [N:0] range: 1 without one."""
    if not cursor.at("["):
        return 1
    opening = cursor.take()
    msb = cursor.take()
    if msb[0] != "number" or not cursor.at(":") or cursor.peek(1)[0] != "number" or not cursor.at("]", 2):
        raise cursor.refuse(opening, "a range is [N:0] with decimal bounds")
    cursor.take()
    lsb = cursor.take()
    cursor.take()
    if lsb[3] != 0:
        raise cursor.refuse(opening, f"[{msb[1]}:{lsb[1]}]: a range is [N:0]; its least significant bit is 0")
    if msb[3] + 1 > MAX_WIDTH:
        raise cursor.refuse(opening, f"[{msb[1]}:0]: wider than {MAX_WIDTH} bits")
    return msb[3] + 1


def _use(cursor: _Cursor, scope: Dict[str, Tuple[str, int]], token: _Token) -> Tuple[str, int]:
    """The declaration of a name a leaf uses: never another module's, never an implicit net."""
    if cursor.at("."):
        raise cursor.refuse(token, f"{token[1]}.{cursor.peek(1)[1]}: a hierarchical reference, which reads or "
                                   "writes another module's registers")
    entry = scope.get(token[1])
    if entry is None:
        raise cursor.refuse(token, f"{token[1]} is not declared before this use: there are no implicit nets")
    return entry


def _expression(cursor: _Cursor, scope: Dict[str, Tuple[str, int]], constant: bool = False) -> None:
    """Read one expression up to the token that ends it, which is left for the caller."""
    stack: List[str] = []
    operand = True
    while True:
        token = cursor.peek()
        kind, text = token[0], token[1]
        is_op = kind == "op"
        if operand:
            if is_op and text in _UNARY:
                if constant:
                    raise cursor.refuse(token, f"{text}: outside a localparam's constant expression "
                                               "(+ - * / and parentheses)")
                cursor.take()
                # A unary operator's operand is a primary (IEEE 1364-2005 A.8.3), and Icarus refuses ~~y.
                following = cursor.peek()
                if following[0] == "op" and following[1] in _UNARY:
                    raise cursor.refuse(following, f"{following[1]} after {text}: a unary operator's operand is a name, "
                                                   "a number or a parenthesised expression, never another unary "
                                                   "operator")
            elif is_op and text == "(":
                if len(stack) == MAX_DEPTH:
                    raise cursor.refuse(token, f"an expression nested more than {MAX_DEPTH} deep")
                cursor.take()
                stack.append("(")
            elif kind == "name":
                cursor.take()
                declared = _use(cursor, scope, token)
                if constant and declared[0] not in ("parameter", "localparam"):
                    raise cursor.refuse(token, f"{text} is declared {declared[0]}: a localparam's expression uses "
                                               "parameters, earlier localparams and literals only")
                if cursor.at("["):
                    if constant:
                        raise cursor.refuse(token, f"{text}[: outside a localparam's constant expression")
                    if len(stack) == MAX_DEPTH:
                        raise cursor.refuse(token, f"an expression nested more than {MAX_DEPTH} deep")
                    cursor.take()
                    stack.append("[")
                else:
                    operand = False
            elif kind in ("number", "sized"):
                cursor.take()
                operand = False
            elif text == "#":
                raise cursor.refuse(token, "a delay (#): the RTL subset is untimed")
            else:
                raise cursor.refuse(token, f"expected an operand, found {_shown(token)}")
            continue
        if is_op and text in (_CONSTANT_BINARY if constant else _BINARY):
            cursor.take()
            operand = True
        elif is_op and text in _NOT_CONSTANT and constant:
            raise cursor.refuse(token, f"{text}: outside a localparam's constant expression (+ - * / and parentheses)")
        elif is_op and text == "?":
            if len(stack) == MAX_DEPTH:
                raise cursor.refuse(token, f"an expression nested more than {MAX_DEPTH} deep")
            cursor.take()
            stack.append("?")
            operand = True
        elif is_op and stack and text == _CLOSING[stack[-1]]:
            cursor.take()
            operand = stack.pop() == "?"
        elif not stack:
            return
        elif is_op and text == ":" and stack[-1] == "[":
            raise cursor.refuse(token, "a part select (name[a:b]): outside the subset")
        else:
            raise cursor.refuse(token, f"expected {_CLOSING[stack[-1]]!r}, found {_shown(token)}")


def _assignment(cursor: _Cursor, scope: Dict[str, Tuple[str, int]], target: _Token, block: int,
                assigned: Dict[str, Tuple[int, int]]) -> None:
    declared = _use(cursor, scope, target)
    if declared[0] not in ("reg", "output"):
        raise cursor.refuse(target, f"an assignment to {declared[0]} {target[1]}: only regs are assigned")
    if cursor.at("["):
        cursor.take()
        _expression(cursor, scope)
        cursor.expect("]", f"closing the index of {target[1]}")
    operator = cursor.take()
    if operator[1] not in ("<=", "=") or operator[0] != "op":
        raise cursor.refuse(operator, f"expected '<=' after {target[1]}, found {_shown(operator)}")
    if operator[1] == "=":
        raise cursor.refuse(operator, f"{target[1]} = ...: a blocking assignment; the subset assigns with <= only")
    _expression(cursor, scope)
    cursor.expect(";", "ending the assignment")
    first = assigned.setdefault(target[1], (block, target[2]))
    if first[0] != block:
        raise cursor.refuse(target, f"{target[1]} is assigned in two always blocks (lines {first[1]} and "
                                    f"{target[2]}); each reg has one")


def _case_item(cursor: _Cursor, scope: Dict[str, Tuple[str, int]]) -> bool:
    """Read the labels of a case item, or its endcase: say whether a statement follows."""
    if cursor.at("endcase"):
        cursor.take()
        return False
    if cursor.at("default"):
        cursor.take()
        if cursor.at(":"):
            cursor.take()
        return True
    while True:
        _expression(cursor, scope)
        if not cursor.at(","):
            break
        cursor.take()
    cursor.expect(":", "after a case item's labels")
    return True


def _not_a_statement(token: _Token) -> str:
    if token[1] == "#":
        return "a delay (#): the RTL subset is untimed"
    if token[1] == "@":
        return "an event control inside a statement: only an always block waits, on @(posedge <input>)"
    if token[1] == ";":
        return "an empty statement (;)"
    return f"expected a statement (begin, if, case or <reg> <= <expression>;), found {_shown(token)}"


def _statement(cursor: _Cursor, scope: Dict[str, Tuple[str, int]], block: int,
               assigned: Dict[str, Tuple[int, int]]) -> None:
    """Read one statement with an explicit stack of the compound statements still open."""
    stack: List[str] = []
    while True:
        token = cursor.take()
        word = token[1] if token[0] == "keyword" else ""
        if word in ("begin", "if", "case"):
            if stack and stack[-1] == "else":
                stack.pop()  # this statement is the whole else branch, so an else-if chain does not deepen
            if len(stack) == MAX_DEPTH:
                raise cursor.refuse(token, f"{word}: statements nested more than {MAX_DEPTH} deep")
            if word != "begin":
                cursor.expect("(", f"after {word}")
                _expression(cursor, scope)
                cursor.expect(")", f"closing the {word} expression")
            stack.append(word)
            if word == "if":
                continue
            if word == "begin":
                if not cursor.at("end"):
                    continue
                cursor.take()
            elif _case_item(cursor, scope):
                continue
            stack.pop()
        elif token[0] == "name":
            _assignment(cursor, scope, token, block, assigned)
        else:
            raise cursor.refuse(token, _not_a_statement(token))
        # A statement is complete: close every compound statement it completes.
        while stack:
            top = stack[-1]
            if top == "begin":
                if not cursor.at("end"):
                    break
                cursor.take()
                stack.pop()
            elif top == "if":
                if cursor.at("else"):
                    cursor.take()
                    stack[-1] = "else"
                    break
                stack.pop()
            elif top == "else":
                stack.pop()
            elif _case_item(cursor, scope):
                break
            else:
                stack.pop()
        if not stack:
            return


def _always(cursor: _Cursor, scope: Dict[str, Tuple[str, int]], block: int, assigned: Dict[str, Tuple[int, int]],
            clock: Optional[Tuple[str, int]]) -> Tuple[str, int]:
    start = cursor.take()
    if not cursor.at("@"):
        if cursor.at("#"):
            raise cursor.refuse(start, "always #: a delay; the RTL subset is untimed, and only the harness drives a "
                                       "clock")
        raise cursor.refuse(start, "an always block is clocked: always @(posedge <input>)")
    cursor.take()
    if not cursor.at("(") or not cursor.at("posedge", 1):
        raise cursor.refuse(start, f"always @{cursor.peek()[1]}...: an always block is clocked by "
                                   "@(posedge <input>) only")
    cursor.take()
    cursor.take()
    edge = cursor.name("after posedge")
    declared = _use(cursor, scope, edge)
    if declared[0] != "input":
        raise cursor.refuse(edge, f"always @(posedge {edge[1]}): {edge[1]} is declared {declared[0]}, not input")
    if clock is not None and clock[0] != edge[1]:
        raise cursor.refuse(edge, f"always @(posedge {edge[1]}): a second clock; {clock[0]} clocks the block on "
                                  f"line {clock[1]}")
    if not cursor.at(")"):
        raise cursor.refuse(cursor.peek(), f"one clock edge per always block: @(posedge {edge[1]})")
    cursor.take()
    _statement(cursor, scope, block, assigned)
    return clock or (edge[1], start[2])


def _port(cursor: _Cursor, scope: Dict[str, Tuple[str, int]]) -> Port:
    direction = cursor.take()
    if direction[0] != "keyword" or direction[1] not in ("input", "output"):
        if direction[1] == ")":
            raise cursor.refuse(direction, "a port list with no ports: a module with no ports is a top, written "
                                           "module NAME;")
        raise cursor.refuse(direction, f"expected input or output, found {_shown(direction)}: ports are declared "
                                       "in the header (ANSI style) only")
    if direction[1] == "input":
        if cursor.at("reg"):
            raise cursor.refuse(direction, "input reg: an input is a wire (input or input wire), never a reg")
        if cursor.at("wire"):
            cursor.take()
    else:
        if not cursor.at("reg"):
            raise cursor.refuse(direction, "an output is declared output reg: the subset assigns outputs in "
                                           "always blocks")
        cursor.take()
    width = _range(cursor)
    name = _declare(cursor, scope, direction[1], f"for the {direction[1]}")
    return Port(name[1], direction[1], width, name[2])


def _end_of_file(cursor: _Cursor, one: str) -> None:
    token = cursor.peek()
    if token[0] == "eof":
        return
    if token[0] == "keyword" and token[1] == "module":
        raise cursor.refuse(token, f"a second module: {one}")
    raise cursor.refuse(token, f"text after endmodule: {_shown(token)}")


def _header(cursor: _Cursor, name: _Token, scope: Dict[str, Tuple[str, int]]) -> Tuple[Dict[str, int], List[Port]]:
    """A leaf's #( ) parameters with their decimal defaults, and its ANSI port list."""
    parameters: Dict[str, int] = {}
    if cursor.at("#"):
        cursor.take()
        cursor.expect("(", "after #")
        while True:
            cursor.expect("parameter", "starting each header item: parameter NAME = <decimal>")
            parameter = _declare(cursor, scope, "parameter", "for the parameter")
            cursor.expect("=", f"after parameter {parameter[1]}")
            default = cursor.take()
            if default[0] != "number" or not (cursor.at(",") or cursor.at(")")):
                raise cursor.refuse(default, f"parameter {parameter[1]}: its default is one decimal literal")
            parameters[parameter[1]] = default[3]
            if not cursor.at(","):
                break
            cursor.take()
        cursor.expect(")", "closing the parameter header")
    cursor.expect("(", f"opening the port list of {name[1]}")
    ports = [_port(cursor, scope)]
    while cursor.at(","):
        cursor.take()
        ports.append(_port(cursor, scope))
    cursor.expect(")", "closing the port list")
    cursor.expect(";", "after the port list")
    return parameters, ports


def _leaf(cursor: _Cursor, name: _Token, path: str, text: str) -> Leaf:
    scope: Dict[str, Tuple[str, int]] = {}
    parameters, ports = _header(cursor, name, scope)
    literal_localparams: Dict[str, Tuple[int, int]] = {}
    assigned: Dict[str, Tuple[int, int]] = {}
    clock: Optional[Tuple[str, int]] = None
    block = 0
    while not cursor.at("endmodule"):
        token = cursor.peek()
        word = token[1] if token[0] == "keyword" else ""
        if word == "localparam":
            cursor.take()
            if cursor.at("["):
                raise cursor.refuse(token, "a leaf's localparam has no range: localparam NAME = <expression>;")
            local = cursor.name("for the localparam")
            if local[1] in scope:
                raise cursor.refuse(local, f"{local[1]} is already declared on line {scope[local[1]][1]}")
            cursor.expect("=", f"after localparam {local[1]}")
            start, first = cursor.index, cursor.peek()
            _expression(cursor, scope, constant=True)
            if first[0] == "number" and cursor.index == start + 1:
                literal_localparams[local[1]] = (first[3], local[2])
            cursor.expect(";", f"ending localparam {local[1]}")
            scope[local[1]] = ("localparam", local[2])
        elif word == "reg":
            cursor.take()
            _range(cursor)
            while True:
                _declare(cursor, scope, "reg", "for the reg")
                if cursor.at("=") or cursor.at("["):
                    raise cursor.refuse(cursor.peek(), "a reg is declared with no initial value and no array "
                                                       "dimension: it takes its values from reset")
                if not cursor.at(","):
                    break
                cursor.take()
            cursor.expect(";", "ending the reg declaration")
        elif word == "always":
            block += 1
            clock = _always(cursor, scope, block, assigned, clock)
        elif word == "parameter":
            raise cursor.refuse(token, "a parameter in the module body: parameters are declared in the #( ) header "
                                       "only")
        elif word == "wire":
            raise cursor.refuse(token, "a wire in a leaf: the subset declares regs, assigned in always blocks")
        elif word in ("input", "output"):
            raise cursor.refuse(token, f"{word} in the module body: ports are declared in the header")
        elif word == "module":
            raise cursor.refuse(token, "a second module: one module per file")
        elif token[0] == "name" and (cursor.peek(1)[0] == "name" or cursor.at("#", 1)):
            raise cursor.refuse(token, f"an instance of {token[1]}: a leaf instantiates no module; a top is written "
                                       "module NAME; with no ports")
        elif token[0] == "eof":
            raise cursor.refuse(token, f"module {name[1]} has no endmodule")
        else:
            raise cursor.refuse(token, f"{_shown(token)} where a localparam, reg or always item is expected")
    cursor.take()
    _end_of_file(cursor, "one module per file")
    for port in ports:
        if port.direction == "output" and port.name not in assigned:
            raise HdlRefused(f"{path}:{port.line}: output reg {port.name} is assigned by no statement")
    return Leaf(name[1], path, text, parameters, tuple(ports), literal_localparams)


def _instance(cursor: _Cursor, scope: Dict[str, Tuple[str, int]], harness: bool) -> Instance:
    module = cursor.take()
    if not cursor.at("#"):
        raise cursor.refuse(module, f"an instance of {module[1]} states its parameters: {module[1]} "
                                    "#(.NAME(value), ...) NAME (.port(signal), ...);")
    cursor.take()
    cursor.expect("(", "after #")
    overrides: Dict[str, Union[int, str]] = {}
    what = "decimal literal" if harness else "top localparam or decimal literal"
    while True:
        cursor.expect(".", "before each override: .NAME(value)")
        parameter = cursor.name("after . in the overrides")
        if parameter[1] in overrides:
            raise cursor.refuse(parameter, f"{parameter[1]} is overridden twice")
        cursor.expect("(", f"after .{parameter[1]}")
        value = cursor.take()
        if not (value[0] == "number" or (value[0] == "name" and not harness)) or not cursor.at(")"):
            raise cursor.refuse(value, f"the override of {parameter[1]} is one {what}, not an expression")
        cursor.take()
        overrides[parameter[1]] = value[3] if value[0] == "number" else value[1]
        if not cursor.at(","):
            break
        cursor.take()
    cursor.expect(")", "closing the overrides")
    name = _declare(cursor, scope, "instance", "for the instance")
    cursor.expect("(", f"opening the connections of {name[1]}")
    connections: Dict[str, str] = {}
    while True:
        dot = cursor.peek()
        if not cursor.at("."):
            raise cursor.refuse(dot, f"{name[1]}: {_shown(dot)}: connections are by name only, .port(signal)")
        cursor.take()
        if cursor.at("*"):
            raise cursor.refuse(dot, f"{name[1]}: .*: connections are by name only, .port(signal)")
        port = cursor.name("after . in the connections")
        if port[1] in connections:
            raise cursor.refuse(port, f"{name[1]}.{port[1]} is connected twice")
        cursor.expect("(", f"after .{port[1]}")
        signal = cursor.take()
        if signal[1] == ")":
            raise cursor.refuse(signal, f"{name[1]}.{port[1]}(): an unconnected port; every port is connected")
        if signal[0] != "name" or not cursor.at(")"):
            raise cursor.refuse(signal, f"{name[1]}.{port[1]}: a connection is one signal name, not an expression")
        cursor.take()
        connections[port[1]] = signal[1]
        if not cursor.at(","):
            break
        cursor.take()
    cursor.expect(")", f"closing the connections of {name[1]}")
    cursor.expect(";", f"ending the instance {name[1]}")
    return Instance(module[1], name[1], overrides, connections, module[2])


def _top_items(cursor: _Cursor, harness: bool) -> Tuple[Dict[str, Tuple[int, Optional[int], int]],
                                                         Dict[str, Tuple[str, int, int]], Dict[str, int],
                                                         List[Instance]]:
    """A top's declarations and instances, up to its endmodule (or, in a harness, its first always)."""
    scope: Dict[str, Tuple[str, int]] = {}
    localparams: Dict[str, Tuple[int, Optional[int], int]] = {}
    signals: Dict[str, Tuple[str, int, int]] = {}
    initial_values: Dict[str, int] = {}
    instances: List[Instance] = []
    while True:
        token = cursor.peek()
        word = token[1] if token[0] == "keyword" else ""
        if word == "endmodule" or (harness and word == "always"):
            return localparams, signals, initial_values, instances
        if word == "localparam":
            if harness:
                raise cursor.refuse(token, "a localparam in the harness: it writes every value as a literal")
            cursor.take()
            width = None
            if cursor.at("["):
                if _range(cursor) != 8:
                    raise cursor.refuse(token, "a top localparam's only range is [7:0]")
                width = 8
            local = _declare(cursor, scope, "localparam", "for the localparam")
            cursor.expect("=", f"after localparam {local[1]}")
            literal = cursor.take()
            if literal[0] not in ("number", "sized") or not cursor.at(";"):
                raise cursor.refuse(literal, f"localparam {local[1]}: a top localparam is one decimal or sized "
                                             "literal, not an expression")
            cursor.take()
            if width is not None and (literal[0] != "sized" or literal[3][0] != 8):
                raise cursor.refuse(literal, f"localparam [7:0] {local[1]}: its literal is 8 bits wide (8'h.., 8'd.. "
                                             "or 8'b..)")
            localparams[local[1]] = (literal[3][1] if literal[0] == "sized" else literal[3], width, local[2])
        elif word in ("reg", "wire"):
            cursor.take()
            width = _range(cursor)
            signal = _declare(cursor, scope, word, f"for the {word}")
            if cursor.at("="):
                if not harness or word == "wire":
                    raise cursor.refuse(signal, f"{word} {signal[1]} = ...: a top declaration has no initial value; "
                                                "the adapter drives every reg")
                cursor.take()
                literal = cursor.take()
                if literal[0] != "sized" or literal[3][1] is None:
                    raise cursor.refuse(literal, f"reg {signal[1]}: its initial value is a sized literal")
                initial_values[signal[1]] = literal[3][1]
            if cursor.at(","):
                raise cursor.refuse(signal, f"{word} {signal[1]}, ...: a top declares one signal per declaration")
            cursor.expect(";", f"ending the {word} declaration")
            signals[signal[1]] = (word, width, signal[2])
        elif token[0] == "name" and (cursor.peek(1)[0] == "name" or cursor.at("#", 1)):
            instances.append(_instance(cursor, scope, harness))
        elif token[0] == "eof":
            raise cursor.refuse(token, "the module has no endmodule")
        else:
            raise cursor.refuse(token, f"{_shown(token)} where a localparam, reg, wire or instance is expected")


def _top(cursor: _Cursor, name: _Token, path: str) -> Top:
    cursor.expect(";", f"after module {name[1]}")
    for token in cursor.tokens[cursor.index:]:
        if token[0] == "keyword" and token[1] not in TOP_KEYWORDS:
            raise cursor.refuse(token, f"{token[1]}: not in a declarative top, which states values and wiring only; "
                                       "the adapter writes the clock, the stimulus and the measurements")
    localparams, signals, _, instances = _top_items(cursor, harness=False)
    cursor.take()
    _end_of_file(cursor, "one module per file")
    return Top(name[1], path, localparams, signals, tuple(instances))


def _module_start(cursor: _Cursor) -> _Token:
    first = cursor.take()
    if first[0] != "timescale":
        raise cursor.refuse(first, f"no {TIMESCALE} before {_shown(first)}: it is the first line that is not a "
                                   "comment")
    cursor.expect("module", f"after {TIMESCALE}")
    return cursor.name("for the module")


def parse_source(data: bytes, path: str) -> Union[Leaf, Top]:
    r"""Read one Verilog source of this module's grammar, or refuse it with the line and the reason.

    The token after the module's name decides its form: "#" or "(" is
    synchronous RTL (a Leaf), ";" is a declarative top (a Top).

    Args:
        data: The file's bytes: UTF-8, LF line ends, non-ASCII only in comments.
        path: The name the refusal messages give the file; also the Leaf's or
            Top's path.

    Returns:
        A Leaf, with the text verbatim, or a Top.

    Raises:
        HdlRefused: The file is outside the grammar; the message names the
            line and why.

    Example:
        >>> source = (b"`timescale 1ns / 1ps\n"
        ...           b"module counter #(parameter STEP = 1) (input wire clk, output reg [3:0] count);\n"
        ...           b"    always @(posedge clk) count <= count + STEP;\n"
        ...           b"endmodule\n")
        >>> leaf = parse_source(source, "counter.v")
        >>> leaf.name, leaf.parameters, [(port.name, port.direction, port.width) for port in leaf.ports]
        ('counter', {'STEP': 1}, [('clk', 'input', 1), ('count', 'output', 4)])
        >>> parse_source(source.replace(b"count + STEP", b"$random"), "counter.v")
        Traceback (most recent call last):
        ...
        ecad_model.verilog.HdlRefused: counter.v:3: $random: randomness
        >>> parse_source(source.replace(b"<=", b"="), "counter.v")
        Traceback (most recent call last):
        ...
        ecad_model.verilog.HdlRefused: counter.v:3: count = ...: a blocking assignment; the subset assigns with <= only
    """
    text, lines = _decode(data, path)
    marker = text.find(_MARKER)
    if marker >= 0:
        raise HdlRefused(f"{path}:{text.count(chr(10), 0, marker) + 1}: {_MARKER}: reserved for the harness's "
                         "metric markers")
    cursor = _Cursor(_tokens(text, lines, path, harness=False), path)
    name = _module_start(cursor)
    if cursor.at(";"):
        return _top(cursor, name, path)
    if cursor.at("#") or cursor.at("("):
        return _leaf(cursor, name, path, text)
    raise cursor.refuse(cursor.peek(), f"module {name[1]}: expected ';' (a top) or '#(' or '(' (RTL), found "
                                       f"{_shown(cursor.peek())}")


def _connect(top: Top, leaf: Leaf, instance: Instance, drivers: Dict[str, List[str]],
             readers: List[Tuple[str, str, int]]) -> None:
    where = f"{top.path}:{instance.line}: {instance.name}"
    for parameter, value in instance.overrides.items():
        if parameter not in leaf.parameters:
            raise HdlRefused(f"{where}: {parameter} is not a parameter of {leaf.name}, whose header declares "
                             f"{', '.join(leaf.parameters) or 'none'}")
        if isinstance(value, str) and value not in top.localparams:
            raise HdlRefused(f"{where}: the override of {parameter}, {value}, is neither a top localparam nor a "
                             "decimal literal")
    ports = {port.name: port for port in leaf.ports}
    for name, signal in instance.connections.items():
        port = ports.get(name)
        if port is None:
            raise HdlRefused(f"{where}: {leaf.name} has no port {name}")
        declared = top.signals.get(signal)
        if declared is None:
            raise HdlRefused(f"{where}.{name}: {signal} is not a signal the top declares")
        kind, width, _ = declared
        if width != port.width:
            raise HdlRefused(f"{where}.{name} is {port.width} bits wide and {signal} is {width}")
        if port.direction == "output":
            if kind == "reg":
                raise HdlRefused(f"{where}.{name} is an output onto reg {signal}: an output drives a wire")
            drivers.setdefault(signal, []).append(f"{instance.name}.{name}")
        elif kind == "wire":
            readers.append((signal, f"{instance.name}.{name}", instance.line))
    for port in leaf.ports:
        if port.name not in instance.connections:
            raise HdlRefused(f"{where}: port {port.name} is not connected; every port is connected by name")


def elaborate(parsed: Sequence[Union[Leaf, Top]]) -> Design:
    r"""Resolve one top's instances against the leaves: every leaf once, every port once, every net driven once.

    Args:
        parsed: What parse_source() returned for each source, at most
            MAX_MODULES of them.

    Returns:
        The design: the top, and the leaves by module name in source order.

    Raises:
        HdlRefused: No top or two, a module defined twice or by no source, a
            leaf instantiated twice or never, an override of anything but a
            header parameter, or a connection that does not match: an unknown
            or unconnected port, a signal the top does not declare, a width
            mismatch, an output onto a reg, a wire with two drivers, or an
            input on a wire nothing drives.

    Example:
        >>> leaf = parse_source(b"`timescale 1ns / 1ps\nmodule inv #(parameter N = 1) (input wire a, output reg y);\n"
        ...                     b"    always @(posedge a) y <= !y;\nendmodule\n", "inv.v")
        >>> top = parse_source(b"`timescale 1ns / 1ps\nmodule tb;\n    reg a;\n    wire y;\n"
        ...                    b"    inv #(.N(2)) u (.a(a), .y(y));\nendmodule\n", "tb.v")
        >>> design = elaborate([top, leaf])
        >>> design.top.instances[0].connections, list(design.leaves)
        ({'a': 'a', 'y': 'y'}, ['inv'])
        >>> elaborate([leaf])
        Traceback (most recent call last):
        ...
        ecad_model.verilog.HdlRefused: inv.v: no top module: a top is written module NAME; with no ports
    """
    if not parsed:
        raise HdlRefused("no sources: a design is one top and the leaves it instantiates")
    if len(parsed) > MAX_MODULES:
        raise HdlRefused(f"{parsed[MAX_MODULES].path}: more than {MAX_MODULES} sources")
    defined: Dict[str, Union[Leaf, Top]] = {}
    for module in parsed:
        if module.name in defined:
            raise HdlRefused(f"{module.path}: module {module.name} is already defined in {defined[module.name].path}")
        defined[module.name] = module
    tops = [module for module in parsed if isinstance(module, Top)]
    if len(tops) != 1:
        if not tops:
            raise HdlRefused(f"{', '.join(module.path for module in parsed)}: no top module: a top is written "
                             "module NAME; with no ports")
        raise HdlRefused(f"{tops[1].path}: a second top module, {tops[1].name}; {tops[0].name} in {tops[0].path} "
                         "is the top")
    top = tops[0]
    leaves = {module.name: module for module in parsed if isinstance(module, Leaf)}
    instantiated: Dict[str, str] = {}
    drivers: Dict[str, List[str]] = {}
    readers: List[Tuple[str, str, int]] = []
    for instance in top.instances:
        where = f"{top.path}:{instance.line}: {instance.name}"
        leaf = leaves.get(instance.module)
        if leaf is None:
            if instance.module == top.name:
                raise HdlRefused(f"{where}: the top {top.name} instantiates itself")
            raise HdlRefused(f"{where}: no source defines module {instance.module}")
        if instance.module in instantiated:
            raise HdlRefused(f"{where}: module {instance.module} is already instantiated as "
                             f"{instantiated[instance.module]}; each leaf is instantiated once")
        instantiated[instance.module] = instance.name
        _connect(top, leaf, instance, drivers, readers)
    for leaf in leaves.values():
        if leaf.name not in instantiated:
            raise HdlRefused(f"{leaf.path}: module {leaf.name} is never instantiated by the top {top.name}")
    for wire, outputs in drivers.items():
        if len(outputs) > 1:
            raise HdlRefused(f"{top.path}:{top.signals[wire][2]}: wire {wire} is driven by {' and '.join(outputs)}")
    for wire, reader, line in readers:
        if wire not in drivers:
            raise HdlRefused(f"{top.path}:{line}: input {reader} is on wire {wire}, which no output drives")
    return Design(top, leaves)


def _harness_values(lines: List[str], first: int, last: int, path: str) -> Dict[str, Any]:
    """The values the harness's fixed line forms carry, from line first up to, not including, line last."""
    once: Dict[str, Tuple[int, Tuple[str, ...]]] = {}
    stimulus: List[Tuple[str, int]] = []
    expected: List[int] = []
    forms = (("clock", _CLOCK_LINE, "always #N clk = ~clk;"), ("reset", _RESET_LINE, "repeat (N) @(posedge clk);"),
             ("array", _EXPECTED_ARRAY, "reg [7:0] ecad_expected [0:N-1];"),
             ("compared", _COMPARED_LINE, "if (ecad_received < N) begin"),
             ("awaited", _AWAITED_LINE, "if (ecad_received < N) ecad_missing = N - ecad_received;"),
             ("end", _END_LINE, "if (ecad_cycle == N) begin"))
    shapes = {key: shape for key, _, shape in forms}
    for number in range(first, last):
        text = lines[number - 1].strip()
        byte = _BYTE_LINE.fullmatch(text)
        if byte is not None:
            stimulus.append((byte.group(1), int(byte.group(2))))
            continue
        entry = _EXPECTED_LINE.fullmatch(text)
        if entry is not None:
            if int(entry.group(1)) != len(expected):
                raise HdlRefused(f"{path}:{number}: ecad_expected[{entry.group(1)}]: the expected bytes are "
                                 f"assigned in index order, and the next is [{len(expected)}]")
            expected.append(int(entry.group(2)))
            continue
        for key, form, _ in forms:
            match = form.fullmatch(text)
            if match is not None:
                if key in once:
                    raise HdlRefused(f"{path}:{number}: a second line of the form {shapes[key]!r}; the first is "
                                     f"line {once[key][0]}")
                once[key] = (number, match.groups())
    for key, _, shape in forms:
        if key not in once:
            raise HdlRefused(f"{path}: no line of the form {shape!r}")
    clock, reset = once["clock"][1], once["reset"][1]
    if reset[1] != clock[1]:
        raise HdlRefused(f"{path}:{once['reset'][0]}: the reset waits on posedge {reset[1]}, not on the clock "
                         f"{clock[1]}")
    return {"clock": clock[1], "half_period": int(clock[0]), "reset_cycles": int(reset[0]),
            "stimulus": tuple(stimulus), "expected": tuple(expected),
            "expected_size": int(once["array"][1][0]) + 1, "compared": int(once["compared"][1][0]),
            "awaited": int(once["awaited"][1][0]),
            "end_cycle": int(once["end"][1][0])}


def read_harness(text: str, path: str) -> HarnessView:
    r"""Read a harness the digital domain wrote back by form, so V2 can compare it with its model.

    The harness is the simulation file's text after its leaves: comments, the
    `` `timescale 1ns / 1ps `` line, and one module, ecad_harness, with nothing
    after its endmodule. Its lexical rules are the sources', except that its
    names start ecad_ as it likes, its strings are ECAD_METRIC declarations in
    $display only, its system identifiers are $display, $finish and $realtime
    only, and it may use real literals, x digits in binary literals, === and
    !==. Whether the values are the ones the model calls for is the caller's
    comparison. Line numbers count from the first line of text.

    Args:
        text: The harness, from the line after the last leaf's text.
        path: The name the refusal messages give it.

    Returns:
        What it states, read by form (see HarnessView).

    Raises:
        HdlRefused: A lexical refusal, another module, text after endmodule,
            a value-bearing form missing or given twice, or expected bytes
            out of order.

    Example:
        >>> harness = "\n".join([
        ...     "`timescale 1ns / 1ps", "module ecad_harness;", "    reg clk = 1'b0;", "    reg [7:0] q = 8'd0;",
        ...     "    always #10 clk = ~clk;", "    initial begin", "        repeat (4) @(posedge clk);",
        ...     "        q <= 8'd53;", "    end", "    integer ecad_cycle = 0;", "    integer ecad_received = 0;",
        ...     "    reg  [7:0] ecad_expected [0:0];", "    initial begin", "        ecad_expected[0] = 8'd53;",
        ...     "    end", "    always @(negedge clk) begin", "        if (ecad_received < 1) begin", "        end",
        ...     "        if (ecad_cycle == 100) begin",
        ...     "            if (ecad_received < 1) ecad_missing = 1 - ecad_received;",
        ...     '            $display("ECAD_METRIC rx_bytes_received %0d", ecad_received);',
        ...     "            $finish;", "        end", "    end", "endmodule", ""])
        >>> view = read_harness(harness, "h.v")
        >>> view.half_period, view.reset_cycles, view.stimulus, view.expected, view.end_cycle, view.metrics
        (10, 4, (('q', 53),), (53,), 100, ('rx_bytes_received',))
        >>> read_harness(harness.replace("$finish", '$fopen("x")'), "h.v")
        Traceback (most recent call last):
        ...
        ecad_model.verilog.HdlRefused: h.v:22: $fopen: opens, reads or writes files; the harness uses only ...
    """
    try:
        data = text.encode("utf-8")
    except UnicodeEncodeError:
        raise HdlRefused(f"{path}: not UTF-8 text") from None
    text, lines = _decode(data, path)
    tokens = _tokens(text, lines, path, harness=True)
    cursor = _Cursor(tokens, path)
    name = _module_start(cursor)
    if name[1] != HARNESS_MODULE:
        raise cursor.refuse(name, f"the harness module is {HARNESS_MODULE}, not {name[1]}")
    cursor.expect(";", f"after module {HARNESS_MODULE}")
    _, signals, initial_values, instances = _top_items(cursor, harness=True)
    first = cursor.peek()[2]
    for index in range(cursor.index, len(tokens)):
        token = tokens[index]
        if token[0] == "keyword" and token[1] == "module":
            raise cursor.refuse(token, f"a second module: the harness is one module, {HARNESS_MODULE}")
        if token[0] == "keyword" and token[1] == "endmodule":
            break
        if token[0] == "string" and not (tokens[index - 1][1] == "(" and tokens[index - 2][1] == "$display"):
            raise cursor.refuse(token, f"{token[1]}: an {_MARKER} declaration stands in $display( ) only")
    else:
        raise cursor.refuse(tokens[-1], f"module {HARNESS_MODULE} has no endmodule")
    last = tokens[index][2]
    if lines[last - 1].strip() != "endmodule":
        raise cursor.refuse(tokens[index], "endmodule stands on a line of its own")
    cursor.index = index + 1
    _end_of_file(cursor, f"the harness is one module, {HARNESS_MODULE}")
    values = _harness_values(lines, first, last, path)
    metrics = tuple(token[3] for token in tokens if token[0] == "string")
    system = tuple(sorted({token[1] for token in tokens if token[0] == "system"}))
    return HarnessView(signals=signals, initial_values=initial_values, instances=tuple(instances),
                       metrics=metrics, system_identifiers=system, **values)
