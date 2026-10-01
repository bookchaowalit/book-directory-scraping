"""Crash-safe file writes for the reports under ``data/``.

``Path.write_text`` truncates the target before writing, so a run killed
mid-write (timeout, Ctrl-C, power loss) leaves an empty or half-written
report. ``write_text_atomic`` writes a temporary file in the same directory,
flushes and fsyncs it, then ``os.replace``-s it over the target, which is
atomic on POSIX and Windows (same volume). Readers see the old file or the
new one, never a partial one.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_text_atomic(path: str | Path, text: str, encoding: str = "utf-8") -> None:
    """Atomically replace ``path`` with ``text``."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
