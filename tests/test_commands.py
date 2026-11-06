from conftest import NOW

from arvre.commands import fork_argv, new_session_argv, new_session_id, resume_argv
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
