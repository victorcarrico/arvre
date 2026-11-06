# arvre 0.3 — plan

## Context

arvre 0.2.1 works, but three things are missing or wrong:

1. **Startup is slow with many sessions.** Measured on a byte-faithful 300-session / 650 MB
   corpus built from real session files: **2778 ms**, of which `discover` is 99%. The cost is
   `json.loads` on every line of every file — not I/O (a raw read of all 650 MB takes 63 ms
   warm). `link_forks` (21 ms) and the flowchart layout (2 ms) are already fine.
2. **No way to branch from the view.** Forking or starting a session means leaving arvre.
3. **No way to retire a session.** Dead ends stay in the graph forever.

Also: the last-24h default was dropped in 0.2.0 and should come back.

Measurements come from `bench*.py` / `gen2.py` (scratchpad, session 15e749ac — copy them into
the repo if the numbers need re-checking at other scales).

## 1. Startup performance — persistent parse cache

Target: warm start **2778 ms → ~6 ms** (measured). Cold start stays serial; parallel parsing
was measured (2778 → ~500 ms with 8 processes) and **deliberately deferred** as unnecessary
complexity for a once-per-machine cost.

### Cache file

`$XDG_CACHE_HOME/arvre/scan-v1.json`, default `~/.cache/arvre/scan-v1.json`. Disposable: safe
to delete at any time, and deleting it must only cost one slow rebuild.

```json
{"version": 1,
 "sessions": {"<id>": {"mtime_ns": 0, "size": 0, "title_mtime_ns": 0,
                       "cwd": "", "name": "", "branch": "",
                       "first": "", "last": "", "created": 0.0,
                       "u": "4a7ee2bb791d1b8b38ffdf83…"}}}
```

`u` holds message uuids truncated to 12 chars and concatenated at fixed width, not a JSON
array of full uuids. Measured on the corpus:

| format | size | load | at 2000 sessions |
|---|---|---|---|
| full uuid arrays | 2.26 MB | 11.1 ms | 15 MB / 74 ms |
| **12-char concatenated** | **0.73 MB** | **1.2 ms** | **5 MB / 8 ms** |

Zero collisions across all 33 888 distinct uuids in the corpus; 12 hex chars ≈ 48 bits, so a
collision is negligible and would only nudge fork ranking, never crash. Keeping uuids in the
cache is what lets `link_forks` run from cache alone with no file reads.

### Invalidation

Key on `(mtime_ns, size)` — the same key `scanner.discover` already uses for its in-memory
cache; this persists it across runs. A changed file is reparsed **whole**; skip incremental
append reads (one active session costs ~10 ms, not worth the risk of assuming the file is
strictly append-only).

Also stat `<project>/<session-id>/custom-title.json` when it exists and include its mtime in
the key — see "Session title sidecar" below.

### Loading indicator

The cold scan stays serial and runs **before** `App.run()`:

```
cli.main → cache = ScanCache.load()
         → sessions = scan_with_progress(root, cache)
         → ArvreApp(sessions=sessions, cache=cache).run()
```

`scan_with_progress` runs a daemon thread that animates `building your arvre.` → `..` → `...`
on stderr via `\r` every ~250 ms while the main thread parses. Four details that matter:

- Start animating only after ~200 ms, so warm runs (~6 ms) stay silent.
- Animate only when `sys.stderr.isatty()` — keeps `--print | pipe`, tests and CI clean.
- Clear the line (`\r` + spaces + `\r`) before the TUI paints.
- Handle Ctrl-C during the scan without leaving a half-drawn line.

Unit-test the frame formatter, not the thread.

In-app `r` (reload) stays synchronous: with a warm cache only changed files reparse.

### Session title sidecar (found while spiking)

Claude Code also writes `<project>/<session-id>/custom-title.json`
(`{"customTitle": "Arvre-Improvements2"}`) alongside the `custom-title` record in the JSONL.
Both agree today, so arvre's current name resolution is correct — but it is a second source of
truth that could diverge.

Read the sidecar as the **highest-priority** name source when present, then fall back to the
existing chain (`custom-title` record → `ai-title` → `lastPrompt` → short id). It is a 37-byte
read and makes renames robust if a future Claude Code version stops writing the JSONL record.

No nested `.jsonl` files exist in these sidecar dirs, so the `*/*.jsonl` glob stays correct.

### Rejected

Regex field extraction instead of `json.loads`. Validated byte-exact against `json.loads` on
all 9 real session files and ~2x faster, but nested content blocks mean it is not *guaranteed*
correct, and the cache makes the speedup irrelevant.

## 2. `f` fork and `n` new session

Both reuse the `suspend()` + `subprocess.run` mechanism `open_here` already proves works.

**Spike result (verified, session 15e749ac):** `claude --resume <parent> --fork-session
--session-id <new>` works — exit 0, the fork file lands at exactly the requested id, carries
the parent's history, shares all the parent's message uuids, and the existing `link_forks`
links it correctly (`parent_id` = parent). So arvre can generate the uuid up front and select
the new node on return; **no after-the-fact diffing of session ids is needed**, and
`link_forks` needs no changes.

- **`f`** → `claude --resume <id> --fork-session --session-id <fresh-uuid>`, run in that
  session's `cwd`. arvre nodes are whole sessions, so this forks from the node's tip.
