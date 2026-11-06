"""Archive flags: which sessions are hidden from the graph.

Kept separate from the parse cache (arvre.cache): losing the cache just costs
one slow rescan, but losing this file means archived sessions silently
reappear, so it lives under the data dir, not the cache dir. Per-session
entries so tags, notes, or a pinned flag can be added later without a schema
migration (docs/plan-0.3.md). No delete here, ever -- archiving only hides a
session from the graph; it never touches the session file itself.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

STATE_VERSION = 1
PRUNE_AFTER_DAYS = 90


def default_state_path() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "arvre" / "state.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cutoff_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


@dataclass
class SessionState:
    archived_at: str | None = None
    last_seen: str = ""


class ArvreState:
    def __init__(self, sessions: dict[str, SessionState] | None = None) -> None:
        self._sessions: dict[str, SessionState] = sessions or {}
        self.dirty = False

    @classmethod
    def load(cls, path: Path | None = None) -> "ArvreState":
        path = path or default_state_path()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls()
        except (OSError, json.JSONDecodeError):
            _quarantine(path)
            return cls()
        if raw.get("version") != STATE_VERSION:
            return cls()
        sessions = {
            sid: SessionState(entry.get("archived_at"), entry.get("last_seen", ""))
            for sid, entry in raw.get("sessions", {}).items()
        }
        return cls(sessions)

    def save(self, path: Path | None = None) -> None:
        if not self.dirty:
            return
        path = path or default_state_path()
        payload = {
            "version": STATE_VERSION,
            "sessions": {
                sid: {"archived_at": s.archived_at, "last_seen": s.last_seen} for sid, s in self._sessions.items()
            },
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, path)
        self.dirty = False

    def is_archived(self, session_id: str) -> bool:
        entry = self._sessions.get(session_id)
        return entry is not None and entry.archived_at is not None

    def archived_ids(self) -> set[str]:
        return {sid for sid, s in self._sessions.items() if s.archived_at is not None}

    def set_archived(self, session_id: str, archived: bool) -> None:
        entry = self._sessions.setdefault(session_id, SessionState())
        entry.archived_at = _now_iso() if archived else None
        if not entry.last_seen:
            entry.last_seen = _now_iso()
        self.dirty = True

    def toggle_archived(self, session_id: str) -> bool:
        """Flips the flag and returns the new state."""
        new_state = not self.is_archived(session_id)
        self.set_archived(session_id, new_state)
        return new_state

    def mark_seen(self, session_ids: set[str]) -> None:
        """Call once, after a full successful scan. Refreshes last_seen on
        entries this scan actually found, then prunes anything -- archived
        or not -- that neither this scan nor the last 90 days have seen.
        A session with no entry here (never archived) needs no bookkeeping."""
        now = _now_iso()
        for sid in session_ids:
            entry = self._sessions.get(sid)
            if entry is not None:
                entry.last_seen = now
                self.dirty = True
        self._prune(session_ids)

    def _prune(self, seen_ids: set[str]) -> None:
        cutoff = _cutoff_iso(PRUNE_AFTER_DAYS)
        stale = [
            sid
            for sid, entry in self._sessions.items()
            if sid not in seen_ids and entry.last_seen and entry.last_seen < cutoff
        ]
        for sid in stale:
            del self._sessions[sid]
        if stale:
            self.dirty = True


def _quarantine(path: Path) -> None:
    """A corrupt state file is moved aside, never silently discarded."""
    try:
        path.rename(path.with_name(f"{path.name}.corrupt-{int(datetime.now().timestamp())}"))
    except OSError:
        pass
