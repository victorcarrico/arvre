"""Command-line entry point for arvre."""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

from arvre import __version__
from arvre.app import ArvreApp
from arvre.cache import ScanCache
from arvre.commands import LAUNCH_TARGETS
from arvre.config import projects_root, resolve_claude_dir
from arvre.forks import link_forks
from arvre.layout import build_rows, row_label, tree_members, visible_ids
from arvre.progress import scan_with_progress
from arvre.state import ArvreState
from arvre.themes import THEMES


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="arvre",
        description="Show Claude Code sessions and their forks as a graph.",
    )
    parser.add_argument("--version", action="version", version=f"arvre {__version__}")
    parser.add_argument("--dir", default=os.getcwd(), help="project directory to show (default: current)")
    parser.add_argument("--this-dir", action="store_true", help="start with only the current directory's sessions")
    parser.add_argument(
        "--all-time", action="store_true", help="start with sessions from any time, not only the last 24 hours"
    )
    parser.add_argument(
        "--style",
        choices=["compact", "flow"],
        default="flow",
        help="tree style to start with (default: flow)",
    )
    parser.add_argument(
        "--theme",
        choices=list(THEMES),
        default="classic",
        help="colour theme to start with (default: classic); press t to cycle",
    )
    parser.add_argument("--show-archived", action="store_true", help="start with archived sessions visible")
    parser.add_argument(
        "--no-cache", action="store_true", help="ignore the on-disk parse cache and don't update it"
    )
    parser.add_argument(
        "--claude-dir",
        metavar="PATH",
        help="Claude Code config directory to read sessions from (default: $ARVRE_CLAUDE_DIR, "
        "then $CLAUDE_CONFIG_DIR, then ~/.claude)",
    )
    parser.add_argument(
        "--open-in",
        choices=list(LAUNCH_TARGETS),
        default=os.environ.get("ARVRE_OPEN_IN") or None,
        help="where open / fork / new start claude: this terminal, a new tmux window, or a new tmux pane "
        "(default: $ARVRE_OPEN_IN, then the last choice made with o, then here). "
        "window and pane need arvre to run inside tmux",
    )
    parser.add_argument("--print", dest="print_only", action="store_true", help="print the graph as text and exit")
    args = parser.parse_args(argv)
    if args.open_in is not None and args.open_in not in LAUNCH_TARGETS:
        parser.error(f"ARVRE_OPEN_IN must be one of {', '.join(LAUNCH_TARGETS)}, not {args.open_in!r}")

    cwd = os.path.realpath(args.dir)
    claude_dir = resolve_claude_dir(args.claude_dir)
    root = projects_root(claude_dir)
    if not root.is_dir():
        parser.error(f"no Claude Code sessions found: {root} is not a directory (set --claude-dir)")
    cache = ScanCache() if args.no_cache else ScanCache.load()

    if args.print_only:
        print_graph(cwd, args, cache, root)
        return

    # Scanned (with a loading indicator if it's slow) before Textual takes
    # the terminal -- see arvre.progress.
    sessions = scan_with_progress(root, cache)
    link_forks(sessions)
    state = ArvreState.load()
    try:
        ArvreApp(
            cwd=cwd,
            root=root,
            claude_dir=claude_dir,
            window_24h=not args.all_time,
            all_projects=not args.this_dir,
            style=args.style,
            theme=args.theme,
            sessions=sessions,
            cache=cache,
            state=state,
            show_archived=args.show_archived,
            launch_target=args.open_in,
        ).run()
    finally:
        if not args.no_cache:
            cache.save()
        state.save()


def print_graph(cwd: str, args: argparse.Namespace, cache: ScanCache, root: Path) -> None:
    now = datetime.now(timezone.utc)
    sessions = scan_with_progress(root, cache)
    link_forks(sessions)
    state = ArvreState.load()
    archived_ids = state.archived_ids()
    visible = visible_ids(sessions, now, not args.all_time, not args.this_dir, cwd)
    members = tree_members(sessions, visible)
    shown = members if args.show_archived else members - archived_ids
    for row in build_rows(sessions, shown, frozenset(archived_ids)):
        print(row_label(row, sessions, now))
    if not args.no_cache:
        cache.save()


if __name__ == "__main__":
    main()
