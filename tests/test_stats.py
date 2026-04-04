"""Tests for nudgarr.stats utility functions."""

from unittest.mock import patch
import pytest

from nudgarr.stats import pick_items_with_cooldown


def _make_items(n):
    """Return n simple item dicts with distinct IDs and titles."""
    return [{"id": i, "title": f"Item {i}", "added": f"2024-0{(i % 9) + 1}-01T00:00:00Z"} for i in range(1, n + 1)]


def _run(items, max_per_run, cooldown_hours=0, sample_mode="random"):
    """Call pick_items_with_cooldown with a mocked DB returning no cooldown hits."""
    with patch("nudgarr.stats.db.get_last_searched_ts_bulk", return_value={}):
        return pick_items_with_cooldown(
            items, "radarr", "TestInstance", "http://localhost", "missing",
            cooldown_hours, max_per_run, sample_mode,
        )


# ── max_per_run behaviour ─────────────────────────────────────────────────────

class TestMaxPerRun:
    def test_zero_returns_all_eligible(self):
        """0 = All Eligible — must return every item that passes cooldown."""
        items = _make_items(10)
        chosen, eligible, skipped = _run(items, max_per_run=0)
        assert len(chosen) == 10
        assert eligible == 10
        assert skipped == 0

    def test_positive_limit_respected(self):
        items = _make_items(10)
        chosen, eligible, skipped = _run(items, max_per_run=3)
        assert len(chosen) == 3
        assert eligible == 10

    def test_limit_larger_than_pool_returns_all(self):
        items = _make_items(5)
        chosen, eligible, _ = _run(items, max_per_run=20)
        assert len(chosen) == 5
        assert eligible == 5

    def test_empty_items_returns_empty(self):
        chosen, eligible, skipped = _run([], max_per_run=0)
        assert chosen == []
        assert eligible == 0
        assert skipped == 0

    def test_zero_with_empty_items_returns_empty(self):
        chosen, eligible, skipped = _run([], max_per_run=0)
        assert chosen == []


# ── cooldown filtering ────────────────────────────────────────────────────────

class TestCooldown:
    def test_all_on_cooldown_returns_empty(self):
        from nudgarr.utils import iso_z
        from datetime import datetime, timezone
        items = _make_items(5)
        # All items were searched 1 hour ago; cooldown is 48h
        recent = iso_z(datetime.now(timezone.utc))
        ts_map = {str(i): recent for i in range(1, 6)}
        with patch("nudgarr.stats.db.get_last_searched_ts_bulk", return_value=ts_map):
            chosen, eligible, skipped = pick_items_with_cooldown(
                items, "radarr", "TestInstance", "http://localhost", "missing",
                48, 10, "random",
            )
        assert len(chosen) == 0
        assert eligible == 0
        assert skipped == 5

    def test_zero_cooldown_skips_nothing(self):
        from nudgarr.utils import iso_z
        from datetime import datetime, timezone
        items = _make_items(5)
        recent = iso_z(datetime.now(timezone.utc))
        ts_map = {str(i): recent for i in range(1, 6)}
        with patch("nudgarr.stats.db.get_last_searched_ts_bulk", return_value=ts_map):
            chosen, eligible, skipped = pick_items_with_cooldown(
                items, "radarr", "TestInstance", "http://localhost", "missing",
                0, 0, "random",
            )
        assert len(chosen) == 5
        assert skipped == 0


# ── sample mode sorting ───────────────────────────────────────────────────────

class TestSampleMode:
    def test_alphabetical_sorts_by_title(self):
        items = [
            {"id": 1, "title": "Zebra"},
            {"id": 2, "title": "Apple"},
            {"id": 3, "title": "Mango"},
        ]
        chosen, _, _ = _run(items, max_per_run=0, sample_mode="alphabetical")
        assert [i["title"] for i in chosen] == ["Apple", "Mango", "Zebra"]

    def test_oldest_added_sorts_ascending(self):
        items = [
            {"id": 1, "title": "A", "added": "2024-03-01T00:00:00Z"},
            {"id": 2, "title": "B", "added": "2024-01-01T00:00:00Z"},
            {"id": 3, "title": "C", "added": "2024-02-01T00:00:00Z"},
        ]
        chosen, _, _ = _run(items, max_per_run=0, sample_mode="oldest_added")
        assert [i["id"] for i in chosen] == [2, 3, 1]

    def test_newest_added_sorts_descending(self):
        items = [
            {"id": 1, "title": "A", "added": "2024-01-01T00:00:00Z"},
            {"id": 2, "title": "B", "added": "2024-03-01T00:00:00Z"},
            {"id": 3, "title": "C", "added": "2024-02-01T00:00:00Z"},
        ]
        chosen, _, _ = _run(items, max_per_run=0, sample_mode="newest_added")
        assert [i["id"] for i in chosen] == [2, 3, 1]

    def test_unknown_mode_preserves_input_order(self):
        """Unrecognised mode strings must not reorder items."""
        items = [{"id": i, "title": f"Item {i}"} for i in [3, 1, 2]]
        chosen, _, _ = _run(items, max_per_run=0, sample_mode="not_a_real_mode")
        assert [i["id"] for i in chosen] == [3, 1, 2]


