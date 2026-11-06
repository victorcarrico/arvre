import io
from pathlib import Path

from arvre.cache import ScanCache
from arvre.progress import FRAMES, frame_for_tick, scan_with_progress


def test_frames_cycle():
    assert frame_for_tick(0) == FRAMES[0]
    assert frame_for_tick(1) == FRAMES[1]
    assert frame_for_tick(2) == FRAMES[2]
    assert frame_for_tick(3) == FRAMES[0]  # wraps back around
    assert frame_for_tick(len(FRAMES) * 5) == FRAMES[0]


def test_frames_all_share_the_same_prefix_so_only_the_dots_change():
    stem = "building your arvre"
    assert all(f.startswith(stem) for f in FRAMES)
    assert [f[len(stem) :] for f in FRAMES] == [".", "..", "..."]


class _NonTTYStream(io.StringIO):
    def isatty(self) -> bool:
        return False


def test_non_tty_stream_scans_silently_without_a_thread(projects_root):
    # Covers --print | pipe, CI, and the test harness itself: no animation,
    # no background thread, just a plain scan.
    stream = _NonTTYStream()
    sessions = scan_with_progress(projects_root, ScanCache(), stream=stream)
    assert sessions  # the fixture has real sessions in it
    assert stream.getvalue() == ""


def test_non_tty_result_matches_a_plain_discover(projects_root):
    from arvre.scanner import discover

    cache_a, cache_b = ScanCache(), ScanCache()
    via_progress = scan_with_progress(projects_root, cache_a, stream=_NonTTYStream())
    direct = discover(projects_root, cache_b)
    assert via_progress.keys() == direct.keys()


class _TTYStream(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_tty_stream_animates_while_the_scan_is_slow(monkeypatch, projects_root):
    import time

    import arvre.progress as progress_mod

    # Real timings (0.2s / 0.25s) would make this test slow and flaky; a
    # 20ms scan against 10ms thresholds exercises the same code path fast.
    monkeypatch.setattr(progress_mod, "SHOW_AFTER_SECONDS", 0.01)
    monkeypatch.setattr(progress_mod, "FRAME_SECONDS", 0.01)
    monkeypatch.setattr(progress_mod, "discover", lambda root, cache: (time.sleep(0.05), {"fake": "session"})[1])

    stream = _TTYStream()
    result = scan_with_progress(Path("unused"), ScanCache(), stream=stream)

    assert result == {"fake": "session"}
    output = stream.getvalue()
    assert "building your arvre" in output
    assert output.endswith("\r\033[K")  # the line is always left clean
