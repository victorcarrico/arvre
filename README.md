# arvre

A terminal graph of your Claude Code sessions and their forks.

`arvre` shows your Claude Code sessions and their forks as a tree. Navigate through them, resume sessions, see which session was forked from which,  and jump between parents and children.

Example output (sample names, flowchart style):

```
                                  ┌──────────────────────────┐
                               ┌──│ Spike rename test        │
┌──────────────────────────┐   │  │ 1m ago · no children     │
│ Auth refactor            │───┤  └──────────────────────────┘
│ 3h ago · 2 children      │   │
└──────────────────────────┘   │  ┌──────────────────────────┐      ┌──────────────────────────┐
                               └──│ Try the other approach   │──────│ Fix token refresh        │
                                  │ 1h ago · 1 child         │      │ 30m ago · no children    │
                                  └──────────────────────────┘      └──────────────────────────┘
```

## Install

With pipx (macOS and Linux, Python 3.11+):

```sh
pipx install arvre
```

You need Claude Code installed, with `claude` on your `PATH`, for the "open in this terminal" action.

## Usage

```sh
arvre                      # last 24h, every project, as a flowchart
arvre --this-dir           # only sessions from the current directory
arvre --all-time           # every session, not only the last 24 hours
arvre --style compact      # start with the compact tree instead
arvre --theme ocean        # start with a colour theme
arvre --show-archived      # start with archived sessions visible too
arvre --print              # print the tree as text and exit
```

Run `arvre --help` for all options.

### Keys

| Key | Action |
| --- | --- |
| `↑` / `↓` (`k` / `j`) | Move. In compact style, through the tree. In flowchart style, to the next session at the same depth. |
| `←` / `→` (`h` / `l`) | Go to the parent / first child |
| `Enter` | Open the action menu for the selected session (or click it twice) |
| `f` | Fork the selected session |
| `n` | Start a new session in the selected session's directory |
| `x` | Archive / unarchive the selected session (hides it from the graph; never touches the session file itself) |
| `z` | Toggle whether archived sessions are shown |
| `a` | Toggle last 24 hours / all time |
| `p` | Toggle this directory / all projects |
| `v` | Toggle compact / flowchart style |
| `t` | Cycle colour themes (`classic`, `ocean`, `forest`, `sunset`) |
| `r` | Reload |
| `q` | Quit |

The action menu offers the same actions as the keys above, plus:

- **Open in this terminal**: runs `claude --resume <id>` in the session's directory, and returns to arvre when Claude exits.
- **Copy command**: copies `cd '<dir>' && claude --resume <id>` to the clipboard, for pasting into another terminal.

## How forks are detected

Claude Code doesn't record a parent link when you fork a session. A fork is a copy of its parent's messages, so arvre links each session to the earlier session that shares the most message IDs with it. The details, including the verified behavior of `f` (fork) and `n` (new session), are in [docs/forks.md](docs/forks.md) and [docs/plan-0.3.md](docs/plan-0.3.md).

Session data is read from `~/.claude/projects`. This is an undocumented format, so a future Claude Code release could change it.

## Performance

A cold start parses every session file once; a warm start (most runs) skips any file whose size and modified time haven't changed since the last scan, via a cache at `~/.cache/arvre/` (override with `$XDG_CACHE_HOME`, or skip it entirely with `--no-cache`). On a 300-session / 650 MB corpus this took a cold scan from ~3s to a warm one of ~30ms. If a scan is slow, arvre prints an animated `building your arvre...` to the terminal instead of a blank screen.

The cache is purely disposable: deleting `~/.cache/arvre/` just costs one slow rescan, never any data loss.

## Archiving

Archiving a session (`x`) hides it from the graph without touching the session file in `~/.claude`. Its forks stay visible and reconnect to the nearest ancestor still shown. The flag lives separately, at `~/.local/share/arvre/state.json` (override with `$XDG_DATA_HOME`), since losing it would be more annoying than losing the cache. There's no way to delete a session from arvre -- only to hide it.

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install -e ".[test]"
.venv/bin/python -m pytest
```

## License

MIT. See [LICENSE](LICENSE).
