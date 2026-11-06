from datetime import datetime, timedelta, timezone

from arvre.state import ArvreState, _cutoff_iso

SID = "aaaaaaaa-0000-0000-0000-000000000001"
OTHER = "aaaaaaaa-0000-0000-0000-000000000002"


def test_fresh_state_has_nothing_archived():
    state = ArvreState()
    assert state.is_archived(SID) is False
    assert state.archived_ids() == set()


def test_toggle_archived_flips_and_returns_new_state():
    state = ArvreState()
    assert state.toggle_archived(SID) is True
    assert state.is_archived(SID) is True
    assert state.archived_ids() == {SID}
    assert state.toggle_archived(SID) is False
    assert state.is_archived(SID) is False
    assert state.archived_ids() == set()


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "state.json"
    state = ArvreState()
    state.set_archived(SID, True)
    state.save(path)
    assert path.exists()

    loaded = ArvreState.load(path)
    assert loaded.is_archived(SID) is True
    assert loaded.is_archived(OTHER) is False


def test_save_is_a_noop_when_nothing_changed(tmp_path):
    path = tmp_path / "state.json"
    ArvreState().save(path)
    assert not path.exists()


def test_missing_file_loads_as_empty(tmp_path):
    state = ArvreState.load(tmp_path / "does-not-exist.json")
    assert state.archived_ids() == set()


def test_corrupt_file_is_quarantined_not_overwritten(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("not json", encoding="utf-8")

    state = ArvreState.load(path)
    assert state.archived_ids() == set()
    assert not path.exists()  # moved aside, not left for a blind overwrite
    quarantined = list(tmp_path.glob("state.json.corrupt-*"))
    assert len(quarantined) == 1
    assert quarantined[0].read_text(encoding="utf-8") == "not json"


def test_mark_seen_prunes_only_entries_absent_and_stale(tmp_path):
    state = ArvreState()
    state.set_archived(SID, True)
    state.set_archived(OTHER, True)
    # Back-date OTHER's last_seen well past the prune window, as if it hadn't
    # been seen in a scan for a long time; SID keeps "just archived".
    state._sessions[OTHER].last_seen = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()

    state.mark_seen({SID})  # a scan that doesn't mention OTHER at all

    assert state.is_archived(SID) is True
    assert state.is_archived(OTHER) is False  # pruned
    assert state.archived_ids() == {SID}


def test_mark_seen_keeps_a_stale_entry_the_scan_still_reports():
    state = ArvreState()
    state.set_archived(SID, True)
    state._sessions[SID].last_seen = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()

    state.mark_seen({SID})  # this scan DID find it, so it must not be pruned

    assert state.is_archived(SID) is True


def test_cutoff_iso_is_in_the_past():
    assert _cutoff_iso(90) < datetime.now(timezone.utc).isoformat()
