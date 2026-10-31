import pytest

from arvre.app import ActionModal, ArvreApp
from arvre.graph_view import GraphView

from conftest import CWD

ROOT = "aaaaaaaa-0000-0000-0000-000000000001"
FORK = "aaaaaaaa-0000-0000-0000-000000000002"
OTHER = "aaaaaaaa-0000-0000-0000-000000000003"


def make_app(projects_root, **kwargs):
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
        drawn = graph.render().plain
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
