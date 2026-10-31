"""Textual interface: session graph, filters, and the action modal."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
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

from arvre.commands import resume_command
from arvre.forks import link_forks
from arvre.graph_view import GraphView
from arvre.layout import build_rows, tree_members, visible_ids
from arvre.scanner import DEFAULT_ROOT, Session, discover
from arvre.themes import THEME_ORDER, THEMES, Theme


class ActionModal(ModalScreen[str | None]):
    """Choose what to do with a session. Dismisses with "open", "copy" or None."""

    BINDINGS = [Binding("escape", "close", "Close")]

    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session

    def compose(self) -> ComposeResult:
        with Vertical(id="modal"):
            yield Label(Text(self.session.name, style="bold"), id="modal-title")
            yield Static(f"{self.session.id}\n{self.session.cwd}", id="modal-meta")
            yield OptionList(
                Option("Open in this terminal", id="open"),
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
        Binding("q", "quit", "Quit"),
        Binding("r", "reload", "Reload"),
        Binding("a", "toggle_window", "24h / all"),
        Binding("p", "toggle_scope", "this dir / all"),
        Binding("v", "toggle_style", "compact / flow"),
        Binding("t", "toggle_theme", "theme"),
    ]

    def __init__(
        self,
        cwd: str,
        root: Path = DEFAULT_ROOT,
        window_24h: bool = True,
        all_projects: bool = False,
        style: str = "compact",
        theme: str = "classic",
    ) -> None:
        super().__init__()
        self.cwd = cwd
        self.root = root
        self.window_24h = window_24h
        self.all_projects = all_projects
        self.style_name = style
        self.theme_name = theme
        self.sessions: dict[str, Session] = {}
        self._cache: dict = {}

    @property
    def palette(self) -> Theme:
        return THEMES[self.theme_name]

    def compose(self) -> ComposeResult:
        with ScrollableContainer(id="scroll"):
            yield GraphView(id="graph")
        yield Static(id="detail")
        yield Static(id="status")

    def on_mount(self) -> None:
        self.load()
        self.query_one(GraphView).focus()

    # --- data -------------------------------------------------------------

    def load(self) -> None:
        self.sessions = discover(self.root, self._cache)
        link_forks(self.sessions)
        self.refresh_rows()

    def refresh_rows(self) -> None:
        now = datetime.now(timezone.utc)
        visible = visible_ids(self.sessions, now, self.window_24h, self.all_projects, self.cwd)
        rows = build_rows(self.sessions, tree_members(self.sessions, visible))
        self.query_one(GraphView).set_data(self.sessions, rows, now, self.style_name, self.palette)
        self.update_status(len(visible))

    def update_status(self, count: int) -> None:
        accent = self.palette.accent
        scope = "all projects" if self.all_projects else "this dir"
        window = "24h" if self.window_24h else "all time"
        line = Text()
        for key, label in [
            ("a", window),
            ("p", scope),
            ("v", self.style_name),
            ("t", f"theme {self.theme_name}"),
        ]:
            line.append(f"{key} ", style=accent)
            line.append(f"{label}  ")
        line.append("r ", style=accent)
        line.append("reload  ")
        line.append("q ", style=accent)
        line.append("quit  ")
        line.append(f"· {count} sessions")
        self.query_one("#status", Static).update(line)
        self.update_detail(self.query_one(GraphView).selected_id)

    def update_detail(self, sid: str | None) -> None:
        detail = self.query_one("#detail", Static)
        if sid is None:
            detail.update(Text("No sessions match the filters. Press a / p to widen them."))
            return
        theme = self.palette
        s = self.sessions[sid]
        parent = self.sessions[s.parent_id].name if s.parent_id else "none"
        children = ", ".join(self.sessions[c].name for c in s.child_ids) or "none"
        text = Text()
        text.append(s.name, style=theme.style("name"))
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
        self.push_screen(ActionModal(session), callback=partial(self.run_choice, session))

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

    def run_choice(self, session: Session, choice: str | None) -> None:
        if choice == "open":
            self.open_here(session)
        elif choice == "copy":
            self.copy_command(session)

    def open_here(self, session: Session) -> None:
        if not os.path.isdir(session.cwd):
            self.notify(f"Directory no longer exists: {session.cwd}", severity="error")
            return
        try:
            with self.suspend():
                subprocess.run(["claude", "--resume", session.id], cwd=session.cwd, check=False)
        except FileNotFoundError:
            self.notify("`claude` was not found on PATH.", severity="error")
            return
        self.load()

    def copy_command(self, session: Session) -> None:
        command = resume_command(session)
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
