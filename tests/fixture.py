"""Properties of the filesystem fixtures."""

from pathlib import Path

import minigun.fixture as f
import minigun.generate as g
from minigun import check
from minigun.specify import conj, context, prop
from tests._support import isolated_fixtures


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


@prop("a scope removes its own temporary paths and keeps permanent ones")
def _scope(seed: int) -> bool:
    with isolated_fixtures():
        outer = f.temporary_path()
        with f.scope():
            inner = f.temporary_path()
            permanent = f.permanent_path()
            inner_existed = inner.is_dir()
        kept = permanent.is_dir()
        return inner_existed and not inner.exists() and outer.is_dir() and kept


@prop("cleanup removes every temporary path")
def _cleanup(seed: int) -> bool:
    # Under a root of its own: cleanup removes every temporary path under
    # the root, also those of properties running beside this one.
    with isolated_fixtures():
        temporary = f.temporary_path()
        f.cleanup_temporary()
        return not temporary.exists()


@prop("an isolated fixture root is removed and the previous one restored")
def _isolated(seed: int) -> bool:
    previous = f.ROOT
    with isolated_fixtures() as root:
        inside = (
            f.ROOT == root and f.permanent_path().parent == root / "permanent"
        )
    return inside and f.ROOT == previous and not root.exists()


@prop("a worker's temporary paths are handed to the run's scope")
def _handed_over(seed: int) -> bool:
    with isolated_fixtures():
        with f.scope():
            with f.scope():
                made = f.temporary_path()
                detached = f._detach()
            survived = made.is_dir()
            f._adopt(detached)
        return detached == [made] and survived and not made.exists()


@prop("a missing source is an error")
def _missing_source(seed: int) -> bool:
    try:
        f.temporary_path(Path(".minigun") / "no-such-directory")
    except FileNotFoundError:
        return True
    return False


spec = conj(
    _distinct,
    _copies,
    _scope,
    _cleanup,
    _isolated,
    _handed_over,
    _missing_source,
)


if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
