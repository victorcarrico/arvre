from datetime import timedelta

from conftest import CWD, NOW, message, write_session

from arvre.commands import resume_command
from arvre.flowchart import BOX_H, BOX_W, flow_layout
from arvre.forks import link_forks
from arvre.layout import build_rows, format_age, row_label, tree_members, visible_ids
from arvre.scanner import Session, discover

ROOT = "aaaaaaaa-0000-0000-0000-000000000001"
FORK = "aaaaaaaa-0000-0000-0000-000000000002"
OTHER = "aaaaaaaa-0000-0000-0000-000000000003"


def load(projects_root):
    sessions = discover(projects_root)
    link_forks(sessions)
    return sessions


def test_discover_skips_empty_sessions_and_reads_names(projects_root):
    sessions = load(projects_root)
    assert set(sessions) == {ROOT, FORK, OTHER}
    assert sessions[ROOT].name == "Auth refactor"  # custom title wins
    assert sessions[FORK].name == "try the other approach"  # last prompt fallback
    assert sessions[OTHER].name == OTHER[:8]  # no title at all


def test_last_interaction_uses_message_timestamps(projects_root):
    sessions = load(projects_root)
    assert abs((NOW - sessions[FORK].last_ts).total_seconds() - 3600) < 5


def test_fork_is_linked_to_parent(projects_root):
    sessions = load(projects_root)
    assert sessions[FORK].parent_id == ROOT
    assert sessions[ROOT].child_ids == [FORK]
    assert sessions[OTHER].parent_id is None


def test_fork_of_fork_chains_to_nearest_ancestor(projects_root):
    fork2 = "aaaaaaaa-0000-0000-0000-000000000009"
    fork_msgs = [message("u1", 3.2), message("u2", 3.1, kind="assistant"), message("u3", 1.0), message("u9", 0.5)]
    write_session(projects_root, fork2, fork_msgs)
    sessions = load(projects_root)
    assert sessions[fork2].parent_id == FORK


def test_visible_window_and_scope(projects_root):
    sessions = load(projects_root)
    assert visible_ids(sessions, NOW, True, False, CWD) == {ROOT, FORK}
    assert visible_ids(sessions, NOW, False, False, CWD) == {ROOT, FORK, OTHER}
    assert visible_ids(sessions, NOW, True, False, "/elsewhere") == set()
    assert visible_ids(sessions, NOW, True, True, "/elsewhere") == {ROOT, FORK}


def test_full_tree_shown_when_one_member_matches(projects_root):
    sessions = load(projects_root)
    # Only the fork matches the filters, but its parent is part of the same tree.
    members = tree_members(sessions, {FORK})
    assert members == {ROOT, FORK}
    rows = build_rows(sessions, members)
    assert [r.session.id for r in rows] == [ROOT, FORK]
    assert rows[1].prefix == "└─ "


def test_trees_without_matches_are_hidden(projects_root):
    sessions = load(projects_root)
    assert tree_members(sessions, {FORK}) == {ROOT, FORK}
    assert OTHER not in tree_members(sessions, {FORK})


def test_tree_connectors_and_sorting(projects_root):
    sessions = load(projects_root)
    fork2 = "aaaaaaaa-0000-0000-0000-000000000009"
    write_session(projects_root, fork2, [message("u1", 3.2), message("u2", 3.1, kind="assistant"), message("u8", 0.2)])
    sessions = load(projects_root)
    rows = build_rows(sessions, {ROOT, FORK, fork2})
    assert [r.session.id for r in rows] == [ROOT, fork2, FORK]  # newest child first
    assert rows[1].prefix == "├─ "
    assert rows[2].prefix == "└─ "


def test_row_label_mentions_parent_and_children(projects_root):
    sessions = load(projects_root)
    rows = build_rows(sessions, {ROOT, FORK})
    root_label = row_label(rows[0], sessions, NOW)
    assert "Auth refactor" in root_label and "1 child" in root_label
    fork_label = row_label(rows[1], sessions, NOW)
    assert "↑ Auth refactor" in fork_label


def test_flow_layout_places_children_to_the_right(projects_root):
    sessions = load(projects_root)
    fork2 = "aaaaaaaa-0000-0000-0000-000000000009"
    write_session(projects_root, fork2, [message("u1", 3.2), message("u2", 3.1, kind="assistant"), message("u8", 0.2)])
    sessions = load(projects_root)
    layout = flow_layout(build_rows(sessions, {ROOT, FORK, fork2}))
    root, fork, sibling = layout.boxes[ROOT], layout.boxes[FORK], layout.boxes[fork2]
    assert fork.x > root.x and sibling.x == fork.x
    # The parent is centred between its two children.
    assert min(fork.y, sibling.y) <= root.y <= max(fork.y, sibling.y)
    assert layout.width == fork.x + BOX_W
    assert layout.height >= sibling.y + BOX_H


def test_format_age():
    assert format_age(NOW, NOW - timedelta(seconds=30)) == "just now"
    assert format_age(NOW, NOW - timedelta(minutes=5)) == "5m ago"
    assert format_age(NOW, NOW - timedelta(hours=2)) == "2h ago"
    assert format_age(NOW, NOW - timedelta(days=3)) == "3d ago"


def test_resume_command_quotes_directory():
    s = Session(
        id="abc",
        path=None,
        cwd="/Users/me/my project",
        name="x",
        first_ts=NOW,
        last_ts=NOW,
        branch="",
        created=0,
        uuids=frozenset(),
    )
    assert resume_command(s) == "cd '/Users/me/my project' && claude --resume abc"
