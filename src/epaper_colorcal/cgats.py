"""Minimal CGATS (ANSI CGATS.17) reading and writing, as ArgyllCMS uses it.

Enough for one data table: the file type line (``CTI2``, ``CTI3``), keywords, the data
format (field names) and the data rows. Values are kept as the strings in the file.
"""

from __future__ import annotations

import shlex
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CGATS:
    file_type: str
    keywords: dict[str, str] = field(default_factory=dict)
    """Keyword -> value as written (strings keep their quotes)."""
    fields: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)

    def keyword(self, name: str) -> str | None:
        """A keyword's value without quotes, or None."""
        value = self.keywords.get(name)
        return None if value is None else value.strip().strip('"')

    def column(self, name: str) -> list[str]:
        i = self.fields.index(name)
        return [row[i] for row in self.rows]

    def records(self) -> list[dict[str, str]]:
        return [dict(zip(self.fields, row)) for row in self.rows]


def _tokens(line: str) -> list[str]:
    lexer = shlex.shlex(line, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = "#"
    return list(lexer)


def _block(lines: Iterator[str], end: str) -> list[list[str]]:
    """Tokenised lines up to ``end`` (exclusive), skipping blanks and comments."""
    out = []
    for line in lines:
        if line.strip() == end:
            break
        if line.strip() and not line.lstrip().startswith("#"):
            out.append(_tokens(line))
    return out


def parse(text: str) -> CGATS:
    lines = (line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#"))
    first = next(lines, None)
    if first is None:
        raise ValueError("empty CGATS file")
    table = CGATS(first.split()[0])
    for line in lines:
        word, _, rest = line.strip().partition(" ")
        if word == "BEGIN_DATA_FORMAT":
            table.fields = [name for tokens in _block(lines, "END_DATA_FORMAT") for name in tokens]
        elif word == "BEGIN_DATA":
            table.rows = _block(lines, "END_DATA")
        elif word not in ("KEYWORD", "NUMBER_OF_FIELDS", "NUMBER_OF_SETS"):
            table.keywords[word] = rest.strip()
    widths = {len(row) for row in table.rows}
    if table.rows and widths != {len(table.fields)}:
        raise ValueError(f"data rows have {sorted(widths)} values for {len(table.fields)} fields")
    return table


def read(path: str | Path) -> CGATS:
    return parse(Path(path).read_text(encoding="utf-8", errors="replace"))


# Keywords every CGATS reader knows; any other is declared with KEYWORD first.
_STANDARD = {"DESCRIPTOR", "ORIGINATOR", "CREATED", "MANUFACTURER", "PROD_DATE", "SERIAL", "MATERIAL"}


def dumps(table: CGATS) -> str:
    out = [f"{table.file_type}", ""]
    for name, value in table.keywords.items():
        if name not in _STANDARD:
            out.append(f'KEYWORD "{name}"')
        out.append(f"{name} {value}")
    out += [
        "",
        f"NUMBER_OF_FIELDS {len(table.fields)}",
        "BEGIN_DATA_FORMAT",
        " ".join(table.fields),
        "END_DATA_FORMAT",
        "",
        f"NUMBER_OF_SETS {len(table.rows)}",
        "BEGIN_DATA",
        *(" ".join(row) for row in table.rows),
        "END_DATA",
        "",
    ]
    return "\n".join(out)


def quoted(text: str) -> str:
    return '"' + text.replace('"', "'") + '"'
