"""
Recorded counterexamples

A regressions file records the failing draws of earlier runs, so later runs
replay them before their own attempts and a bug stays covered after it is
fixed. An entry is a property's description, the seed of the run that
found the failure and the index of the attempt that drew it. A property's
draws depend only on the seed and its description, so an entry draws the
same arguments again for as long as the property's generators are
unchanged, and shrinking then reaches the same counterexample.

An entry also keeps the canonical text (``minigun.canonical``) of the
arguments the attempt drew. When a generator changes, the attempt draws
something else; the replay compares the text of what it draws with the
recorded text, and an entry that no longer matches is stale: its
property fails, saying which entries to remove, instead of silently
replaying a draw that no longer covers the bug.

The shrunk arguments and the exception are also recorded as text, for
reading only: nothing is replayed from the text, so no value is
serialized.

A file is JSON, written whole through a temporary file so a run that stops
midway never leaves it half written. Entries are kept in the order they
were recorded and are only removed by hand.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from minigun import canonical
from minigun.parallel import exception_name
from minigun.specify import Outcome, Recorded

__all__ = [
    "FORMAT",
    "VERSION",
    "RegressionsError",
    "Regression",
    "module_file",
    "load",
    "record",
    "check_properties",
    "from_outcome",
]

#: The format tag of a regressions file.
FORMAT = "minigun-regressions"

#: The version of the format this module reads and writes.
VERSION = 2

_NOTE = (
    "Failing draws recorded by minigun, each replayed before its "
    "property's own attempts. Keep this file in version control; remove "
    "an entry to stop replaying it."
)

_KEYS = frozenset(
    {"property", "seed", "attempt", "drawn", "arguments", "exception"}
)
_TOP_KEYS = frozenset({"format", "version", "note", "regressions"})


class RegressionsError(Exception):
    """A regressions file cannot be read, or records properties the
    specification does not define."""


@dataclass(frozen=True)
class Regression:
    """A recorded failing draw.

    :param desc: The description of the property it falsified.
    :param seed: The seed of the run that drew it.
    :param attempt: The zero-based index of the attempt that drew it.
    :param drawn: The canonical text of the arguments the attempt drew,
        by name, which a replay checks it draws again.
    :param arguments: The shrunk counterexample's arguments as canonical
        text, for reading.
    :param exception: The exception the law raised on them as
        ``Type: message``, or None when the law returned False.
    """

    desc: str
    seed: int
    attempt: int
    drawn: dict[str, str]
    arguments: dict[str, str]
    exception: str | None = None

    @property
    def key(self) -> tuple[str, int, int]:
        """What identifies the draw: the property, seed and attempt."""
        return self.desc, self.seed, self.attempt

    @property
    def recorded(self) -> Recorded:
        """The draw for its property to replay."""
        return Recorded(self.seed, self.attempt, dict(self.drawn))


def module_file(directory: Path, module: str) -> Path:
    """The regressions file of a test module in a directory."""
    return directory / f"{module}.json"


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _entry(path: Path, index: int, entry: Any) -> Regression:
    def _bad(why: str) -> RegressionsError:
        return RegressionsError(
            f"Entry {index} of the regressions file {path} {why}"
        )

    if not isinstance(entry, dict) or set(entry) != _KEYS:
        raise _bad(
            f"must be an object with the keys {', '.join(sorted(_KEYS))}"
        )
    desc = entry["property"]
    seed = entry["seed"]
    attempt = entry["attempt"]
    drawn = entry["drawn"]
    arguments = entry["arguments"]
    exception = entry["exception"]
    if not isinstance(desc, str):
        raise _bad("names its property with something other than a string")
    if not _is_int(seed):
        raise _bad(f"has a seed that is not an integer: {seed!r}")
    if not _is_int(attempt) or attempt < 0:
        raise _bad(f"has an attempt that is not a natural number: {attempt!r}")
    if not _texts(drawn):
        raise _bad("has drawn arguments that are not strings by name")
    if not _texts(arguments):
        raise _bad("has arguments that are not strings by name")
    if exception is not None and not isinstance(exception, str):
        raise _bad("has an exception that is neither a string nor null")
    return Regression(
        desc, seed, attempt, dict(drawn), dict(arguments), exception
    )


def _texts(value: Any) -> bool:
    return isinstance(value, dict) and all(
        isinstance(name, str) and isinstance(text, str)
        for name, text in value.items()
    )


def load(path: Path) -> list[Regression]:
    """The regressions recorded in a file, in the order recorded; none
    when the file does not exist.

    :raises RegressionsError: When the file cannot be read or is not a
        regressions file of this version.
    """
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RegressionsError(
            f"Cannot read the regressions file {path}: {error}"
        ) from error
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise RegressionsError(
            f'{path} is not a regressions file: its "format" is not "{FORMAT}"'
        )
    unknown = sorted(set(data) - _TOP_KEYS)
    if unknown:
        raise RegressionsError(
            f"The regressions file {path} has unknown keys: "
            f"{', '.join(unknown)}"
        )
    if data.get("version") != VERSION:
        raise RegressionsError(
            f"The regressions file {path} has version "
            f"{data.get('version')!r}; this version of minigun reads "
            f"version {VERSION}"
            + (
                ". Version 1 entries do not record what their attempts "
                "drew, so a replay cannot tell whether they are stale; "
                "remove the file and record the failures again"
                if data.get("version") == 1
                else ""
            )
        )
    entries = data.get("regressions")
    if not isinstance(entries, list):
        raise RegressionsError(
            f'The regressions file {path} has no list of "regressions"'
        )
    return [_entry(path, index, entry) for index, entry in enumerate(entries)]


def _save(path: Path, regressions: list[Regression]) -> None:
    data = {
        "format": FORMAT,
        "version": VERSION,
        "note": _NOTE,
        "regressions": [
            {
                "property": regression.desc,
                "seed": regression.seed,
                "attempt": regression.attempt,
                "drawn": regression.drawn,
                "arguments": regression.arguments,
                "exception": regression.exception,
            }
            for regression in regressions
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def record(path: Path, regression: Regression) -> bool:
    """Add a regression to a file, creating the file and its directory
    when missing.

    :return: Whether it was added; False when the file already records
        the same draw.

    :raises RegressionsError: When the existing file cannot be read.
    """
    regressions = load(path)
    if any(entry.key == regression.key for entry in regressions):
        return False
    _save(path, [*regressions, regression])
    return True


def check_properties(
    path: Path, regressions: list[Regression], descs: Iterable[str]
) -> None:
    """Check that every regression names a property of a specification.

    An entry of a property that was renamed or removed would otherwise
    never be replayed again, and the bug it records would silently lose
    its coverage.

    :param path: The file the regressions were loaded from, for the error.
    :param descs: The descriptions of every property of the specification.

    :raises RegressionsError: When a regression names another property.
    """
    unknown = sorted({entry.desc for entry in regressions} - set(descs))
    if unknown:
        raise RegressionsError(
            f"The regressions file {path} records counterexamples of "
            "properties the specification does not define: "
            + ", ".join(f'"{desc}"' for desc in unknown)
            + "; rename or remove their entries"
        )


def from_outcome(
    seed: int, outcome: Outcome, drawn: dict[str, str]
) -> Regression | None:
    """The regression to record for an outcome of a run: one whose law
    failed on a counterexample the run drew itself.

    :param seed: The run seed.
    :param drawn: The canonical text of the arguments the failing attempt
        drew (``specify.drawn_text`` of the attempt drawn again, since the
        law may have changed the arguments it was given).

    :return: The regression, or None when the property held, failed
        without a counterexample, or failed on a replayed one.
    """
    example = outcome.counter_example
    if (
        outcome.holds
        or outcome.negated
        or example is None
        or example.seed is not None
    ):
        return None
    return Regression(
        outcome.desc,
        seed,
        example.attempt,
        dict(drawn),
        {name: canonical.text(value) for name, value in example.args.items()},
        None
        if example.exception is None
        else f"{exception_name(example.exception)}: {example.exception}",
    )
