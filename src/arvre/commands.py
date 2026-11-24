"""Argument lists for resuming, forking, and starting Claude Code sessions."""

from __future__ import annotations

import shlex
import uuid
from pathlib import Path

from arvre.config import DEFAULT_CLAUDE_DIR
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


def _env_prefix(claude_dir: Path | None) -> str:
    if claude_dir is not None and claude_dir != DEFAULT_CLAUDE_DIR:
        return f"CLAUDE_CONFIG_DIR={shlex.quote(str(claude_dir))} "
    return ""


def resume_command(session: Session, claude_dir: Path | None = None) -> str:
    # --resume is scoped to the project directory, so cd there first.
    return f"cd {shlex.quote(session.cwd)} && {_env_prefix(claude_dir)}claude --resume {session.id}"


LAUNCH_TARGETS = ("here", "window", "pane")


def tmux_argv(target: str, argv: list[str], cwd: str, name: str, claude_dir: Path | None = None) -> list[str]:
    """Run `argv` in `cwd` in a new tmux window or a new pane split beside this one.

    The command is handed to tmux as one shell string, so CLAUDE_CONFIG_DIR
    can ride along as a prefix (`new-window -e` would need tmux >= 3.0).
    """
    shell_command = _env_prefix(claude_dir) + shlex.join(argv)
    if target == "window":
        return ["tmux", "new-window", "-c", cwd, "-n", name, shell_command]
    if target == "pane":
        return ["tmux", "split-window", "-h", "-c", cwd, shell_command]
    raise ValueError(f"not a tmux launch target: {target!r}")


def tmux_window_name(name: str, limit: int = 24) -> str:
    name = " ".join(name.split()) or "claude"
    return name if len(name) <= limit else name[: limit - 1] + "…"
