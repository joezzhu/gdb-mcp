"""GDB/MI output parser.

Parses GDB Machine Interface (MI) output lines into structured Python dictionaries.
Based on the GDB/MI protocol specification:
https://sourceware.org/gdb/onlinedocs/gdb/GDB_002fMI.html

Each parsed response is a dict with keys:
    - type: "result", "console", "log", "target", "notify", "output"
    - message: str or None (e.g., "done", "error", "stopped")
    - payload: str, dict, list, or None
    - token: int or None (command token for result/notify records)

This module is a self-contained reimplementation inspired by pygdbmi's gdbmiparser,
with no external dependencies beyond the Python standard library.
"""

import functools
import logging
import re
from typing import Any, Callable, Dict, Iterator, List, Match, Optional, Pattern, Tuple, Union

__all__ = [
    "parse_response",
    "response_is_finished",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GDB escape handling
# ---------------------------------------------------------------------------

# Map from single-character escape codes in GDB MI strings to unescaped values.
_NON_OCTAL_ESCAPES: Dict[str, str] = {
    "'": "'",
    "\\": "\\",
    "a": "\a",
    "b": "\b",
    "e": "\033",  # GDB-specific escape
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    '"': '"',
}

# Regex matching escapes and unescaped quotes in GDB MI strings.
_ESCAPES_RE = re.compile(
    r"""
    (?P<before>.*?)
    (
        (
            \\
            (
                (?P<escaped_octal>
                    [0-7]{3}
                    (
                        \\
                        [0-7]{3}
                    )*
                )
                |
                (?P<escaped_char>.)
            )
        )
        |
        (?P<unescaped_quote>")
    )
    """,
    flags=re.VERBOSE,
)


def _split_n_chars(s: str, n: int) -> Iterator[str]:
    """Iterate over string *s* in chunks of *n* characters."""
    for i in range(0, len(s), n):
        yield s[i : i + n]


def _unescape_internal(
    escaped_str: str,
    *,
    expect_closing_quote: bool,
    start: int = 0,
) -> Tuple[str, int]:
    """Unescape a GDB MI escaped string.

    MI-mode escapes are similar to standard C escapes but also include ``\\e``
    and use octal ``\\NNN`` sequences.

    Args:
        escaped_str: The raw string containing GDB escapes.
        expect_closing_quote: If True, processing stops at the first unescaped
            double-quote (the closing quote).  If False, no unescaped quote is
            expected.
        start: Position in *escaped_str* to begin processing.

    Returns:
        ``(unescaped_string, index_after_closing_quote)`` – the index is ``-1``
        when *expect_closing_quote* is False.
    """
    unmatched_start_index = start
    found_closing_quote = False
    unescaped_parts: list[str] = []

    for match in _ESCAPES_RE.finditer(escaped_str, pos=start):
        unescaped_parts.append(match["before"])
        escaped_octal = match["escaped_octal"]
        escaped_char = match["escaped_char"]
        unescaped_quote = match["unescaped_quote"]
        _, unmatched_start_index = match.span()

        if escaped_octal is not None:
            octal_bytes = bytearray()
            for octal_number in _split_n_chars(escaped_octal.replace("\\", ""), 3):
                try:
                    octal_bytes.append(int(octal_number, base=8))
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid octal number {octal_number!r} in {escaped_str!r}"
                    ) from exc
            try:
                replaced = octal_bytes.decode("utf-8")
            except UnicodeDecodeError:
                # Keep unchanged on decode failure (can happen on Windows – pygdbmi #64)
                replaced = f"\\{escaped_octal}"

        elif escaped_char is not None:
            try:
                replaced = _NON_OCTAL_ESCAPES[escaped_char]
            except KeyError as exc:
                raise ValueError(
                    f"Invalid escape character {escaped_char!r} in {escaped_str!r}"
                ) from exc

        elif unescaped_quote:
            if not expect_closing_quote:
                raise ValueError(f"Unescaped quote found in {escaped_str!r}")
            found_closing_quote = True
            break

        else:
            raise AssertionError(
                f"Unreachable code reached for string {escaped_str!r}"
            )

        unescaped_parts.append(replaced)

    if not found_closing_quote:
        if expect_closing_quote:
            raise ValueError(f"Missing closing quote in {escaped_str!r}")
        unescaped_parts.append(escaped_str[unmatched_start_index:])
        unmatched_start_index = -1

    return "".join(unescaped_parts), unmatched_start_index


def unescape(escaped_str: str) -> str:
    """Unescape a GDB MI string (without surrounding double-quotes)."""
    result, _ = _unescape_internal(escaped_str, expect_closing_quote=False)
    return result


