"""Budget-preserving, deterministic inventory allocation. All calculations use cents."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def cents(value):
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError("Amount must be finite")
    return int((number * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def allocation(rap, bonus, catalog):
    rap_cents = cents(rap)
    bonus = min(Decimal("0.5"), max(Decimal("0"), Decimal(str(bonus or 0))))
    budget = int((Decimal(rap_cents) * Decimal("0.8") * (1 + bonus)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if rap_cents < 3500:
        raise ValueError("Минимальная сумма — 35 RAP")
    unique = {}
    for item in catalog:
        try:
            price = cents(item.get("price", 0))
        except (InvalidOperation, ValueError, TypeError):
            continue
        if not item.get("id") or not item.get("name") or price <= 0 or price > budget:
            continue
        clean = {k: item[k] for k in ("id", "type", "name", "rarity", "image") if k in item}
        clean["price"] = price / 100
        unique[str(item["id"])] = (price, clean)
    available = sorted(unique.values(), key=lambda pair: (pair[0], str(pair[1]["id"])))
    count = min(5, len(available))
    while count and sum(price for price, _ in available[:count]) > budget:
        count -= 1
    selected, remaining = [], budget
    for slots in range(count, 0, -1):
        choices = []
        for index, (price, item) in enumerate(available):
            others = available[:index] + available[index + 1:]
            reserve = sum(p for p, _ in others[:slots - 1])
            if price + reserve <= remaining:
                # Equal shares when the catalog allows; never buy beyond the remainder.
                choices.append((abs(price * slots - remaining), -price, index))
        _, _, index = min(choices)
        price, item = available.pop(index)
        selected.append(item)
        remaining -= price
    spent = sum(cents(item["price"]) for item in selected)
    if spent + remaining != budget or remaining < 0:
        raise ValueError("Ошибка распределения депозита")
    return {
        "rap": rap_cents / 100, "fee": 0.20, "bonus_applied": float(bonus),
        "credited": budget / 100, "amount": budget / 100,
        "skins_total": spent / 100, "balance_credited": remaining / 100,
        "issued_skins": selected, "settlement_version": 1,
    }