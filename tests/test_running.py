import json
import os

from arvre import running
from arvre.running import RunningSession, pane_of, read_records, running_sessions, switch_to_pane_argv

SID = "aaaaaaaa-0000-0000-0000-000000000001"
OTHER = "aaaaaaaa-0000-0000-0000-000000000002"


def write_record(claude_dir, pid, session_id, **extra):
    folder = claude_dir / "sessions"
    folder.mkdir(parents=True, exist_ok=True)
    record = {"pid": pid, "sessionId": session_id, "cwd": "/p", "status": "idle", "kind": "interactive", **extra}
    (folder / f"{pid}.json").write_text(json.dumps(record), encoding="utf-8")


def test_read_records_skips_spares_garbage_and_key_files(tmp_path):
    write_record(tmp_path, 10, SID)
    write_record(tmp_path, 11, OTHER, kind="bg")
    (tmp_path / "sessions" / "12.json").write_text("not json", encoding="utf-8")
    (tmp_path / "sessions" / "10.abc.key").write_text('{"peerToken": "secret"}', encoding="utf-8")
    assert [r["sessionId"] for r in read_records(tmp_path / "sessions")] == [SID]


def test_read_records_without_a_sessions_dir_is_empty(tmp_path):
    assert read_records(tmp_path / "sessions") == []


def test_dead_processes_are_not_running(tmp_path, monkeypatch):
    write_record(tmp_path, 10, SID)
    write_record(tmp_path, 20, OTHER)
    monkeypatch.setattr(running, "process_parents", lambda: {10: 1})
    found = running_sessions(tmp_path, in_tmux=False)
    assert set(found) == {SID}
    assert found[SID] == RunningSession(SID, 10, "/p", "idle", None)


def test_tmux_pane_is_found_by_walking_up_the_process_tree(tmp_path, monkeypatch):
    write_record(tmp_path, 30, SID)
    # claude (30) <- shell (20) <- pane process (10) <- tmux server (1)
    monkeypatch.setattr(running, "process_parents", lambda: {30: 20, 20: 10, 10: 1})
    monkeypatch.setattr(running, "tmux_panes", lambda: {10: "%7"})
    assert running_sessions(tmp_path, in_tmux=True)[SID].tmux_pane == "%7"
    # Outside tmux, panes aren't even looked up.
    assert running_sessions(tmp_path, in_tmux=False)[SID].tmux_pane is None


def test_two_processes_on_one_session_prefer_the_reachable_one(tmp_path, monkeypatch):
    write_record(tmp_path, 30, SID)
    write_record(tmp_path, 40, SID)
    monkeypatch.setattr(running, "process_parents", lambda: {30: 1, 40: 10, 10: 1})
    monkeypatch.setattr(running, "tmux_panes", lambda: {10: "%7"})
    found = running_sessions(tmp_path, in_tmux=True)
    assert found[SID].pid == 40


def test_reused_pid_with_a_different_start_time_is_not_running(tmp_path):
    if not os.path.exists(f"/proc/{os.getpid()}/stat"):
        return  # /proc only exists on Linux
    write_record(tmp_path, os.getpid(), SID, procStart="1")
    assert running_sessions(tmp_path, in_tmux=False) == {}


def test_matching_start_time_is_running(tmp_path):
    stat_path = f"/proc/{os.getpid()}/stat"
    if not os.path.exists(stat_path):
        return
    start = open(stat_path).read().rsplit(")", 1)[-1].split()[19]
    write_record(tmp_path, os.getpid(), SID, procStart=start)
    assert set(running_sessions(tmp_path, in_tmux=False)) == {SID}


def test_pane_of_stops_on_cycles_and_missing_parents():
    assert pane_of(5, {5: 6, 6: 5}, {}) is None
    assert pane_of(5, {}, {}) is None


def test_switch_to_pane_selects_window_pane_and_session():
    assert switch_to_pane_argv("%7") == [
        "tmux", "select-window", "-t", "%7", ";", "select-pane", "-t", "%7", ";", "switch-client", "-t", "%7",
    ]