# ---------------------------------------------------------------------------
# StringStream – lightweight character stream for recursive descent parsing
# ---------------------------------------------------------------------------


class StringStream:
    """A simple character stream backed by a Python string.

    Avoids repeated string slicing/allocation by tracking a mutable index.
    """

    __slots__ = ("raw_text", "index", "length")

    def __init__(self, raw_text: str) -> None:
        self.raw_text = raw_text
        self.index = 0
        self.length = len(raw_text)

    def read(self, count: int) -> str:
        """Read *count* characters and advance the index."""
        new_index = self.index + count
        if new_index > self.length:
            buf = self.raw_text[self.index :]
        else:
            buf = self.raw_text[self.index : new_index]
        self.index = new_index
        return buf

    def seek(self, offset: int) -> None:
        """Move the index by *offset* characters (can be negative)."""
        self.index += offset

    def advance_past_chars(self, chars: List[str]) -> str:
        """Advance past the first occurrence of any character in *chars*.

        Returns the substring *before* the matched character.
        """
        start_index = self.index
        while self.index < self.length:
            current_char = self.raw_text[self.index]
            self.index += 1
            if current_char in chars:
                break
        else:
            # Reached end without finding any of the chars
            pass
        return self.raw_text[start_index : self.index - 1]

    def advance_past_string_with_gdb_escapes(self) -> str:
        """Advance past a GDB MI quoted string, returning the unescaped content.

        Must be called immediately after consuming the opening ``\"``.
        """
        unescaped_str, self.index = _unescape_internal(
            self.raw_text, expect_closing_quote=True, start=self.index
        )
        return unescaped_str


# ---------------------------------------------------------------------------
# Recursive-descent MI value parsers
# ---------------------------------------------------------------------------

_WHITESPACE = frozenset(" \t\r\n")


def _parse_dict(stream: StringStream) -> Dict[str, Any]:
    """Parse a GDB MI dict value.  The opening ``{`` has already been consumed."""
    obj: Dict[str, Any] = {}

    while True:
        c = stream.read(1)
        if c in _WHITESPACE:
            continue
        elif c in ("{", ","):
            continue
        elif c in ("}", ""):
            break
        else:
            stream.seek(-1)
            key, val = _parse_key_val(stream)

            # Handle GDB bug: repeated keys (e.g. thread-ids={thread-id="1",thread-id="2"})
            # Merge into a list instead of overwriting.
            if key in obj:
                existing = obj[key]
                if isinstance(existing, list):
                    existing.append(val)
                else:
                    obj[key] = [existing, val]
            else:
                obj[key] = val

            # Skip any garbage between values
            c = stream.read(1)
            while c not in ("}", ",", ""):
                c = stream.read(1)
            stream.seek(-1)

    return obj


def _parse_key_val(stream: StringStream) -> Tuple[str, Any]:
    """Parse ``key=value`` from the stream."""
    key = stream.advance_past_chars(["="])
    val = _parse_val(stream)
    return key, val


def _parse_val(stream: StringStream) -> Any:
    """Parse a value: dict, array, or quoted string."""
    while True:
        c = stream.read(1)
        if c == "{":
            return _parse_dict(stream)
        elif c == "[":
            return _parse_array(stream)
        elif c == '"':
            return stream.advance_past_string_with_gdb_escapes()
        elif c == "":
            return ""
        else:
            # Unexpected character – skip and try again
            logger.debug("Skipping unexpected character in value: %r", c)
            continue


def _parse_array(stream: StringStream) -> List[Any]:
    """Parse an array.  The opening ``[`` has already been consumed."""
    arr: List[Any] = []

    while True:
        c = stream.read(1)
        if c in ('"', "{", "["):
            stream.seek(-1)
            val = _parse_val(stream)
            arr.append(val)
        elif c in _WHITESPACE or c == ",":
            continue
        elif c == "]" or c == "":
            break

    return arr


# ---------------------------------------------------------------------------
# Top-level MI line parsers
# ---------------------------------------------------------------------------

# Regex components
_GDB_MI_COMPONENT_TOKEN = r"(?P<token>\d+)?"
_GDB_MI_COMPONENT_PAYLOAD = r"(?P<payload>,.*)?$"

# Match (gdb) prompt
_GDB_MI_RESPONSE_FINISHED_RE = re.compile(r"^\(gdb\)\s*$")

# Parser function signature
_PARSER_FUNCTION = Callable[[Match, StringStream], Dict[str, Any]]


def _parse_mi_result(match: Match, stream: StringStream) -> Dict[str, Any]:
    """Parse a result record: ``[token]^result-class[,payload]``."""
    return {
        "type": "result",
        "message": match["message"],
        "payload": _extract_payload(match, stream),
        "token": _extract_token(match),
    }


