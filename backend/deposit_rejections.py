"""Player-facing text for preset rejection codes, including old saved requests."""
REASONS = {
    "long_wait": "Долгое ожидание",
    "illiquid_skin": "Неликвидный скин",
    "yellow_tag": "Жёлтая табличка на скине",
    "no_reason": "Без причины",
}


def rejection_reason_text(reason):
    return REASONS.get(reason, reason)
