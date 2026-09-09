"""Чистая математика rain-раздачи: без БД и сети, чтобы можно было тестировать отдельно.

Схема — 4 доли одного группового бюджета (в процентах, сумма 100).
Бюджет режется на 4 куска, копейки уходят последнему куску, чтобы сумма сходилась.
"""
from typing import List, Sequence

RAIN_SCHEMES: List[List[int]] = [
    [15, 20, 30, 35],
    [10, 25, 30, 35],
    [15, 25, 25, 35],
    [20, 20, 25, 35],
    [10, 10, 20, 60],
    [20, 25, 25, 30],
]


def pick_scheme(rng, schemes: Sequence[Sequence[int]] = RAIN_SCHEMES) -> List[int]:
    """Случайная схема + случайный порядок долей между 4 местами."""
    base = list(schemes[rng.randrange(len(schemes))])
    rng.shuffle(base)
    return base


def split_budget(budget: float, shares: Sequence[int]) -> List[float]:
    """Режет бюджет по долям, округляет до копеек. Сумма кусков == округлённому бюджету."""
    total = round(float(budget), 2)
    weights = [float(s) for s in shares]
    wsum = sum(weights)
    if total <= 0 or wsum <= 0 or not weights:
        return [0.0 for _ in weights]
    out = [round(total * w / wsum, 2) for w in weights[:-1]]
    out.append(round(total - sum(out), 2))
    return out
