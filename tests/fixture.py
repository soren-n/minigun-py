"""Properties of the filesystem fixtures."""

from pathlib import Path

import minigun.fixture as f
import minigun.generate as g
from minigun import check
from minigun.specify import conj, context, prop


@prop("temporary paths are fresh, distinct directories")
def _distinct(seed: int) -> bool:
    first, second = f.temporary_path(), f.temporary_path()
    return first != second and first.is_dir() and second.is_dir()


@context(g.bounded_dicts(0, 5, g.bounded_strings(1, 8, "abcxyz"), g.words()))
@prop("fixtures copy their source directory byte for byte")
def _copies(files: dict[str, str]) -> bool:
    source = f.temporary_path()
    for name, content in files.items():
        (source / name).write_text(content)
    copy = f.temporary_path(source)
    return {p.name: p.read_text() for p in copy.iterdir()} == files


@prop("cleanup removes temporary paths and keeps permanent ones")
def _cleanup(seed: int) -> bool:
    temporary = f.temporary_path()
    permanent = f.permanent_path()
    f.cleanup_temporary()
    kept = permanent.is_dir()
    permanent.rmdir()
    return not temporary.exists() and kept


@prop("a missing source is an error")
def _missing_source(seed: int) -> bool:
    try:
        f.temporary_path(Path(".minigun") / "no-such-directory")
    except FileNotFoundError:
        return True
    return False


spec = conj(_distinct, _copies, _cleanup, _missing_source)


if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
