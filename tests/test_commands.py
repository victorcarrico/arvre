from conftest import NOW

from pathlib import Path

import pytest

from arvre.commands import (
    fork_argv,
    new_session_argv,
    new_session_id,
    resume_argv,
    tmux_argv,
    tmux_window_name,
)
from arvre.scanner import Session


def make_session(session_id: str = "abc") -> Session:
    return Session(
        id=session_id,
        path=None,
        cwd="/Users/me/my project",
        name="x",
        first_ts=NOW,
        last_ts=NOW,
        branch="",
        created=0,
        uuids=frozenset(),
    )


def test_resume_argv():
    assert resume_argv(make_session()) == ["claude", "--resume", "abc"]


def test_fork_argv_combines_resume_fork_session_and_session_id():
    # Combination verified against the real CLI in docs/plan-0.3.md.
    assert fork_argv(make_session(), "new-id") == [
        "claude", "--resume", "abc", "--fork-session", "--session-id", "new-id",
    ]


def test_new_session_argv():
    assert new_session_argv("new-id") == ["claude", "--session-id", "new-id"]


def test_new_session_id_is_a_fresh_uuid_each_time():
    a, b = new_session_id(), new_session_id()
    assert a != b
    assert len(a) == 36


def test_tmux_window_runs_the_quoted_command_in_the_session_directory():
    argv = tmux_argv("window", ["claude", "--resume", "abc"], "/Users/me/my project", "x")
    assert argv == ["tmux", "new-window", "-c", "/Users/me/my project", "-n", "x", "claude --resume abc"]


def test_tmux_pane_splits_beside_the_current_pane():
    argv = tmux_argv("pane", ["claude", "--resume", "abc"], "/tmp/p", "x")
    assert argv == ["tmux", "split-window", "-h", "-c", "/tmp/p", "claude --resume abc"]


def test_tmux_command_carries_a_non_default_claude_dir():
    argv = tmux_argv("window", ["claude"], "/tmp/p", "x", claude_dir=Path("/opt/my claude"))
    assert argv[-1] == "CLAUDE_CONFIG_DIR='/opt/my claude' claude"


def test_tmux_argv_rejects_here():
    with pytest.raises(ValueError):
        tmux_argv("here", ["claude"], "/tmp/p", "x")


def test_tmux_window_name_is_collapsed_and_truncated():
    assert tmux_window_name("  fix\nthe   bug ") == "fix the bug"
    assert tmux_window_name("") == "claude"
    assert len(tmux_window_name("a" * 100)) == 24
