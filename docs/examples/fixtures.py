"""Filesystem fixtures: temporary and permanent directories for a test."""

import json

import minigun.fixture as f
import minigun.generate as g
from minigun import check
from minigun.specify import conj, context, prop


# -- start: temporary --
@context(g.lists(g.words()))
@prop("Lines written to a file are read back unchanged")
def _round_trip(lines: list[str]) -> bool:
    path = f.temporary_path() / "lines.txt"
    path.write_text("\n".join(lines))
    return path.read_text().split("\n") == (lines or [""])


# -- end: temporary --


# -- start: permanent --
# One artifact directory per run, created when the module loads.
ARTIFACTS = f.permanent_path()


@context(g.dicts(g.words(), g.ints()), g.small_nats())
@prop("Rendered artifacts outlive the run")
def _render(table: dict[str, int], index: int) -> bool:
    artifact = ARTIFACTS / f"table-{index}.json"
    artifact.write_text(json.dumps(table, indent=2))
    loaded: dict[str, int] = json.loads(artifact.read_text())
    return loaded == table


# -- end: permanent --

spec = conj(_round_trip, _render)

if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
