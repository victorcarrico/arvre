# arvre

A terminal graph of your Claude Code sessions and their forks.

`/resume` shows sessions as a flat list. `arvre` shows them as a tree, so you can see which session was forked from which, when each one was last used, and jump between parents and children.

Example output (sample names):

```
● Auth refactor  · 3h ago (2026-10-30 19:12)  · 2 children
├─ ● try the other approach  · 1h ago (2026-10-30 21:02)  · ↑ Auth refactor
└─ ● spike rename test  · 2m ago (2026-10-30 22:08)  · ↑ Auth refactor
```

## Install

With pipx (macOS and Linux, Python 3.11+):

```sh
pipx install git+https://github.com/victorcarrico/arvre
```

You need Claude Code installed, with `claude` on your `PATH`, for the "open in this terminal" action.

## Usage

```sh
arvre                      # sessions from the current directory, last 24 hours
arvre --all-time           # all sessions, not just the last 24 hours
arvre --all-projects       # sessions from every project
arvre --style flow         # start with the left-to-right flowchart
arvre --theme ocean        # start with a colour theme
arvre --print              # print the tree as text and exit
```

Run `arvre --help` for all options.

### Keys

| Key | Action |
| --- | --- |
| `↑` / `↓` (`k` / `j`) | Move. In compact style, through the tree. In flowchart style, to the next session at the same depth. |
| `←` / `→` (`h` / `l`) | Go to the parent / first child |
| `Enter` | Open the action menu for the selected session (or click it twice) |
| `a` | Toggle last 24 hours / all time |
| `p` | Toggle this directory / all projects |
| `v` | Toggle compact / flowchart style |
| `t` | Cycle colour themes (`classic`, `ocean`, `forest`, `sunset`) |
| `r` | Reload |
| `q` | Quit |

The action menu offers:

- **Open in this terminal**: runs `claude --resume <id>` in the session's directory, and returns to arvre when Claude exits.
- **Copy command**: copies `cd '<dir>' && claude --resume <id>` to the clipboard, for pasting into another terminal.

## How forks are detected

Claude Code doesn't record a parent link when you fork a session. A fork is a copy of its parent's messages, so arvre links each session to the earlier session that shares the most message IDs with it. The details are in [docs/forks.md](docs/forks.md).

Session data is read from `~/.claude/projects`. This is an undocumented format, so a future Claude Code release could change it.

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install -e ".[test]"
.venv/bin/python -m pytest
```

## License

MIT. See [LICENSE](LICENSE).
