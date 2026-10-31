import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

PROJECT_DIR = "-Users-me-project"
CWD = "/Users/me/project"
NOW = datetime.now(timezone.utc)


def stamp(hours_ago: float) -> str:
    return (NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def message(uuid: str, hours_ago: float, kind: str = "user", **extra) -> dict:
    return {
        "type": kind,
        "uuid": uuid,
        "timestamp": stamp(hours_ago),
        "cwd": CWD,
        "gitBranch": "main",
        "message": {"role": kind, "content": "hi"},
        **extra,
    }


def write_session(root: Path, session_id: str, records: list[dict]) -> Path:
    folder = root / PROJECT_DIR
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{session_id}.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def projects_root(tmp_path: Path) -> Path:
    """
    root  (3h ago, named)  ── fork  (1h ago, copies root's uuids + one new)
    other (30h ago)        unrelated, outside the 24h window
    empty                  only a last-prompt record, must be skipped
    """
    root_id = "aaaaaaaa-0000-0000-0000-000000000001"
    fork_id = "aaaaaaaa-0000-0000-0000-000000000002"
    other_id = "aaaaaaaa-0000-0000-0000-000000000003"
    empty_id = "aaaaaaaa-0000-0000-0000-000000000004"

    root_msgs = [
        message("u1", 3.2),
        message("u2", 3.1, kind="assistant"),
        {"type": "custom-title", "customTitle": "Auth refactor", "sessionId": root_id},
    ]
    write_session(tmp_path, root_id, root_msgs)

    fork_msgs = root_msgs[:2] + [
        message("u3", 1.0),
        {"type": "last-prompt", "lastPrompt": "try the other approach", "sessionId": fork_id},
    ]
    write_session(tmp_path, fork_id, fork_msgs)

    write_session(
        tmp_path,
        other_id,
        [message("o1", 30.0), message("o2", 29.9, kind="assistant")],
    )
    write_session(
        tmp_path,
        empty_id,
        [{"type": "last-prompt", "lastPrompt": "nothing", "sessionId": empty_id}],
    )
    return tmp_path
