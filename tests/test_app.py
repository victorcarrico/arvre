import pytest
from textual.widgets import OptionList, Static

from arvre.app import ActionModal, ArvreApp
from arvre.graph_view import GraphView

from conftest import CWD, message, write_session

ROOT = "aaaaaaaa-0000-0000-0000-000000000001"
FORK = "aaaaaaaa-0000-0000-0000-000000000002"
OTHER = "aaaaaaaa-0000-0000-0000-000000000003"


def make_app(projects_root, **kwargs):
    # The tests start from the compact, last-24h, this-dir view unless they say otherwise.
    kwargs.setdefault("window_24h", True)
    kwargs.setdefault("all_projects", False)
    kwargs.setdefault("style", "compact")
    # Isolates any archive-state write a test triggers to this run's tmp_path,
    # never the real ~/.local/share/arvre/state.json.
    kwargs.setdefault("state_path", projects_root / "state.json")
    return ArvreApp(cwd=CWD, root=projects_root, **kwargs)


def graph_ids(app):
    return [row.session.id for row in app.query_one(GraphView).rows]


@pytest.mark.asyncio
async def test_default_view_shows_recent_sessions_of_this_dir(projects_root):
    app = make_app(projects_root)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert graph_ids(app) == [ROOT, FORK]
        assert app.query_one(GraphView).style_name == "compact"