# ── round_robin ───────────────────────────────────────────────────────────────

class TestRoundRobin:
    """Tests for the round_robin sample mode in pick_items_with_cooldown."""

    def _run_rr(self, items, ts_map, max_per_run=0):
        """Run with a specific ts_map so NULL vs searched can be controlled."""
        with patch("nudgarr.stats.db.get_last_searched_ts_bulk", return_value=ts_map):
            return pick_items_with_cooldown(
                items, "radarr", "TestInstance", "http://localhost", "movie",
                0, max_per_run, "round_robin",
            )

    def test_null_items_sort_before_searched(self):
        """Items never searched (NULL ts) must come before items with a timestamp."""
        items = [
            {"id": 1, "title": "Searched A"},
            {"id": 2, "title": "Never Searched"},
            {"id": 3, "title": "Searched B"},
        ]
        ts_map = {
            "1": "2024-01-10T00:00:00Z",
            "3": "2024-01-05T00:00:00Z",
            # id 2 absent — never searched
        }
        chosen, _, _ = self._run_rr(items, ts_map)
        ids = [i["id"] for i in chosen]
        assert ids[0] == 2, "NULL item must be first"
        assert set(ids) == {1, 2, 3}

    def test_searched_items_sort_oldest_first(self):
        """Among items with timestamps, longest-waiting (oldest ts) goes first."""
        items = [
            {"id": 1, "title": "Recent"},
            {"id": 2, "title": "Oldest"},
            {"id": 3, "title": "Middle"},
        ]
        ts_map = {
            "1": "2024-03-01T00:00:00Z",
            "2": "2024-01-01T00:00:00Z",
            "3": "2024-02-01T00:00:00Z",
        }
        chosen, _, _ = self._run_rr(items, ts_map)
        assert [i["id"] for i in chosen] == [2, 3, 1]

    def test_multiple_null_items_all_present(self):
        """Multiple never-searched items must all appear (random order among themselves)."""
        items = [{"id": i, "title": f"Item {i}"} for i in range(1, 6)]
        # All NULL — no ts_map entries
        chosen, _, _ = self._run_rr(items, {})
        assert len(chosen) == 5
        assert {i["id"] for i in chosen} == {1, 2, 3, 4, 5}

    def test_null_items_precede_all_searched_items(self):
        """Every NULL item must appear before every searched item regardless of ts values."""
        items = [
            {"id": 1, "title": "Very Old Searched", "added": "2023-01-01T00:00:00Z"},
            {"id": 2, "title": "Never Searched A"},
            {"id": 3, "title": "Never Searched B"},
            {"id": 4, "title": "Recent Searched"},
        ]
        ts_map = {
            "1": "2023-06-01T00:00:00Z",
            "4": "2024-06-01T00:00:00Z",
        }
        chosen, _, _ = self._run_rr(items, ts_map)
        ids = [i["id"] for i in chosen]
        null_positions = [ids.index(2), ids.index(3)]
        searched_positions = [ids.index(1), ids.index(4)]
        assert max(null_positions) < min(searched_positions), (
            "All NULL items must precede all searched items"
        )

    def test_max_per_run_respected(self):
        """round_robin must still cap at max_per_run after sorting."""
        items = [{"id": i, "title": f"Item {i}"} for i in range(1, 8)]
        chosen, eligible, _ = self._run_rr(items, {}, max_per_run=3)
        assert len(chosen) == 3
        assert eligible == 7

    def test_empty_list_returns_empty(self):
        chosen, eligible, skipped = self._run_rr([], {})
        assert chosen == []
        assert eligible == 0


# ── largest_gap_first ─────────────────────────────────────────────────────────

