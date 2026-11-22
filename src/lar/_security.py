"""
Small security helpers shared across Lár modules.

- ``safe_id``: validate an identifier before it is used as part of a file name.
- ``secure_makedirs`` / ``secure_write_text`` / ``secure_append_text``: create
  directories ``0700`` and files ``0600`` so audit logs, checkpoints and ledgers
  are not world-readable on a shared host.
"""
import os
import re
from pathlib import Path
from typing import Union

# Letters, digits, dot, underscore, hyphen; must start with an alphanumeric.
# No path separators, no leading dot, so ".." and absolute paths are impossible.
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def safe_id(value: str, what: str = "identifier") -> str:
    """Return ``value`` if it is safe to use inside a file name, else raise ``ValueError``."""
    if not isinstance(value, str) or not _SAFE_ID.match(value) or ".." in value:
        raise ValueError(
            f"Unsafe {what} {value!r}: use 1-128 characters from A-Z a-z 0-9 . _ - "
            f"starting with a letter or digit (no path separators or '..')."
        )
    return value


def secure_makedirs(path: Union[str, os.PathLike]) -> None:
    """Create a directory (and parents) with owner-only permissions."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(p, 0o700)
    except OSError:
        pass


def _open_private(path: Union[str, os.PathLike], flags: int):
    fd = os.open(str(path), flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
    except (OSError, AttributeError):
        pass
    return os.fdopen(fd, "w", encoding="utf-8")


def secure_write_text(path: Union[str, os.PathLike], text: str, atomic: bool = True) -> None:
    """Write ``text`` to ``path`` with mode 0600; atomic replace by default."""
    path = str(path)
    if atomic:
        tmp = f"{path}.tmp.{os.getpid()}"
        with _open_private(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    else:
        with _open_private(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())


def secure_append_text(path: Union[str, os.PathLike], text: str) -> None:
    """Append ``text`` to ``path`` (mode 0600) and fsync so the line survives a crash."""
    with _open_private(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND) as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