@pytest.mark.asyncio
async def test_toggle_window_shows_older_sessions(projects_root):
    app = make_app(projects_root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        assert set(graph_ids(app)) == {ROOT, FORK, OTHER}


@pytest.mark.asyncio
async def test_keyboard_jump_to_parent_and_child(projects_root):
    app = make_app(projects_root)
    async with app.run_test() as pilot:
        await pilot.pause()
        graph = app.query_one(GraphView)
        graph.select_id(FORK)
        await pilot.pause()
        await pilot.press("h")
        await pilot.pause()
        assert graph.selected_id == ROOT
        await pilot.press("l")
        await pilot.pause()
        assert graph.selected_id == FORK


@pytest.mark.asyncio
async def test_style_toggle_switches_to_flowchart(projects_root):
    app = make_app(projects_root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("v")
        await pilot.pause()
        graph = app.query_one(GraphView)
        assert graph.style_name == "flow"
        drawn = graph.plain_text()
        assert "Auth refactor" in drawn
        assert "┐" in drawn or "└" in drawn


@pytest.mark.asyncio
async def test_enter_opens_action_modal_and_escape_closes(projects_root):
    app = make_app(projects_root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, ActionModal)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, ActionModal)


@pytest.mark.asyncio
async def test_toggle_theme_cycles_palettes(projects_root):
    app = make_app(projects_root)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.theme_name == "classic"
        await pilot.press("t")
        await pilot.pause()
        assert app.theme_name == "ocean"
        assert app.query_one(GraphView).theme.name == "ocean"


@pytest.mark.asyncio
async def test_flow_up_down_moves_within_the_same_level(projects_root):
    app = make_app(projects_root, style="flow")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")  # all time: OTHER becomes a second top-level session
        await pilot.pause()
        graph = app.query_one(GraphView)
        graph.select_id(ROOT)
        await pilot.press("down")
        await pilot.pause()
        assert graph.selected_id == OTHER  # the next top-level session, not ROOT's child
        await pilot.press("up")
        await pilot.pause()
        assert graph.selected_id == ROOT


@pytest.mark.asyncio
async def test_click_selects_row_and_click_again_opens_modal(projects_root):
    app = make_app(projects_root)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click(GraphView, offset=(2, 1))  # second row: the fork
        await pilot.pause()
        assert app.query_one(GraphView).selected_id == FORK
        await pilot.click(GraphView, offset=(2, 1))
        await pilot.pause()
        assert isinstance(app.screen, ActionModal)


@pytest.mark.asyncio
async def test_click_on_flowchart_box_selects_it(projects_root):
    app = make_app(projects_root, style="flow")
    async with app.run_test() as pilot:
        await pilot.pause()
        graph = app.query_one(GraphView)
        box = graph._flow.boxes[FORK]
        await pilot.click(GraphView, offset=(box.x + 3, box.y + 1))
        await pilot.pause()
        assert graph.selected_id == FORK


@pytest.mark.asyncio
async def test_defaults_are_flow_all_projects_last_24h(projects_root):
    app = ArvreApp(cwd=CWD, root=projects_root, state_path=projects_root / "state.json")
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.style_name == "flow"
        assert app.all_projects is True
        assert app.window_24h is True
        # OTHER is 30h old and unrelated to ROOT/FORK's tree, so the 24h
        # default -- restored in 0.3 -- excludes it even with all projects on.
        assert set(graph_ids(app)) == {ROOT, FORK}


@pytest.mark.asyncio
async def test_fork_action_runs_the_right_argv_and_selects_the_result(projects_root, monkeypatch):
    app = make_app(projects_root)
    calls = []
    created_ids = []

    def fake_run(argv, cwd):
        calls.append((argv, cwd))
        new_id = argv[argv.index("--session-id") + 1]
        created_ids.append(new_id)
        write_session(projects_root, new_id, [message("nf1", 0.0), message("nf2", 0.0, kind="assistant")])

    async with app.run_test() as pilot:
        await pilot.pause()
        monkeypatch.setattr(app, "_run_claude", fake_run)
        # The fixture's CWD ("/Users/me/project") is synthetic and doesn't
        # exist on the machine running the tests; only _run_claude is faked.
        monkeypatch.setattr(app, "_dir_exists", lambda cwd: True)
        monkeypatch.setattr(app, "_claude_available", lambda: True)  # CI runners don't have claude installed
        graph = app.query_one(GraphView)
        graph.select_id(ROOT)
        await pilot.pause()

        await pilot.press("f")
        await pilot.pause()

        assert len(calls) == 1
        argv, cwd = calls[0]
        assert argv[:3] == ["claude", "--resume", ROOT]
        assert "--fork-session" in argv
        assert cwd == CWD
        assert graph.selected_id == created_ids[0]


@pytest.mark.asyncio
async def test_new_session_action_starts_in_the_selected_nodes_directory(projects_root, monkeypatch):
    app = make_app(projects_root)
    calls = []
    created_ids = []

    def fake_run(argv, cwd):
        calls.append((argv, cwd))
        new_id = argv[argv.index("--session-id") + 1]
        created_ids.append(new_id)
        write_session(projects_root, new_id, [message("nn1", 0.0), message("nn2", 0.0, kind="assistant")])

    async with app.run_test() as pilot:
        await pilot.pause()
        monkeypatch.setattr(app, "_run_claude", fake_run)
        monkeypatch.setattr(app, "_dir_exists", lambda cwd: True)
        monkeypatch.setattr(app, "_claude_available", lambda: True)  # CI runners don't have claude installed
        graph = app.query_one(GraphView)
        graph.select_id(FORK)
        await pilot.pause()

        await pilot.press("n")
        await pilot.pause()

        assert len(calls) == 1
        argv, cwd = calls[0]
        assert argv == ["claude", "--session-id", created_ids[0]]  # no --resume: unrelated to FORK
        assert cwd == CWD
        assert graph.selected_id == created_ids[0]


@pytest.mark.asyncio
async def test_fork_notifies_instead_of_selecting_when_the_new_session_has_no_messages(projects_root, monkeypatch):
    app = make_app(projects_root)
    notified = []
    app.notify = lambda message, **kwargs: notified.append(message)

    async with app.run_test() as pilot:
        await pilot.pause()
        monkeypatch.setattr(app, "_run_claude", lambda argv, cwd: None)  # claude ran but wrote nothing
        monkeypatch.setattr(app, "_dir_exists", lambda cwd: True)
        monkeypatch.setattr(app, "_claude_available", lambda: True)  # CI runners don't have claude installed
        graph = app.query_one(GraphView)
        graph.select_id(ROOT)
        await pilot.pause()
        before = graph.selected_id

        await pilot.press("f")
        await pilot.pause()

        assert graph.selected_id == before  # nothing to select, selection is unchanged
        assert any("no messages yet" in n for n in notified)


@pytest.mark.asyncio
async def test_archive_hides_a_node_and_z_toggles_it_back(projects_root):
    app = make_app(projects_root)
    async with app.run_test() as pilot:
        await pilot.pause()
        graph = app.query_one(GraphView)
        graph.select_id(FORK)
        await pilot.pause()

        await pilot.press("x")
        await pilot.pause()
        assert FORK not in graph_ids(app)
        assert app.state.is_archived(FORK) is True
        status = app.query_one("#status", Static).content.plain
        assert "1 archived hidden" in status

        await pilot.press("z")  # show archived
        await pilot.pause()
        assert FORK in graph_ids(app)

        await pilot.press("z")  # hide again
        await pilot.pause()
        assert FORK not in graph_ids(app)

        # FORK is hidden, so the selection fell back to another row; bring it
        # back into view to unarchive it.
        await pilot.press("z")
        await pilot.pause()
        graph.select_id(FORK)
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        assert app.state.is_archived(FORK) is False


@pytest.mark.asyncio
async def test_modal_offers_archive_and_choosing_it_archives_the_session(projects_root):
    app = make_app(projects_root)
    async with app.run_test() as pilot:
        await pilot.pause()
        graph = app.query_one(GraphView)
        graph.select_id(FORK)
        await pilot.pause()

        await pilot.press("enter")
        await pilot.pause()
        modal = app.screen
        assert isinstance(modal, ActionModal)
        options = modal.query_one(OptionList)
        archive_index = next(
            i for i in range(options.option_count) if options.get_option_at_index(i).id == "archive"
        )
        assert options.get_option_at_index(archive_index).prompt == "Archive"

        options.highlighted = archive_index
        await pilot.press("enter")
        await pilot.pause()

        assert app.state.is_archived(FORK) is True
        assert FORK not in graph_ids(app)

        # Reopening the modal on the (now archived, so hidden by default)
        # session should offer "Unarchive" instead.
        await pilot.press("z")
        await pilot.pause()
        graph.select_id(FORK)
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        options = app.screen.query_one(OptionList)
        archive_index = next(
            i for i in range(options.option_count) if options.get_option_at_index(i).id == "archive"
        )
        assert options.get_option_at_index(archive_index).prompt == "Unarchive"


def write_many(root, count):
    """`count` independent sessions, all recent, so every one is a top-level row."""
    from conftest import message, write_session

    for i in range(count):
        session_id = f"bbbbbbbb-0000-0000-0000-{i:012d}"
        write_session(root, session_id, [message(f"m{i}a", 0.5), message(f"m{i}b", 0.4, kind="assistant")])


@pytest.mark.asyncio
@pytest.mark.parametrize("style", ["compact", "flow"])
async def test_navigating_down_scrolls_the_view(projects_root, style):
    write_many(projects_root, 150)
    app = ArvreApp(
        cwd=CWD, root=projects_root, window_24h=False, all_projects=True, style=style,
        state_path=projects_root / "state.json",
    )
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        graph = app.query_one(GraphView)
        container = app.query_one("#scroll")
        for _ in range(80):
            await pilot.press("down")
        await pilot.pause()
        assert container.scroll_y > 0
        if style == "flow":
            box = graph._flow.boxes[graph.selected_id]
            top, bottom = box.y, box.y + 4
        else:
            top, bottom = graph._index, graph._index + 1
        assert container.scroll_y <= top and bottom <= container.scroll_y + container.size.height
