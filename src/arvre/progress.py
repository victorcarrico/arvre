"""An animated status line for a slow, cold session scan.

The scan has to finish before Textual takes over the terminal (it runs an
alternate screen buffer that would hide or garble raw writes to the same
tty), so this prints to stderr, synchronously, before `App.run()`. It only
shows anything if the scan is actually slow and stderr is an interactive
terminal -- a warm, ~6ms scan stays silent, and so does `--print | pipe`,
a test harness, or CI.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import TextIO

from arvre.cache import ScanCache
from arvre.scanner import Session, discover

SHOW_AFTER_SECONDS = 0.2
FRAME_SECONDS = 0.25
FRAMES = ["building your arvre.", "building your arvre..", "building your arvre..."]


def frame_for_tick(tick: int) -> str:
    return FRAMES[tick % len(FRAMES)]


def scan_with_progress(root: Path, cache: ScanCache, *, stream: TextIO | None = None) -> dict[str, Session]:
    """discover(root, cache), with the animation if it runs long."""
    stream = stream if stream is not None else sys.stderr
    if not stream.isatty():
        return discover(root, cache)

    done = threading.Event()
    result: dict[str, Session] = {}

    def work() -> None:
        try:
            result.update(discover(root, cache))
        finally:
            done.set()

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    # Not wrapped in try/finally: on Ctrl-C this should return control
    # immediately, not block waiting for the rest of a cold scan to finish.
    # _animate() has its own try/finally to clear the line either way, and
    # the background thread is a daemon, so the process can exit without it.
    if not done.wait(timeout=SHOW_AFTER_SECONDS):
        _animate(done, stream)
    thread.join()
    return result


def _animate(done: threading.Event, stream: TextIO) -> None:
    tick = 0
    try:
        while not done.wait(timeout=FRAME_SECONDS):
            stream.write(f"\r{frame_for_tick(tick)}\033[K")
            stream.flush()
            tick += 1
    finally:
        stream.write("\r\033[K")  # always leave the line clean, even on Ctrl-C
        stream.flush()
