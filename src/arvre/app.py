"""Textual interface: session graph, filters, and the action modal."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList, Static
from textual.widgets.option_list import Option

from arvre.cache import ScanCache
from arvre.commands import (
    LAUNCH_TARGETS,
    fork_argv,
    new_session_argv,
    new_session_id,
    resume_argv,
    resume_command,
    tmux_argv,
    tmux_window_name,
)
from arvre.config import claude_env
from arvre.forks import link_forks
from arvre.graph_view import GraphView
from arvre.layout import build_rows, tree_members, visible_ids
from arvre.running import RunningSession, running_sessions, switch_to_pane_argv
from arvre.scanner import DEFAULT_ROOT, Session, discover
from arvre.state import ArvreState
from arvre.themes import THEME_ORDER, THEMES, Theme


LAUNCH_TARGET_PHRASES = {
    "here": "in this terminal",
    "window": "in a new tmux window",
    "pane": "in a new tmux pane",
}


# How often to look for running claude processes and for sessions started in tmux.
POLL_SECONDS = 3.0
# Stop waiting for a session started in tmux to show up after this long.
AWAIT_SECONDS = 30 * 60


def inside_tmux() -> bool:
    return bool(os.environ.get("TMUX")) and shutil.which("tmux") is not None


@dataclass
class AwaitedSession:
    """A fork or new session started in tmux, which arvre selects once it has messages."""

    session_id: str
    launched_from: str  # the selection at launch; only auto-select if it hasn't moved
    deadline: float
    file_size: int = -1


def open_label(running: RunningSession | None, in_tmux: bool, where: str) -> str:
    if running is None:
        return f"Open {where}"
    if running.tmux_pane and in_tmux:
        return f"Go to it (already running in tmux pane {running.tmux_pane})"
    return f"Already open in another terminal (pid {running.pid})"


class ActionModal(ModalScreen[str | None]):
    """Choose what to do with a session. Dismisses with the chosen action id,
    or None if closed without choosing."""

    BINDINGS = [Binding("escape", "close", "Close")]

    def __init__(
        self,
        session: Session,
        archived: bool,
        launch_target: str = "here",
        running: RunningSession | None = None,
        in_tmux: bool = False,
    ) -> None:
        super().__init__()
        self.session = session
        self.archived = archived
        self.launch_target = launch_target
        self.running = running
        self.in_tmux = in_tmux

    def compose(self) -> ComposeResult:
        where = LAUNCH_TARGET_PHRASES[self.launch_target]
        with Vertical(id="modal"):
            yield Label(Text(self.session.name, style="bold"), id="modal-title")
            yield Static(f"{self.session.id}\n{self.session.cwd}", id="modal-meta")
            yield OptionList(
                Option(open_label(self.running, self.in_tmux, where), id="open"),
                Option(f"Fork this session {where}", id="fork"),
                Option(f"New session in this directory {where}", id="new"),
                Option("Unarchive" if self.archived else "Archive", id="archive"),
                Option("Copy command", id="copy"),
                id="modal-actions",
            )
            yield Static(resume_command(self.session), id="modal-command")

    def on_mount(self) -> None:
        self.query_one(OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)

    def action_close(self) -> None:
        self.dismiss(None)


class ArvreApp(App):
    TITLE = "arvre"
    CSS = """
    #scroll { height: 1fr; }
    #detail { height: auto; max-height: 8; padding: 0 1; border-top: solid $accent; }
    #status { height: 1; padding: 0 1; }
    ActionModal { align: center middle; }
    #modal { width: 70; height: auto; border: thick $accent; background: $surface; padding: 1 2; }
    #modal-actions { height: auto; margin: 1 0; }
    #modal-meta, #modal-command { color: $text-muted; }
    """
    BINDINGS = [
        Binding("q,escape", "quit", "Quit"),
        Binding("r", "reload", "Reload"),
        Binding("a", "toggle_window", "24h / all"),
        Binding("p", "toggle_scope", "this dir / all"),
        Binding("v", "toggle_style", "compact / flow"),
        Binding("t", "toggle_theme", "theme"),
        Binding("f", "fork_selected", "fork"),
        Binding("n", "new_selected", "new"),
        Binding("x", "archive_selected", "archive"),
        Binding("z", "toggle_archived", "archived"),
        Binding("o", "cycle_launch_target", "open in"),
    ]

    def __init__(
        self,
        cwd: str,
        root: Path = DEFAULT_ROOT,
        window_24h: bool = True,
        all_projects: bool = True,
        style: str = "flow",
        theme: str = "classic",
        sessions: dict[str, Session] | None = None,
        cache: ScanCache | None = None,
        state: ArvreState | None = None,
        state_path: Path | None = None,
        show_archived: bool = False,
        claude_dir: Path | None = None,
        launch_target: str | None = None,
        in_tmux: bool | None = None,
        poll_seconds: float | None = POLL_SECONDS,
    ) -> None:
        super().__init__()
        self.state = state if state is not None else ArvreState()
        self.state_path = state_path
        self.in_tmux = inside_tmux() if in_tmux is None else in_tmux
        # An explicit choice (flag or $ARVRE_OPEN_IN) wins over the one saved by `o`.
        chosen = launch_target or self.state.launch_target or "here"
        if chosen not in LAUNCH_TARGETS:
            chosen = "here"
        # Outside tmux there's nowhere else to open, so stay in this terminal
        # (without overwriting the saved choice).
        self.launch_target = chosen if self.in_tmux else "here"
        self.poll_seconds = poll_seconds
        self.running: dict[str, RunningSession] = {}
        self.awaiting: AwaitedSession | None = None
        self.cwd = cwd
        self.root = root
        self.claude_dir = claude_dir
        self.window_24h = window_24h
        self.all_projects = all_projects
        self.style_name = style
        self.theme_name = theme
        self.show_archived = show_archived
        self.sessions: dict[str, Session] = {}
        self._cache = cache if cache is not None else ScanCache()
        self._initial_sessions = sessions

    @property
    def palette(self) -> Theme:
        return THEMES[self.theme_name]

    def compose(self) -> ComposeResult:
        with ScrollableContainer(id="scroll"):
            yield GraphView(id="graph")
        yield Static(id="detail")
        yield Static(id="status")

    def on_mount(self) -> None:
        self.running = self.fetch_running()
        if self._initial_sessions is not None:
            # Already scanned (with the loading indicator) before Textual
            # took the terminal; re-scanning here would just hit a warm cache,
            # but there's no reason to pay even that.
            self.sessions = self._initial_sessions
            link_forks(self.sessions)
            self.refresh_rows()
        else:
            self.load()
        self.state.mark_seen(set(self.sessions))
        self.state.save(self.state_path)
        self.query_one(GraphView).focus()
        if self.poll_seconds:
            self.set_interval(self.poll_seconds, self.poll)

    # --- data -------------------------------------------------------------

    def load(self) -> None:
        self.sessions = discover(self.root, self._cache)
        link_forks(self.sessions)
        self.refresh_rows()

    def refresh_rows(self) -> None:
        now = datetime.now(timezone.utc)
        visible = visible_ids(self.sessions, now, self.window_24h, self.all_projects, self.cwd)
        members = tree_members(self.sessions, visible)
        archived_ids = self.state.archived_ids()
        shown = members if self.show_archived else members - archived_ids
        rows = build_rows(self.sessions, shown, frozenset(archived_ids), frozenset(self.running))
        self.query_one(GraphView).set_data(self.sessions, rows, now, self.style_name, self.palette)
        hidden = 0 if self.show_archived else len(members & archived_ids)
        self.update_status(len(visible), hidden)

    def update_status(self, count: int, hidden_archived: int) -> None:
        accent = self.palette.accent
        scope = "all projects" if self.all_projects else "this dir"
        window = "24h" if self.window_24h else "all time"
        line = Text()
        for key, label in [
            ("a", window),
            ("p", scope),
            ("v", self.style_name),
            ("t", f"theme {self.theme_name}"),
            ("f", "fork"),
            ("n", "new"),
            ("x", "archive"),
            ("z", "archived shown" if self.show_archived else "archived hidden"),
            *([("o", f"open in {self.launch_target}")] if self.in_tmux else []),
        ]:
            line.append(f"{key} ", style=accent)
            line.append(f"{label}  ")
        line.append("r ", style=accent)
        line.append("reload  ")
        line.append("q/esc ", style=accent)
        line.append("quit  ")
        line.append(f"· {count} sessions")
        if hidden_archived:
            line.append(f"  · {hidden_archived} archived hidden")
        self.query_one("#status", Static).update(line)
        self.update_detail(self.query_one(GraphView).selected_id)

    def update_detail(self, sid: str | None) -> None:
        detail = self.query_one("#detail", Static)
        if sid is None:
            detail.update(Text("No sessions match the filters. Press a / p / z to widen them."))
            return
        theme = self.palette
        s = self.sessions[sid]
        parent = self.sessions[s.parent_id].name if s.parent_id else "none"
        children = ", ".join(self.sessions[c].name for c in s.child_ids) or "none"
        text = Text()
        text.append(s.name, style=theme.style("name"))
        if self.state.is_archived(sid):
            text.append("  (archived)", style=theme.style("meta"))
        running = self.running.get(sid)
        if running is not None:
            where = f"tmux pane {running.tmux_pane}" if running.tmux_pane else f"pid {running.pid}"
            status = f", {running.status}" if running.status else ""
            text.append(f"  (running in {where}{status})", style=theme.style("meta"))
        text.append(f"\nid {s.id}  ·  branch {s.branch or '-'}  ·  {s.cwd}", style=theme.style("meta"))
        text.append("\nparent: ", style=theme.style("meta"))
        text.append(parent)
        text.append("\nchildren: ", style=theme.style("meta"))
        text.append(children)
        detail.update(text)

    # --- events -------------------------------------------------------------

    def on_graph_view_highlighted(self, event: GraphView.Highlighted) -> None:
        self.update_detail(event.session_id)

    def on_graph_view_activated(self, event: GraphView.Activated) -> None:
        if event.session_id is None:
            return
        session = self.sessions[event.session_id]
        archived = self.state.is_archived(session.id)
        modal = ActionModal(session, archived, self.launch_target, self.running.get(session.id), self.in_tmux)
        self.push_screen(modal, callback=partial(self.run_choice, session))

    # --- actions ------------------------------------------------------------

    def action_reload(self) -> None:
        self.load()

    def action_toggle_window(self) -> None:
        self.window_24h = not self.window_24h
        self.refresh_rows()

    def action_toggle_scope(self) -> None:
        self.all_projects = not self.all_projects
        self.refresh_rows()

    def action_toggle_style(self) -> None:
        self.style_name = "flow" if self.style_name == "compact" else "compact"
        self.refresh_rows()

    def action_toggle_theme(self) -> None:
        self.theme_name = THEME_ORDER[(THEME_ORDER.index(self.theme_name) + 1) % len(THEME_ORDER)]
        self.refresh_rows()

    def action_toggle_archived(self) -> None:
        self.show_archived = not self.show_archived
        self.refresh_rows()

    def action_cycle_launch_target(self) -> None:
        if not self.in_tmux:
            self.notify("Not running inside tmux, so sessions open in this terminal.", severity="warning")
            return
        index = LAUNCH_TARGETS.index(self.launch_target)
        self.launch_target = LAUNCH_TARGETS[(index + 1) % len(LAUNCH_TARGETS)]
        self.state.launch_target = self.launch_target
        self.state.save(self.state_path)
        self.notify(f"Sessions now open {LAUNCH_TARGET_PHRASES[self.launch_target]}.")
        self.refresh_rows()

    def action_archive_selected(self) -> None:
        sid = self.query_one(GraphView).selected_id
        if sid is not None:
            self._toggle_archive(sid)

    def action_fork_selected(self) -> None:
        sid = self.query_one(GraphView).selected_id
        if sid is not None:
            self.fork_session(self.sessions[sid])

    def action_new_selected(self) -> None:
        sid = self.query_one(GraphView).selected_id
        if sid is not None:
            self.new_session(self.sessions[sid])

    def run_choice(self, session: Session, choice: str | None) -> None:
        if choice == "open":
            self.open_here(session)
        elif choice == "fork":
            self.fork_session(session)
        elif choice == "new":
            self.new_session(session)
        elif choice == "archive":
            self._toggle_archive(session.id)
        elif choice == "copy":
            self.copy_command(session)

    def _toggle_archive(self, sid: str) -> None:
        now_archived = self.state.toggle_archived(sid)
        self.state.save(self.state_path)
        self.notify(f"{'Archived' if now_archived else 'Unarchived'}: {self.sessions[sid].name}")
        self.refresh_rows()

    def _claude_available(self) -> bool:
        if shutil.which("claude"):
            return True
        self.notify("`claude` was not found on PATH.", severity="error")
        return False

    def _dir_exists(self, cwd: str) -> bool:
        if os.path.isdir(cwd):
            return True
        self.notify(f"Directory no longer exists: {cwd}", severity="error")
        return False

    def _run_claude(self, argv: list[str], cwd: str) -> None:
        # Its own method so tests can replace it without a real terminal to
        # suspend into (Textual's test driver doesn't support App.suspend()).
        with self.suspend():
            subprocess.run(argv, cwd=cwd, env=claude_env(self.claude_dir), check=False)

    def _run_tmux(self, argv: list[str]) -> bool:
        # Its own method so tests can replace it without a real tmux server.
        result = subprocess.run(argv, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            self.notify(f"tmux failed: {result.stderr.strip() or result.returncode}", severity="error")
            return False
        return True

    def _launch(self, argv: list[str], session: Session, name: str) -> str | None:
        """Run claude where the launch target says. Returns "here" once it has
        run in this terminal and exited, "tmux" once tmux has started it, or
        None if tmux failed."""
        if self.launch_target == "here":
            self._run_claude(argv, session.cwd)
            return "here"
        command = tmux_argv(self.launch_target, argv, session.cwd, tmux_window_name(name), self.claude_dir)
        return "tmux" if self._run_tmux(command) else None

    def open_here(self, session: Session) -> None:
        # Re-check rather than trust the last poll: a second claude on the same
        # session would interleave writes to one file.
        self.running = self.fetch_running()
        running = self.running.get(session.id)
        if running is not None:
            self._go_to_running(running)
            return
        if not (self._dir_exists(session.cwd) and self._claude_available()):
            return
        where = self._launch(resume_argv(session), session, session.name)
        if where == "here":
            self.load()
        elif where == "tmux":
            self.notify(f"Opened {LAUNCH_TARGET_PHRASES[self.launch_target]}.")
            self.refresh_rows()

    def _go_to_running(self, running: RunningSession) -> None:
        if running.tmux_pane and self.in_tmux:
            if self._run_tmux(switch_to_pane_argv(running.tmux_pane)):
                self.notify(f"Already running, so switched to tmux pane {running.tmux_pane}.")
            return
        self.notify(
            f"Already open in another terminal (pid {running.pid}), so not opening a second copy.",
            severity="warning",
        )

    def fork_session(self, session: Session) -> None:
        if not (self._dir_exists(session.cwd) and self._claude_available()):
            return
        new_id = new_session_id()
        self._after_start(new_id, session, self._launch(fork_argv(session, new_id), session, f"fork: {session.name}"))

    def new_session(self, session: Session) -> None:
        if not (self._dir_exists(session.cwd) and self._claude_available()):
            return
        new_id = new_session_id()
        name = "new: " + os.path.basename(session.cwd.rstrip("/"))
        self._after_start(new_id, session, self._launch(new_session_argv(new_id), session, name))

    def _after_start(self, new_id: str, origin: Session, where: str | None) -> None:
        if where == "here":
            self._reload_and_select(new_id)
        elif where == "tmux":
            self.awaiting = AwaitedSession(new_id, origin.id, time.monotonic() + AWAIT_SECONDS)
            self.notify(
                f"Started {LAUNCH_TARGET_PHRASES[self.launch_target]}. "
                "It will be selected here once it has messages."
            )

    # --- polling ------------------------------------------------------------

    def fetch_running(self) -> dict[str, RunningSession]:
        # The projects root is <claude dir>/projects, so this is <claude dir>.
        return running_sessions(self.root.parent, self.in_tmux)

    def poll(self) -> None:
        running = self.fetch_running()
        changed = {k: v.tmux_pane for k, v in running.items()} != {k: v.tmux_pane for k, v in self.running.items()}
        self.running = running
        if self.awaiting is not None and self.check_awaiting():
            return  # it reloaded, which redrew everything
        if changed:
            self.refresh_rows()

    def check_awaiting(self) -> bool:
        """Reload once the awaited session's file grows; select it once it has
        messages. Returns True if it reloaded."""
        awaited = self.awaiting
        if time.monotonic() > awaited.deadline:
            self.awaiting = None
            return False
        size = -1
        for path in self.root.glob(f"*/{awaited.session_id}.jsonl"):
            try:
                size = max(size, path.stat().st_size)
            except OSError:
                pass
        if size == awaited.file_size:
            return False
        awaited.file_size = size
        self.load()
        if awaited.session_id not in self.sessions:
            return True  # no messages yet: keep waiting
        self.awaiting = None
        graph = self.query_one(GraphView)
        if graph.selected_id == awaited.launched_from and graph.select_id(awaited.session_id):
            self.notify(f"New session: {self.sessions[awaited.session_id].name}")
        return True

    def _reload_and_select(self, session_id: str) -> None:
        self.load()
        if not self.query_one(GraphView).select_id(session_id):
            self.notify("The new session has no messages yet, so it isn't shown. Press r to check again later.")

    def copy_command(self, session: Session) -> None:
        command = resume_command(session, self.claude_dir)
        self.copy_to_clipboard(command)  # OSC 52: works over SSH and in most modern terminals
        clipboard = system_clipboard_command()
        if clipboard:
            subprocess.run(clipboard, input=command, text=True, check=False)
        self.notify(f"Copied: {command}")


def system_clipboard_command() -> list[str] | None:
    """A native clipboard tool for this platform, if one is installed."""
    if sys.platform == "darwin":
        return ["pbcopy"]
    candidates = [
        ["wl-copy"],
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
    ]
    for command in candidates:
        if shutil.which(command[0]):
            return command
    return None
