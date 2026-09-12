"""
Filesystem fixtures

Directories under ``.minigun`` for tests that need a place on disk.
Temporary paths belong to the run that created them and are removed when
it ends; permanent paths outlive it, for rendered artifacts such as images
of generated structures.
"""

import secrets
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

#: The root of all fixture directories.
ROOT = Path(".minigun")

# Temporary paths created within each active scope, innermost last.
_scopes: list[list[Path]] = []


def _fresh(kind: str, source: Path | None) -> Path:
    path = ROOT / kind / secrets.token_hex(15)
    path.parent.mkdir(parents=True, exist_ok=True)
    if source is not None:
        if not source.is_dir():
            raise FileNotFoundError(
                f"Fixture source {source} is not a directory"
            )
        shutil.copytree(source, path)
    else:
        path.mkdir()
    return path


def temporary_path(source: Path | None = None) -> Path:
    """A fresh directory removed when the enclosing scope ends.

    Outside any scope the directory is removed by ``cleanup_temporary``.

    :param source: A directory whose contents are copied into it.

    :raises FileNotFoundError: When ``source`` is not a directory.
    """
    path = _fresh("temporary", source)
    if _scopes:
        _scopes[-1].append(path)
    return path


def permanent_path(source: Path | None = None) -> Path:
    """A fresh directory that outlives the run.

    :param source: A directory whose contents are copied into it.

    :raises FileNotFoundError: When ``source`` is not a directory.
    """
    return _fresh("permanent", source)


@contextmanager
def scope() -> Iterator[None]:
    """A scope whose temporary paths are removed when it ends.

    Scopes nest: a run inside a run removes only its own paths.
    """
    created: list[Path] = []
    _scopes.append(created)
    try:
        yield
    finally:
        _scopes.pop()
        for path in created:
            if path.exists():
                shutil.rmtree(path)


def cleanup_temporary() -> None:
    """Remove every temporary fixture directory, whatever created it."""
    temporary = ROOT / "temporary"
    if temporary.exists():
        shutil.rmtree(temporary)
