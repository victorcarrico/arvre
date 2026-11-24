"""Which sessions have a live `claude` process, and which tmux pane holds it.

Claude Code writes one record per running process to
<claude dir>/sessions/<pid>.json, holding (among other things) the process's
`sessionId`, `cwd`, `status` and `procStart`. Only those `*.json` records are
read here -- the `*.key` files beside them hold tokens and are never opened.
This is an undocumented format, like the session files themselves, so every
field is optional and anything unexpected just means "not running".

A record can outlive its process (a crash leaves it behind), so each one is
checked against the live process table. On Linux its `procStart` is also
compared with /proc/<pid>/stat, so a reused pid isn't mistaken for it.

The tmux pane is found by walking up from the claude process to a pane's
shell, using *this* tmux server's pane list. That way a pane id is only
reported when this arvre can actually switch to it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunningSession:
    session_id: str
    pid: int
    cwd: str
    status: str
    tmux_pane: str | None = None  # e.g. "%173", in this arvre's tmux server


def running_sessions(claude_dir: Path, in_tmux: bool) -> dict[str, RunningSession]:
    records = read_records(claude_dir / "sessions")
    if not records:
        return {}
    parents = process_parents()
    panes = tmux_panes() if in_tmux else {}
    found: dict[str, RunningSession] = {}
    for record in records:
        pid = record["pid"]
        if pid not in parents or not _same_process(pid, record.get("procStart")):
            continue
        running = RunningSession(
            session_id=record["sessionId"],
            pid=pid,
            cwd=str(record.get("cwd") or ""),
            status=str(record.get("status") or ""),
            tmux_pane=pane_of(pid, parents, panes),
        )
        previous = found.get(running.session_id)
        # Two processes on one session: prefer the one arvre can switch to.
        if previous is None or (previous.tmux_pane is None and running.tmux_pane is not None):
            found[running.session_id] = running
    return found


def read_records(directory: Path) -> list[dict]:
    records = []
    try:
        paths = list(directory.glob("*.json"))
    except OSError:
        return []
    for path in paths:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (
            isinstance(record, dict)
            and isinstance(record.get("pid"), int)
            and isinstance(record.get("sessionId"), str)
            and record["sessionId"]
            # "bg" is Claude's pre-started spare process, not a session anyone opened.
            and record.get("kind") != "bg"
        ):
            records.append(record)
    return records


def process_parents() -> dict[int, int]:
    """pid -> parent pid for every live process (works on Linux and macOS)."""
    try:
        out = subprocess.run(
            ["ps", "-A", "-o", "pid=", "-o", "ppid="], capture_output=True, text=True, check=False, timeout=5
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    parents = {}
    for line in out.splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[0].isdigit() and fields[1].isdigit():
            parents[int(fields[0])] = int(fields[1])
    return parents


def tmux_panes() -> dict[int, str]:
    """The pid of each pane's first process -> its pane id, in this tmux server."""
    if shutil.which("tmux") is None:
        return {}
    try:
        out = subprocess.run(
            ["tmux", "list-panes", "-a", "-F", "#{pane_pid} #{pane_id}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    panes = {}
    for line in out.splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[0].isdigit():
            panes[int(fields[0])] = fields[1]
    return panes


def pane_of(pid: int, parents: dict[int, int], panes: dict[int, str]) -> str | None:
    seen = set()
    while pid > 1 and pid not in seen:
        if pid in panes:
            return panes[pid]
        seen.add(pid)
        pid = parents.get(pid, 0)
    return None


def _same_process(pid: int, proc_start: object) -> bool:
    if not isinstance(proc_start, str) or not proc_start:
        return True
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return True  # no /proc (macOS) or it just exited: trust the process table
    # The command name (field 2) can hold spaces and parens, so split after it.
    fields = stat.rsplit(")", 1)[-1].split()
    # Field 22 overall (starttime) is index 19 after the pid and command name.
    return len(fields) > 19 and fields[19] == proc_start


def switch_to_pane_argv(pane: str) -> list[str]:
    """Bring `pane` to the front: its window, the pane itself, then its session."""
    return [
        "tmux", "select-window", "-t", pane, ";",
        "select-pane", "-t", pane, ";",
        "switch-client", "-t", pane,
    ]
