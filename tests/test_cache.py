from conftest import fake_uuid, message, write_session, write_title_sidecar

from arvre.cache import MISS, ScanCache
from arvre.forks import link_forks
from arvre.scanner import UUID_PREFIX_LEN, discover

SID = "aaaaaaaa-0000-0000-0000-000000000001"


def test_cold_scan_then_warm_scan_yield_identical_sessions(projects_root):
    cache = ScanCache()
    cold = discover(projects_root, cache)
    assert cache.dirty  # new entries were stored

    warm = discover(projects_root, cache)
    assert warm.keys() == cold.keys()
    for sid in cold:
        assert warm[sid].name == cold[sid].name
        assert warm[sid].uuids == cold[sid].uuids
        assert warm[sid].last_ts == cold[sid].last_ts


def test_changed_file_invalidates_its_cache_entry(projects_root):
    cache = ScanCache()
    before = discover(projects_root, cache)

    write_session(projects_root, SID, [message("u1", 3.2), message("u2", 0.1, kind="assistant")])

    after = discover(projects_root, cache)
    assert after[SID].uuids == {fake_uuid("u1")[:UUID_PREFIX_LEN], fake_uuid("u2")[:UUID_PREFIX_LEN]}
    assert after[SID].last_ts != before[SID].last_ts


def test_lookup_reports_miss_for_an_unknown_or_stale_key(projects_root, tmp_path):
    cache = ScanCache()
    path = tmp_path / "x.jsonl"
    path.write_text("{}\n", encoding="utf-8")
    assert cache.lookup(str(path), 1, 2, 0) is MISS
    cache.store(str(path), 1, 2, 0, None)
    assert cache.lookup(str(path), 1, 2, 0) is None  # a hit can legitimately be None
    assert cache.lookup(str(path), 1, 3, 0) is MISS  # size changed
    assert cache.lookup(str(path), 9, 2, 0) is MISS  # mtime changed
    assert cache.lookup(str(path), 1, 2, 7) is MISS  # title sidecar mtime changed


def test_save_and_load_round_trip_through_disk(projects_root, tmp_path):
    cache_path = tmp_path / "scan-v1.json"
    cache = ScanCache()
    sessions = discover(projects_root, cache)
    link_forks(sessions)
    cache.save(cache_path)
    assert cache_path.exists()

    loaded = ScanCache.load(cache_path)
    reloaded = discover(projects_root, loaded)
    # Nothing on disk changed, so every lookup should be a cache hit and the
    # reloaded sessions should match exactly, fork links included.
    assert not loaded.dirty
    assert reloaded.keys() == sessions.keys()
    for sid in sessions:
        assert reloaded[sid].uuids == sessions[sid].uuids
        assert reloaded[sid].cwd == sessions[sid].cwd
        assert reloaded[sid].name == sessions[sid].name


def test_save_is_a_noop_when_not_dirty(tmp_path):
    cache_path = tmp_path / "scan-v1.json"
    ScanCache().save(cache_path)
    assert not cache_path.exists()


def test_load_ignores_a_corrupt_file(tmp_path):
    cache_path = tmp_path / "scan-v1.json"
    cache_path.write_text("not json", encoding="utf-8")
    cache = ScanCache.load(cache_path)
    assert cache.lookup("whatever", 1, 2, 0) is MISS


def test_load_ignores_a_different_cache_version(tmp_path):
    cache_path = tmp_path / "scan-v1.json"
    cache_path.write_text('{"version": 999, "sessions": {}}', encoding="utf-8")
    cache = ScanCache.load(cache_path)
    assert cache.lookup("whatever", 1, 2, 0) is MISS


def test_sidecar_rename_invalidates_cache_even_if_the_jsonl_is_untouched(projects_root):
    cache = ScanCache()
    before = discover(projects_root, cache)
    assert before[SID].name == "Auth refactor"

    write_title_sidecar(projects_root, SID, "Renamed later")
    after = discover(projects_root, cache)
    assert after[SID].name == "Renamed later"