def _parse_mi_notify(match: Match, stream: StringStream) -> Dict[str, Any]:
    """Parse an async record: ``[token]*|=async-class[,payload]``."""
    return {
        "type": "notify",
        "message": match["message"].strip(),
        "payload": _extract_payload(match, stream),
        "token": _extract_token(match),
    }


def _parse_mi_output(
    match: Match, stream: StringStream, output_type: str
) -> Dict[str, Any]:
    """Parse a stream record: ``~"..."`` / ``&"..."`` / ``@"..."``."""
    return {
        "type": output_type,
        "message": None,
        "payload": unescape(match["payload"]),
    }


def _parse_mi_finished(match: Match, stream: StringStream) -> Dict[str, Any]:
    """Parse the ``(gdb)`` prompt."""
    return {
        "type": "done",
        "message": None,
        "payload": None,
    }


def _extract_token(match: Match) -> Optional[int]:
    """Extract the integer token from a regex match, or None."""
    token = match["token"]
    return int(token) if token is not None else None


def _extract_payload(match: Match, stream: StringStream) -> Optional[Dict[str, Any]]:
    """Extract and parse a payload dict from a regex match."""
    if match["payload"] is None:
        return None
    stream.advance_past_chars([","])
    return _parse_dict(stream)


# Ordered list of (pattern, parser) pairs.  First match wins.
_GDB_MI_PATTERNS_AND_PARSERS: List[Tuple[Pattern, _PARSER_FUNCTION]] = [  # type: ignore[type-arg]
    # Result records: [token]^result-class[,payload]
    (
        re.compile(
            rf"^{_GDB_MI_COMPONENT_TOKEN}\^(?P<message>\S+?){_GDB_MI_COMPONENT_PAYLOAD}"
        ),
        _parse_mi_result,
    ),
    # Async records (exec and notify): [token]*|=async-class[,payload]
    (
        re.compile(
            rf"^{_GDB_MI_COMPONENT_TOKEN}[*=](?P<message>\S+?){_GDB_MI_COMPONENT_PAYLOAD}"
        ),
        _parse_mi_notify,
    ),
    # Console stream output: ~"..."
    (
        re.compile(r'~"(?P<payload>.*)"', re.DOTALL),
        functools.partial(_parse_mi_output, output_type="console"),
    ),
    # Log stream output: &"..."
    (
        re.compile(r'&"(?P<payload>.*)"', re.DOTALL),
        functools.partial(_parse_mi_output, output_type="log"),
    ),
    # Target stream output: @"..."
    (
        re.compile(r'@"(?P<payload>.*)"', re.DOTALL),
        functools.partial(_parse_mi_output, output_type="target"),
    ),
    # (gdb) prompt
    (
        _GDB_MI_RESPONSE_FINISHED_RE,
        _parse_mi_finished,
    ),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_response(gdb_mi_text: str) -> Dict[str, Any]:
    """Parse a single line of GDB/MI output into a structured dictionary.

    Args:
        gdb_mi_text: One line of GDB MI output (may include trailing newline).

    Returns:
        A dict with keys ``type``, ``message``, ``payload``, ``token``.

    Examples::

        >>> parse_response('~"Hello\\\\n"')
        {'type': 'console', 'message': None, 'payload': 'Hello\\n'}

        >>> parse_response('1000^done,value="42"')
        {'type': 'result', 'message': 'done', 'payload': {'value': '42'}, 'token': 1000}

        >>> parse_response('*stopped,reason="breakpoint-hit",bkptno="1"')
        {'type': 'notify', 'message': 'stopped', 'payload': {'reason': 'breakpoint-hit', 'bkptno': '1'}, 'token': None}
    """
    gdb_mi_text = gdb_mi_text.strip()

    if not gdb_mi_text:
        return {"type": "output", "message": None, "payload": None, "token": None}

    stream = StringStream(gdb_mi_text)
    for pattern, parser in _GDB_MI_PATTERNS_AND_PARSERS:
        match = pattern.match(gdb_mi_text)
        if match is not None:
            return parser(match, stream)

    # Not recognized as MI output – treat as raw output from the inferior program
    return {
        "type": "output",
        "message": None,
        "payload": gdb_mi_text,
        "token": None,
    }


def response_is_finished(gdb_mi_text: str) -> bool:
    """Return True if the line is a ``(gdb)`` prompt (response finished marker)."""
    return _GDB_MI_RESPONSE_FINISHED_RE.match(gdb_mi_text.strip()) is not None
