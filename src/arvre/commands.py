"""Argument lists for resuming, forking, and starting Claude Code sessions."""

from __future__ import annotations

import shlex
import uuid

from arvre.scanner import Session


def new_session_id() -> str:
    return str(uuid.uuid4())


def resume_argv(session: Session) -> list[str]:
    return ["claude", "--resume", session.id]


def fork_argv(session: Session, new_id: str) -> list[str]:
    """Fork `session`: `new_id` starts from its tip, carrying its history.

    Verified in docs/plan-0.3.md (spike, session 15e749ac): --resume,
    --fork-session and --session-id combine as expected -- the fork lands at
    exactly `new_id` and shares the parent's message uuids, so
    arvre.forks.link_forks links it on the very next scan, no extra
    bookkeeping required.
    """
    return ["claude", "--resume", session.id, "--fork-session", "--session-id", new_id]


def new_session_argv(new_id: str) -> list[str]:
    return ["claude", "--session-id", new_id]


def resume_command(session: Session) -> str:
    # --resume is scoped to the project directory, so cd there first.
    return f"cd {shlex.quote(session.cwd)} && claude --resume {session.id}"