class TestLargestGapFirst:
    """Tests for the largest_gap_first sample mode in pick_items_with_cooldown."""

    def _run_lgf(self, items, ts_map, max_per_run=0):
        with patch("nudgarr.stats.db.get_last_searched_ts_bulk", return_value=ts_map):
            return pick_items_with_cooldown(
                items, "radarr", "TestInstance", "http://localhost", "movie",
                0, max_per_run, "largest_gap_first",
            )

    def _item(self, id_, current, cutoff, ts=None):
        """Build a CF Score item dict. ts=None means never searched."""
        return {
            "id": id_,
            "title": f"Item {id_}",
            "current_score": current,
            "cutoff_score": cutoff,
            "added": "2024-01-01T00:00:00Z",
        }

    def test_primary_sort_largest_gap_first(self):
        """Items with a larger gap must appear before items with a smaller gap."""
        items = [
            self._item(1, current=50, cutoff=100),   # gap 50
            self._item(2, current=10, cutoff=100),   # gap 90
            self._item(3, current=70, cutoff=100),   # gap 30
        ]
        ts_map = {
            "1": "2024-01-10T00:00:00Z",
            "2": "2024-01-10T00:00:00Z",
            "3": "2024-01-10T00:00:00Z",
        }
        chosen, _, _ = self._run_lgf(items, ts_map)
        assert [i["id"] for i in chosen] == [2, 1, 3]

    def test_tiebreaker_oldest_searched_first(self):
        """Within equal gap groups, the item searched longest ago must go first."""
        items = [
            self._item(1, current=50, cutoff=100),   # gap 50, recent
            self._item(2, current=50, cutoff=100),   # gap 50, oldest
            self._item(3, current=50, cutoff=100),   # gap 50, middle
        ]
        ts_map = {
            "1": "2024-03-01T00:00:00Z",
            "2": "2024-01-01T00:00:00Z",
            "3": "2024-02-01T00:00:00Z",
        }
        chosen, _, _ = self._run_lgf(items, ts_map)
        assert [i["id"] for i in chosen] == [2, 3, 1]

    def test_null_items_in_tied_group_precede_searched(self):
        """NULL items within a tied gap group must come before searched items in that group."""
        items = [
            self._item(1, current=50, cutoff=100),   # gap 50, searched
            self._item(2, current=50, cutoff=100),   # gap 50, never searched
            self._item(3, current=10, cutoff=100),   # gap 90, searched — different group
        ]
        ts_map = {
            "1": "2024-01-10T00:00:00Z",
            "3": "2024-01-01T00:00:00Z",
            # id 2: NULL
        }
        chosen, _, _ = self._run_lgf(items, ts_map)
        ids = [i["id"] for i in chosen]
        # Item 3 (gap 90) must be first
        assert ids[0] == 3
        # Within the gap-50 group, NULL item 2 must precede searched item 1
        assert ids.index(2) < ids.index(1)

    def test_different_gap_groups_never_reorder(self):
        """Items from a higher gap group must always precede lower gap groups."""
        items = [
            self._item(1, current=80, cutoff=100),   # gap 20
            self._item(2, current=20, cutoff=100),   # gap 80
            self._item(3, current=60, cutoff=100),   # gap 40
        ]
        ts_map = {
            "1": "2024-01-01T00:00:00Z",  # oldest — but lowest gap
            "2": "2024-06-01T00:00:00Z",  # newest — but highest gap
            "3": "2024-03-01T00:00:00Z",
        }
        chosen, _, _ = self._run_lgf(items, ts_map)
        assert [i["id"] for i in chosen] == [2, 3, 1]

    def test_all_null_items_sorted_by_gap(self):
        """When all items are never searched, primary sort (gap desc) still applies."""
        items = [
            self._item(1, current=70, cutoff=100),   # gap 30
            self._item(2, current=10, cutoff=100),   # gap 90
            self._item(3, current=50, cutoff=100),   # gap 50
        ]
        chosen, _, _ = self._run_lgf(items, {})
        # Gap groups: 90 > 50 > 30 — within each single-item group NULL order is random
        # but cross-group ordering must be correct
        assert chosen[0]["id"] == 2   # gap 90 always first
        assert chosen[2]["id"] == 1   # gap 30 always last

    def test_max_per_run_respected(self):
        items = [self._item(i, current=i * 5, cutoff=100) for i in range(1, 8)]
        ts_map = {str(i): "2024-01-01T00:00:00Z" for i in range(1, 8)}
        chosen, eligible, _ = self._run_lgf(items, ts_map, max_per_run=3)
        assert len(chosen) == 3
        assert eligible == 7

    def test_empty_list_returns_empty(self):
        chosen, eligible, skipped = self._run_lgf([], {})
        assert chosen == []
        assert eligible == 0
