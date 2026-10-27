"""Gym and Compex blocks and rewards (rules confirmed by Nick, 27 Oct 2026)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from custom_components.health_hub.core import settings as settings_mod
from custom_components.health_hub.core import training
from custom_components.health_hub.core.store import Store

MONDAY = date(2026, 9, 28)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "hub.db")
    settings_mod.update(s, {"block_anchor": MONDAY.isoformat()})
    yield s
    s.close()


def _log(store, kind, variant, count, first=MONDAY):
    for i in range(count):
        training.log(store, first + timedelta(days=i % 28), kind, variant)


def _balance(store):
    return sum(r["delta"] for r in store.rewards_ledger())


def test_both_targets_earn_three(store):
    _log(store, "gym", "push", 12)
    _log(store, "compex", None, 16)
    training.settle(store, settings_mod.load(store), MONDAY + timedelta(days=28))
    assert _balance(store) == 3


def test_one_target_earns_one_and_counts_twice_a_day(store):
    for _ in range(2):  # two sessions in one day count as two
        _log(store, "gym", "legs", 6)
    _log(store, "compex", None, 15)
    training.settle(store, settings_mod.load(store), MONDAY + timedelta(days=30))
    assert _balance(store) == 1


def test_block_not_counted_until_it_ends(store):
    _log(store, "gym", "pull", 12)
    training.settle(store, settings_mod.load(store), MONDAY + timedelta(days=27))
    assert _balance(store) == 0


def test_late_log_recounts_a_finished_block(store):
    _log(store, "gym", "push", 11)
    s = settings_mod.load(store)
    training.settle(store, s, MONDAY + timedelta(days=29))
    assert _balance(store) == 0
    training.log(store, MONDAY + timedelta(days=27), "gym", "pull")  # forgotten Sunday session
    training.settle(store, s, MONDAY + timedelta(days=29))
    assert _balance(store) == 1
    assert len([r for r in store.rewards_ledger() if r["block_start"]]) == 1


def test_spend(store):
    with pytest.raises(training.TrainingError):
        training.spend(store)
    _log(store, "compex", None, 16)
    training.settle(store, settings_mod.load(store), MONDAY + timedelta(days=28))
    training.spend(store)
    assert _balance(store) == 0
