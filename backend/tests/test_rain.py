"""Rain math tests: pure functions only, no DB/env needed."""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rain_math import RAIN_SCHEMES, pick_scheme, split_budget


def test_schemes_six_and_sum_100():
    assert len(RAIN_SCHEMES) == 6
    for s in RAIN_SCHEMES:
        assert len(s) == 4
        assert sum(s) == 100
    assert [10, 10, 20, 60] in RAIN_SCHEMES  # схема 5 с джекпотом


def test_split_sums_to_budget():
    for budget in (1000.0, 743.55, 1128.0, 100.0, 0.04):
        amounts = split_budget(budget, [10, 10, 20, 60])
        assert len(amounts) == 4
        assert abs(sum(amounts) - round(budget, 2)) < 1e-9
        assert all(a >= 0 for a in amounts)


def test_split_example_1000_scheme5():
    assert split_budget(1000.0, [10, 10, 20, 60]) == [100.0, 100.0, 200.0, 600.0]


def test_pick_scheme_shuffles_but_keeps_sums():
    rng = random.Random(42)
    seen = set()
    for _ in range(50):
        s = pick_scheme(rng)
        assert sum(s) == 100 and len(s) == 4
        seen.add(tuple(sorted(s)))
    assert len(seen) > 1  # и схемы, и порядок реально меняются
