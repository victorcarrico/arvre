"""Persistent, disposable cache of parsed session metadata.

Parsing every line of every session file with json.loads is the entire cost
of a scan -- 99% of it, measured on a 300-session / 650 MB corpus
(docs/plan-0.3.md). This cache lets a warm run skip that work for any file
whose (mtime, size) -- and title sidecar mtime -- haven't changed, which cut
that scan from ~2.8s to ~6ms in the same measurement.

Safe to delete at any time: deleting it only costs one slow rescan. Never
written anywhere under ~/.claude -- that directory belongs to Claude Code.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from arvre.scanner import Session, UUID_PREFIX_LEN, parse_ts

CACHE_VERSION = 1

MISS = object()  # returned by ScanCache.lookup() on a miss; a hit may legitimately be None


def default_cache_path() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "arvre" / "scan-v1.json"


@dataclass(frozen=True)
class _Entry:
    mtime_ns: int
    size: int
    title_mtime_ns: int
    session: Session | None  # None means "parsed, but had no messages"


class ScanCache:
    """Maps a session file's path to its already-parsed Session, valid as
    long as the file's (mtime, size) and its title sidecar's mtime match."""

    def __init__(self) -> None:
        self._entries: dict[str, _Entry] = {}
        self.dirty = False

    @classmethod
    def load(cls, path: Path | None = None) -> "ScanCache":
        cache = cls()
        path = path or default_cache_path()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cache
        if raw.get("version") != CACHE_VERSION:
            return cache
        for path_str, entry in raw.get("sessions", {}).items():
            try:
                cache._entries[path_str] = _entry_from_json(path_str, entry)
            except (KeyError, TypeError, ValueError):
                continue  # one corrupt entry doesn't invalidate the rest
        return cache

    def save(self, path: Path | None = None) -> None:
        if not self.dirty:
            return
        path = path or default_cache_path()
        payload = {
            "version": CACHE_VERSION,
            "sessions": {path_str: _entry_to_json(entry) for path_str, entry in self._entries.items()},
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, path)
        self.dirty = False

    def lookup(self, path_str: str, mtime_ns: int, size: int, title_mtime_ns: int) -> Session | None:
        """Returns the cached Session (or None, for a known-empty file) on a
        hit, or the MISS sentinel if nothing cached matches this key."""
        entry = self._entries.get(path_str)
        if entry is None:
            return MISS
        if (entry.mtime_ns, entry.size, entry.title_mtime_ns) != (mtime_ns, size, title_mtime_ns):
            return MISS
        return entry.session

    def store(self, path_str: str, mtime_ns: int, size: int, title_mtime_ns: int, session: Session | None) -> None:
        self._entries[path_str] = _Entry(mtime_ns, size, title_mtime_ns, session)
        self.dirty = True


def _entry_to_json(entry: _Entry) -> dict:
    data: dict = {"mtime_ns": entry.mtime_ns, "size": entry.size, "title_mtime_ns": entry.title_mtime_ns}
    if entry.session is not None:
        s = entry.session
        data["session"] = {
            "id": s.id,
            "cwd": s.cwd,
            "name": s.name,
            "first": s.first_ts.isoformat(),
            "last": s.last_ts.isoformat(),
            "branch": s.branch,
            "created": s.created,
            # Fixed-width uuids concatenated into one string: ~3x smaller and
            # ~9x faster to load than a JSON array (docs/plan-0.3.md).
            "u": "".join(sorted(s.uuids)),
        }
    return data


def _entry_from_json(path_str: str, data: dict) -> _Entry:
    session_data = data.get("session")
    session = None
    if session_data is not None:
        blob = session_data.get("u", "")
        uuids = frozenset(blob[i : i + UUID_PREFIX_LEN] for i in range(0, len(blob), UUID_PREFIX_LEN))
        session = Session(
            id=session_data["id"],
            path=Path(path_str),
            cwd=session_data["cwd"],
            name=session_data["name"],
            first_ts=parse_ts(session_data["first"]),
            last_ts=parse_ts(session_data["last"]),
            branch=session_data["branch"],
            created=session_data["created"],
            uuids=uuids,
        )
    return _Entry(data["mtime_ns"], data["size"], data.get("title_mtime_ns", 0), session)
