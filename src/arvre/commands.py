"""Commands for resuming a session."""

from __future__ import annotations

import shlex

from arvre.scanner import Session


def resume_command(session: Session) -> str:
    # --resume is scoped to the project directory, so cd there first.
    return f"cd {shlex.quote(session.cwd)} && claude --resume {session.id}"
