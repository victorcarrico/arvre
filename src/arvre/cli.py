"""Command-line entry point for arvre."""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone

from arvre.app import ArvreApp
from arvre.forks import link_forks
from arvre.layout import build_rows, row_label, tree_members, visible_ids
from arvre.scanner import DEFAULT_ROOT, discover
from arvre.themes import THEMES


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="arvre",
        description="Show Claude Code sessions and their forks as a graph.",
    )
    parser.add_argument("--dir", default=os.getcwd(), help="project directory to show (default: current)")
    parser.add_argument("--this-dir", action="store_true", help="start with only the current directory's sessions")
    parser.add_argument("--last-day", action="store_true", help="start with only sessions from the last 24 hours")
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
    parser.add_argument("--print", dest="print_only", action="store_true", help="print the graph as text and exit")
    args = parser.parse_args(argv)

    cwd = os.path.realpath(args.dir)
    if args.print_only:
        print_graph(cwd, args)
        return
    ArvreApp(
        cwd=cwd,
        root=DEFAULT_ROOT,
        window_24h=args.last_day,
        all_projects=not args.this_dir,
        style=args.style,
        theme=args.theme,
    ).run()


def print_graph(cwd: str, args: argparse.Namespace) -> None:
    now = datetime.now(timezone.utc)
    sessions = discover(DEFAULT_ROOT)
    link_forks(sessions)
    visible = visible_ids(sessions, now, args.last_day, not args.this_dir, cwd)
    for row in build_rows(sessions, tree_members(sessions, visible)):
        print(row_label(row, sessions, now))


if __name__ == "__main__":
    main()
