"""Infer parent/child links between sessions. See docs/forks.md."""

from __future__ import annotations

from collections import Counter, defaultdict

from arvre.scanner import Session


def link_forks(sessions: dict[str, Session]) -> None:
    """Set parent_id and child_ids on every session.

    A fork is a copy of its parent's records with the same uuids, so the parent
    of a session is the earlier session sharing the most uuids with it.
    """
    order = sorted(sessions.values(), key=lambda s: (s.first_ts, s.created))
    rank = {s.id: i for i, s in enumerate(order)}

    by_uuid: dict[str, list[str]] = defaultdict(list)
    for session in sessions.values():
        session.parent_id = None
        session.child_ids = []
        for uuid in session.uuids:
            by_uuid[uuid].append(session.id)

    for session in sessions.values():
        shared: Counter[str] = Counter()
        for uuid in session.uuids:
            for other_id in by_uuid[uuid]:
                if other_id != session.id and rank[other_id] < rank[session.id]:
                    shared[other_id] += 1
        if shared:
            session.parent_id = max(shared, key=lambda oid: (shared[oid], -rank[oid]))

    for session in sessions.values():
        if session.parent_id:
            sessions[session.parent_id].child_ids.append(session.id)
