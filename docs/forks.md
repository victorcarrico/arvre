# How Claude Code records forks (Phase 0 findings)

Verified with Claude Code 2.1.314 by creating sessions in a scratch project.

## Session files
- Path: `~/.claude/projects/<cwd with "/" replaced by "-">/<sessionId>.jsonl`.
- Each line is a JSON record with a `type` and usually a `sessionId`.

## Forks (`claude --resume <id> --fork-session`)
- No explicit parent field is written (`forkedFrom`, `parentSessionId`, etc. are absent).
- The fork file is a **copy of the parent's records** with the same message `uuid`s, with `sessionId` rewritten to the new id. In the test, 15 of the fork's 20 uuid-bearing records were copied from the parent; the 5 others are new turns.
- Parent detection therefore relies on shared `uuid`s.

## Rule used by `forks.py`
For each session X with first timestamp `t(X)`:
- Candidates are sessions Y where `first(Y) < first(X)` and `uuids(Y) ∩ uuids(X) ≠ ∅`.
- Parent = candidate with the largest intersection. Ties go to the earliest `first(Y)`.
- Sessions with no candidate are roots.

Verified on the scratch data: fork `1367693d` → parent `45aba1c5` (15 shared uuids); the unrelated named session has no parent.

**Known limitation:** siblings forked from the same parent share the parent's prefix, so the rule links each sibling to the parent (not to each other). This is the desired result. Siblings are not linked to each other.

## Names (display title, in priority order)
1. `custom-title` (`customTitle`), written by `--name` and `/rename`. The latest record wins.
2. `ai-title` (`aiTitle`), auto-generated after several turns (not present in short sessions).
3. First line of `last-prompt` (`lastPrompt`).
4. Short session id.

`agent-name` mirrors `custom-title` and is not used separately.

## Last interaction
- Use the `timestamp` of the last `user` or `assistant` record. File mtime is not reliable because metadata records are appended without user activity.

## Not yet verified
- `/branch` and the interactive `/rename` paths were not run (non-interactive mode only). Expect the same record shape; confirm in the scanner tests against a real `/branch` session before relying on it.
- Whether `/resume` hides empty sessions and sidechain files. To check against `/resume` output in milestone 3.