- **`n`** → `claude --session-id <fresh-uuid>`, run in **the selected node's project dir**, so
  it behaves the same wherever arvre was launched.

Build both as argument lists in `commands.py` beside `resume_command` so they unit-test without
spawning anything.

### Fork name inheritance

The spike showed a parent and its fork both displaying as `'say A'`: a fork inherits the
parent's name until Claude generates its own title. With `f` one keystroke away, identically
labelled sibling boxes become routine.

Fix in the display: when a node's name equals its parent's, append a dim `⑂` marker in
`row_segments`. Do **not** pass `--name` on fork — that writes a `custom-title`, which outranks
`ai-title`, so the forced label would stick permanently and suppress the better name Claude
generates later. (Claude Code does this itself in `aiTitle`: `build-arvre-session-graph ⑂ ⑂`.)

A "name this fork" input is a reasonable extra later; out of scope here.

### Gotchas

- A session opened and quit without a prompt leaves no message records, so the scanner skips it
  and no node appears. Notify rather than leaving the user guessing.
- Guard both actions with `shutil.which("claude")`.

## 3. Archive + state file

Archive only. **No delete** — arvre never writes to or removes anything under `~/.claude`.

### Storage

`$XDG_DATA_HOME/arvre/state.json`, default `~/.local/share/arvre/state.json` — separate from
the cache, because losing the cache is harmless and losing archive flags is annoying.

```json
{"version": 1,
 "sessions": {"<id>": {"archived_at": "2026-11-06T…Z", "last_seen": "2026-11-06T…Z"}}}
```

Per-session dicts so tags, notes or a pinned flag drop in later without a migration.

Rules: never write inside `~/.claude`; write atomically (temp file + `os.replace`); treat a
missing file as empty and move a corrupt one aside as `state.json.corrupt-<ts>` rather than
crashing or silently discarding; store **only ids and flags, never message content**.

Performance is a non-issue: 300 entries without uuids loaded in **under 1 ms**.

### Tree semantics — node only

Filtering order matters, because `tree_members` pulls in a whole family when any member
matches, so archived nodes must be removed *after* it:

```
visible = visible_ids(...)                  # time + scope filters
shown   = tree_members(visible) − archived  # unless "show archived" is on
```

`build_rows` then needs an **effective parent**: walk up to the nearest ancestor still in
`shown`. Today orphans become roots, which would flatten the tree whenever a middle node is
archived; reconnecting keeps children nested under the grandparent. Small change in `layout.py`.

### Pruning

Refresh `last_seen` on every *full successful* scan and drop entries unseen for 90+ days. Never
prune after a partial or failed scan, or a temporarily-missing project dir silently loses flags.

With two arvre instances open, re-read state immediately before each toggle write — cheap, and
avoids lost updates without real locking.

## 4. Default back to last-24h

`cli.py` flips to `window_24h=True`; `--all-time` replaces `--last-day`. All-projects and flow
stay as they are. **This breaks `test_defaults_are_flow_all_projects_all_time`**, which asserts
`window_24h is False` — rename and update it.

## Keys

`f`, `n`, `x`, `z` are all free (`q r a p v t` and `h j k l` are taken).

| key | action |
|---|---|
| `f` | fork the selected session |
| `n` | new session in the selected node's project dir |
| `x` | archive / unarchive selected |
| `z` | show / hide archived |

Show `archived hidden: N` in the status line so a vanished session is never a mystery. Add fork,
new and archive to `ActionModal` as well as the keys.

## Files

| file | change |
|---|---|
| `src/arvre/cache.py` | **new** — `ScanCache` load/save, `(mtime_ns, size)` keys, compact uuid encoding |
| `src/arvre/state.py` | **new** — `ArvreState`, XDG paths, atomic write, archive toggle, pruning |
| `src/arvre/scanner.py` | accept a `ScanCache`; read the title sidecar; add `scan_with_progress` |
| `src/arvre/layout.py` | subtract archived from `shown`; effective-parent reconnection; `⑂` duplicate-name marker |
| `src/arvre/commands.py` | `fork_command`, `new_session_command` |
| `src/arvre/app.py` | `f`/`n`/`x`/`z` bindings, modal entries, status-line archived count |
| `src/arvre/cli.py` | pre-TUI scan with indicator; `--all-time` replaces `--last-day`; `--no-cache` escape hatch |
| `tests/` | cache round-trip + invalidation, archive hiding + reconnection, command building, indicator frames, updated defaults test |

## Verification

- **Unit:** cache round-trips and invalidates on both mtime and size change; archiving a middle
  node keeps grandchildren nested; `fork_command` / `new_session_command` produce the right
  argv (assert the list, don't spawn); sidecar title outranks the JSONL record.
- **Perf:** rebuild a corpus with `gen2.py <dir> 300 2`, then time a cold scan followed by a
  warm one, asserting warm is under ~50 ms for 300 sessions.
- **Manual:** `f` on a node produces a child node after exit, distinguishable by the `⑂` marker;
  `n` starts in the right project; `x` hides a node while its forks stay nested; `z` brings it
  back; deleting `~/.cache/arvre/` shows the indicator again and rebuilds an identical graph.

## Open items

- Corpus is synthetic (9 real sessions replicated), so cold-scan time at your real scale is an
  extrapolation. The warm path does not depend on that.
- Parallel cold scan is measured and available (~500 ms for 300 sessions) if the first run
  proves annoying in practice.
