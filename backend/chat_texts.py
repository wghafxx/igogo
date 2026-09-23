"""Automatic support-chat texts in the player's language (ru / en)."""

LANGS = ("ru", "en")
CURRENCIES = ("RUB", "USD", "EUR", "UAH", "KZT", "BYN", "BRL", "TRY", "PLN", "UZS")

TEXTS = {
    "welcome": {
        "ru": (
            "Здравствуйте! Это чат поддержки. Здесь вы сможете быстро пополнить баланс деньгами или скинами.\n\n"
            "Доступна оплата в следующих валютах:\n"
            "BYN — белорусский рубль\nEUR — евро\nKZT — казахстанский тенге\nRUB — российский рубль\n"
            "UAH — украинская гривна\nUSD — доллар США\nBRL — бразильский реал\nTRY — турецкая лира\n"
            "PLN — польский злотый\nUZS — узбекский сум\n\n"
            "Также вы можете решить здесь свой вопрос — просто задайте его. Можно приложить скриншот (до 1 МБ, хранится 3 дня)."
        ),
        "en": (
            "Hello! This is the support chat. Here you can quickly top up your balance with money or skins.\n\n"
            "Payments are accepted in these currencies:\n"
            "BYN — Belarusian ruble\nEUR — euro\nKZT — Kazakhstani tenge\nRUB — Russian ruble\n"
            "UAH — Ukrainian hryvnia\nUSD — US dollar\nBRL — Brazilian real\nTRY — Turkish lira\n"
            "PLN — Polish zloty\nUZS — Uzbekistani som\n\n"
            "You can also ask any question here. Screenshots can be attached (up to 1 MB, kept for 3 days)."
        ),
    },
    "reopened": {"ru": "Чат открыт заново. Оператор скоро подключится.", "en": "Chat reopened. An operator will join shortly."},
    "deposit_request": {"ru": "Хочу пополнить примерно на {rap:.2f} RAP", "en": "I want to top up about {rap:.2f} RAP"},
    "deposit_created": {"ru": "Заявка на пополнение создана. Оператор скоро подключится и подскажет, как передать скины.",
                        "en": "Top-up request created. An operator will join shortly and explain how to hand over the skins."},
    "withdrawal_request": {"ru": "Хочу получить скины на вывод: {names} (всего {count} шт., ≈{total:.2f} RAP)",
                           "en": "I want to withdraw skins: {names} ({count} pcs total, ≈{total:.2f} RAP)"},
    "withdrawal_more": {"ru": " и ещё {n}", "en": " and {n} more"},
    "withdrawal_created": {"ru": "Заявка на вывод принята. Оператор скоро подключится и передаст скины через трейд в игре.",
                           "en": "Withdrawal request accepted. An operator will join shortly and send the skins via an in-game trade."},
    "user_closed": {"ru": "Вы завершили чат. Открыть его снова можно через 3 минуты", "en": "You ended the chat. You can reopen it in 3 minutes"},
    "operator_joined": {"ru": "Оператор подключился к чату", "en": "An operator joined the chat"},
    "operator_closed": {"ru": "Чат завершён оператором. Напишите снова, если нужна помощь", "en": "The operator closed the chat. Write again if you need help"},
    "deposit_confirmed": {"ru": "Пополнение подтверждено: зачислено {credited:.2f} RAP (скины и остаток на балансе)",
                          "en": "Top-up confirmed: {credited:.2f} RAP credited (skins and the rest to your balance)"},
    "deposit_rejected": {"ru": "Заявка на пополнение отклонена. Причина: {reason}", "en": "Top-up request rejected. Reason: {reason}"},
    "skins_issued": {"ru": "Скины выданы: {done} шт. на {total:.2f} RAP. Проверьте инвентарь Roblox",
                     "en": "Skins delivered: {done} pcs worth {total:.2f} RAP. Check your Roblox inventory"},
    "withdrawal_cancelled": {"ru": "Вывод «{name}» отменён, скин возвращён в инвентарь. Причина: {reason}",
                             "en": "Withdrawal of “{name}” cancelled, the skin is back in your inventory. Reason: {reason}"},
    "screenshot": {"ru": "📎 Скриншот", "en": "📎 Screenshot"},
    "da_request": {"ru": "Хочу оплатить {amount} {currency} через DonationAlerts", "en": "I want to pay {amount} {currency} via DonationAlerts"},
    "da_instructions": {
        "ru": (
            "Оплата в валюте через DonationAlerts — пошагово:\n\n"
            "1. Откройте страницу: {url}\n"
            "2. Выберите валюту {currency} и введите сумму {amount} (не меньше минимальной суммы, указанной на странице DonationAlerts).\n"
            "3. В поле «Имя» укажите ваш Roblox-ник: {nick}\n"
            "4. В поле «Сообщение» обязательно напишите ровно эту фразу (без неё платёж не найти): {phrase}\n"
            "5. Оплатите удобным способом (карта любой страны и т. д.).\n"
            "6. Вернитесь в этот чат и нажмите кнопку «Я оплатил — проверить». Нажать можно один раз.\n\n"
            "Курс: 1 RAP = {rate} ₽. RAP начисляются по сумме в рублях, которая фактически пришла на DonationAlerts (с учётом промокода). "
            "Комиссию DonationAlerts и банка оплачивает плательщик. Можно приложить скриншот оплаты."
        ),
        "en": (
            "Paying in your currency via DonationAlerts — step by step:\n\n"
            "1. Open the page: {url}\n"
            "2. Choose the currency {currency} and enter the amount {amount} (not less than the minimum shown on the DonationAlerts page).\n"
            "3. In the “Name” field enter your Roblox username: {nick}\n"
            "4. In the “Message” field be sure to write exactly this phrase (we find your payment by it): {phrase}\n"
            "5. Pay with any convenient method (a card from any country, etc.).\n"
            "6. Come back to this chat and press “I paid — check”. It can be pressed only once.\n\n"
            "Rate: 1 RAP = {rate} RUB. RAP is credited for the ruble amount actually received on DonationAlerts (promo code included). "
            "DonationAlerts and bank fees are paid by the payer. You can attach a payment screenshot."
        ),
    },
    "da_claimed": {"ru": "Оплата отправлена на проверку. Оператор сверит платёж на DonationAlerts и зачислит RAP — обычно это занимает несколько минут.",
                   "en": "Payment sent for review. The operator will check it on DonationAlerts and credit your RAP — usually within a few minutes."},
    "da_not_found": {"ru": "платёж не найден на DonationAlerts", "en": "payment not found on DonationAlerts"},
}

REJECTION_REASONS_EN = {
    "long_wait": "Long wait",
    "illiquid_skin": "Illiquid skin",
    "yellow_tag": "Yellow tag on the skin",
    "no_reason": "No reason given",
    "payment_not_found": "Payment not found on DonationAlerts",
}


def norm_lang(value) -> str:
    value = str(value or "").lower()[:2]
    return value if value in LANGS else "ru"


def tr(key: str, lang: str = "ru", **kw) -> str:
    text = TEXTS[key][norm_lang(lang)]
    return text.format(**kw) if kw else text


def request_lang(request) -> str:
    return norm_lang(request.headers.get("x-lang"))
