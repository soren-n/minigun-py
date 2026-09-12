"""
Filesystem fixtures

Directories under ``.minigun`` for tests that need a place on disk.
Temporary paths are removed at the end of a run; permanent paths outlive
it, for rendered artifacts such as images of generated structures.
"""

import secrets
import shutil
from pathlib import Path

#: The root of all fixture directories.
ROOT = Path(".minigun")


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
    """A fresh directory removed by ``cleanup_temporary``.

    :param source: A directory whose contents are copied into it.

    :raises FileNotFoundError: When ``source`` is not a directory.
    """
    return _fresh("temporary", source)


def permanent_path(source: Path | None = None) -> Path:
    """A fresh directory that outlives the run.

    :param source: A directory whose contents are copied into it.

    :raises FileNotFoundError: When ``source`` is not a directory.
    """
    return _fresh("permanent", source)


def cleanup_temporary() -> None:
    """Remove every temporary fixture directory."""
    temporary = ROOT / "temporary"
    if temporary.exists():
        shutil.rmtree(temporary)
