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
