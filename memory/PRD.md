# BLOXGRADE — PRD / состояние

## Сессия 3 (2026-06): админ-банк — PIN и полный сброс
- PIN-код 1001 (ADMIN_BANK_PIN в env, по умолчанию 1001; проверка server-side hmac) обязателен для: смены RTP (диалог подтверждения «было → стало»), корректировки банка ±, изменения пула ±, полного сброса.
- POST /api/admin/bank/reset {pin}: под bank_lock() (Mongo-lease) bank_state → {bank 0, pool 0, commission_profit 0, receipts [], rain_returns [], commission_backfill_version 1}, bank_ledger очищается + 1 строка kind "reset"; admin_audit event bank_reset. Не трогает upgrades/users/deposits/withdrawals. pool=0.0 выставлен явно, чтобы ensure_pool не восстанавливал его из истории.
- Frontend: components/admin/PinConfirmDialog.jsx, BankTab.jsx (ResetPanel, askPin). Тесты: BankTab.test.jsx 7/7; testing agent iteration_7 — backend 13/13, frontend 100%.


## Сессия 2 (2026-06): колесо, фразы, звуки, баг сброса результата
- Зона колеса — оранжевый градиент (#be4a1d→#e8862f→#ffbf48→#ffe6a3) + размытое SVG-свечение (feGaussianBlur, мягкая пульсация). Пользователь явно выбрал ОРАНЖЕВЫЙ вариант — не менять на золотой.
- Вместо надписи «кешбэк +N» (кешбэк всё равно начисляется) — фразы: проигрыш «Скоро повезет !»/«Почти докрутило !»/«Еще чуть чуть..», победа «Поздравляем !»/«Удачный прокрут !». 1% редкие: «Ёбаный рот этого казино...» + тихий /sounds/casino.mp3 (vol .12); «Меллстройность подкрутил...» + /sounds/mellstroy.mp3 (vol .3). Логика в hooks/useUpgradeSpin.js (pickPhrase), lib/sound.js (playRareSound).
- Баг: после проигрыша долго держались результат и старые проценты. UpgradePanel: результат/lockedChance авто-сбрасываются через 4с; смена цели/скинов внутри окна 1.5с планирует сброс, а не теряется. Testing agent iteration_6 — все регрессии пройдены.


## Актуальная сессия (2026-06): вывод скинов → поддержка, вкладка «Деньги»
Исходный запрос: «без лишних слов исправь вывод скина кнопку красивее как на сайте кнопки например вывода под цветовую гамму и нужно при выводе не эта меню а перевод на поддержку как при пополнении там все помогут. в пополнить не меняя стиль рубли изменить на деньги/money оставить сбп как есть но переводить в поддержку и добавить картой все страны для всех стран перевод на поддержку.» Уточнение: поддержка = лайв-чат внутри сайта; ysrent1 больше никогда не актуален.

Сделано:
- Backend: `POST /api/chats` принимает `kind:"withdrawal"` (только авторизованные) → в чат постится сообщение `withdrawal_request` со списком pending-выводов + системное сообщение. `RECEIVERS` → `{id:"support", nickname:"Поддержка"}`; ysrent1 удалён из кода и public/receivers.
- Frontend: вывод из инвентаря и «Как получить скин» создают withdrawal-чат и открывают LiveChatWidget; withdrawal-ветка SupportDialog удалена. `.btn-withdraw` — тёмная #1c1d25 с золотым текстом/рамкой, при hover — золотая.
- Пополнение: вкладка «Деньги»/«Money» (WalletIcon). `SbpTopUp.jsx`: плитки СБП + «Карта · все страны» (Visa, /payments/visa.png). Обе создают support-чат с готовым сообщением, закрывают модалку, открывают чат. Бейдж `withdrawal_request` в ChatMessages, ключи i18n `rub.*`, `chat.withdrawal`.
- Тесты: backend/tests/test_withdrawal_chat_topup_flow.py (5/5), WithdrawalHistory.test.jsx (5/5), testing agent iteration_5 — всё зелёное.
- Backlog P2: подсветка withdrawal_request в админ-панели чатов.


## Последнее согласованное состояние (2026-09-18, после серии визуальных правок)
- Последний запрос: «поставь это фоном что бы не нагружало и тд webp формат наверное» + новый размытый фон Train за мокрым стеклом. Именно этот файл, НЕ предыдущий резкий Train и НЕ Dust2. Исходник /app/assets/backgrounds/train-soft-original.png (1692×930, 1 899 310 B). WebP: src/assets/bg-train-soft.webp (57 722 B); мобильный центральный кроп640×1100 bg-train-soft-mobile.webp (13 808 B), media ≤639px. Скрипт scripts/prepare_background.py. Никаких runtime blur, анимаций, дополнительных затемняющих слоёв фона.
- Последние указания о бренде: «ВЕРНИ ТЕПЕРЬ СТАРЫЙ ТЕКСТ не фото и сделай серыми иконки справа слева выбора скинов», затем «сверху и снизу замени лого на это» + квадратная картинка двух белых стрелок на тёмном фоне. Итог: header-brand-icon/page-brand-icon — IMG /brand/icon-192.png (из присланного avatar-original.png), размеры40px/40–46px; слово BLOXGRADE — обычный жирный белый Rubik (SPAN), НЕ картинка шрифта и НЕ Russo One. Большие SVG иконки source/target muted серые #969ca6/#777e89. Source смотрит вниз, target вверх как раньше.
- Колесо и указатель — ИСХОДНЫЕ оранжевые градиенты. Пользователь отменил серебристое, золотистое оформление, уменьшение логотипов и 22% затемнение. Не возвращать отменённые эксперименты.
- Favicon/apple/OG avatar подготовлены из присланного изображения. Meta/OG/Twitter описание ровно: «BloxGrade - Прокачай свои скины BloxStrike !». На странице описание не показывать (явный выбор пользователя). OG URL из REACT_APP_BACKEND_URL, не старый домен.
- Карточки выбора — градиент как live drop, крупнее оружие, подписи/цена, нижняя полоса редкости; точки справа сверху удалены. Hover не перемещает саму кнопку, только изображение.

### Баги: новые доказательства и сохранённые исправления
- Блокировка при движении автокликера была отдельно воспроизведена настоящими mouse down/move/up: выделение начиналось в промежутке сетки и захватывало текст карточек; следующий захват вызывал trusted dragstart/pointercancel. Это отличается от первоначального синтетического теста click(). Исправлены user-select на игровых областях и dragstart capture через lib/game-interactions.js с исключениями для editable полей. Пользователь подтвердил «все починилось молодец». НЕ предотвращать pointerdown/mousedown глобально — нужна прокрутка, фокус, слайдеры.
- Полоса при прокрутке/выбранной справа цели: убран backdrop-filter только у source-panel/target-panel и gauge-disc; внутренний slot не обрезает тень. Пользователь сообщил, что после отключения blur панелей полоса осталась только на колесе, затем снят blur диска. Геометрия, оранжевая зона, анимации сохранены. Точный GPU-артефакт пользователя не гарантированно воспроизводится в автоматизации.
- Testing agent /app/test_reports/iteration_2.json:18/18 unit tests, production build OK, реальные жесты >10s в магазине/инвентаре:0 uncancelled dragstart/pointercancel, клики работают; метаданные/иконки/текст/цвета OK; полоса не наблюдалась при1920×800 + CSS zoom1.5, прокрутке под шапку и смене цели. Пользователь отдельно предупреждал, что широкий вид без прокрутки НЕ повторяет его состояние.
- После отчёта закрыт пробел mobile wheel-test: CDP native touch swipe на390×844 прокрутил scrollY0→728, обычный выбор скина после свайпа работает. Desktop/mobile document overflow пустой. Новый последний фон проверяется отдельно визуально/на загрузку после изменения CSS.

### Текущий backlog
- P0: завершить визуальную/сетевую проверку последнего WebP-фона; остальные последние функции проверены iteration2.
- P1: если полоса снова проявится — профиль конкретного устройства с его масштабом; не возвращать тяжёлые backdrop-фильтры в колесо/preview.
- P2: включить native drag/move тесты в CI; по отдельному запросу обновить архив/патч со всеми изменениями (старый public/fixes/rapid-click.patch содержит только первую итерацию, не последние правк��).
- Backend/финансовая логика/аккаунты в этих визуальных изменениях не менялись. Discord OAuth/платежи в локальной копии не настроены; тестовый JWT см. test_credentials.md. Исторические записи ниже не отражают отменённые новые варианты оформления.

## Актуальная сессия: зависание при быстрых кликах (2026-09-18)
Исходный запрос: исправить зависание мыши при быстрых переходах по вкладкам и выборе/снятии оружия в https://github.com/wghafxx/igogo. Пользователь выбрал определение сценария по коду и основную ветку. Полный исходный запрос, архитектурные решения, изменения, границы проверки и приоритетный backlog: [rapid-click-fix.md](./rapid-click-fix.md).

- Сохранён React/FastAPI/MongoDB и существующий дизайн; backend финансовых операций не менялся.
- Исправлена бесконечно откладываемая разблокировка pointer-events, меню профиля/баланса не захватывают body. Снижены перерисовки и перезапуски аудио; функциональный выбор цели не теряет клики. Каталог сохраняется между вкладками, запросы отменяются при смене фильтров.
- Проверено: 155.8 событий клика/с за 25 с в пакетном браузерном тесте; 120 предметов; 18/18 unit-тестов и 4/4 API smoke; сборка успешна. Полный краш браузера пользователя не воспроизведён — воспроизведена и исправлена блокировка при непрерывных анимациях.
- P0 завершено. P1 — профиль конкретного устройства, если полный краш повторится. P2 — длительный stress-test в CI. Следующий шаг: применить проверенный патч к main; исходный GitHub не изменялся.
- Старые записи ниже — исторический контекст, их заявления о GPU не являются установленной причиной текущего обращения.

## Исходный запрос (сессия 2026-06)
«https://github.com/wghafxx/igogo — 1. Лайв-чат на сайте: при пополнении скинами вместо Roblox-профиля создаётся заявка на примерный RAP и переносится в окно лайв-чата справа снизу; оператор в админ-панели принимает чат и отвечает. Плюс всегда доступный лайв-чат поддержки справа снизу. 2. xRocket перенести во вкладку «Крипта» и добавить CryptoBot по токену.»
Уточнение пользователя: иконки криптовалют — настоящие PNG; логотип CryptoBot — присланная картинка.

## Архитектура
React CRA + FastAPI + MongoDB (supervisor: frontend 3000 / backend 8001). Код импортирован из GitHub (клон в /app). Discord OAuth в preview не настроен (заглушки в backend/.env) — вход пользователя работает только на проде.

## Реализовано (2026-06)
- backend/live_chat.py + маршруты /api/chats* (гости через X-Session-Id, пользователи через JWT) и /api/admin/chats* (список, summary, accept, messages, close). Коллекции chats, chat_messages. Polling (3 c в открытом окне).
- POST /api/chats {kind:"deposit", expected_rap} создаёт deposit (pending, via_chat, chat_id) + чат с сообщением-заявкой. Подтверждение/отклонение депозита в админке пишет системное сообщение в чат.
- Frontend: components/chat/LiveChatWidget.jsx (кнопка + панель справа снизу), hooks/useLiveChat.js, ChatMessages.jsx. TopUpModal: «Скины» → AmountStep → создание чата (ReceiverStep больше не используется). Футер «Поддержка» открывает чат.
- Админка: вкладка «Чаты» (components/admin/ChatsTab.jsx) с фильтрами, принятием, ответами, закрытием и панелью депозита (подтвердить/отклонить); бейдж непринятых/непрочитанных.
- backend/cryptobot_payments.py (Crypto Pay API, fiat RUB invoices, webhook HMAC, reconcile loop) + /api/payments/cryptobot/*; вкладка «Платежи CryptoBot» в админке.
- Выбор монеты плитками (иконки PNG, 4 колонки) и в xRocket, и в CryptoBot; для CryptoBot выбранная монета передаётся как accepted_assets (currency в CryptobotInvoiceIn, по умолчанию USDT).
- TopUpModal: вкладки Скины / ₽ Рубли (только СБП) / Крипта (CryptoBot по умолчанию, xRocket) / Мои заявки. XrocketTopUp.jsx стал универсальным (prop provider). Иконки монет: public/payments/coins/*.png, логотип public/payments/cryptobot.png.
- .env: CRYPTOBOT_API_TOKEN, CRYPTOBOT_TESTNET; сид-фраза админа в memory/test_credentials.md.

- Онлайн: окно присутствия 120 c (было 45), heartbeat при возврате на вкладку, значение не падает ниже 1 и не скачет.
- Лайв-дропы: убрана надпись «Live drops», «Лучший за час» и лента — единый блок (сайдбар и мобильная полоса). Фон сайта — заблюренный dust2 (src/assets/bg-dust2.webp, класс .blox-bg), шапка/сайдбар полупрозрачные с blur.


## Сессия 2026-06 (колесо + /ru /en)
Запрос: колесо красивее (дизайн как референс: тёмное кольцо, вертикальный оранжевый градиент, оранжевая стрелка, без сияния), плавная анимация полоски шанса; автоматические префиксы /ru и /en по стране/языку. Выбор пользователя: определение по языку браузера (бесплатно, без лимитов), часовой пояс СНГ как офлайн-гео-запасной вариант, без платных IP-API.
- components/Gauge.jsx: полупрозрачный «стеклянный» диск (bg-[#0f1015]/80 backdrop-blur-md как шапка/лайв-дроп), тёмный трек, зона — вертикальный градиент #5a1400→#ffc233 с шумовой текстурой, тонкий серый обод, слабые внешние лучи, оранжевый шеврон-стрелка. Зона = две зеркальные dash-дуги, закреплённые в нижней точке → растёт снизу вверх симметрично; transition stroke-dasharray 0.55s (.gauge-zone-arc в index.css).
- lib/locale.js (detectLang/withLang/langFromPath/stripLang), lib/router.jsx (Link/Navigate с префиксом), lib/i18n.js (язык из URL; переключатель меняет префикс), App.js: маршруты /:lang + LangGate + RootRedirect; старые пути редиректятся; /admin и /auth/callback без префикса.
- Проверено testing agent (iteration_6.json): маршрутизация, переключатель, симметричная анимация зоны, backend smoke — всё ок.
- Backlog: P1 hreflang/canonical для /ru и /en; P2 серверный редирект «/».
- Лайв-дроп (2026-06): карточки вплотную друг к другу (divide-y white/10), без цены, крупное фото на градиенте под цвет редкости с полоской снизу (.drop-thumb, --rarity), «Лучший за час» в том же ряду с золотым оттенком (.best-drop-card). Новые дропы появляются с animate.css `animate__bounceInLeft` (useFreshDrops — только реально новые id). Ссылки через lib/router Link. Сид для проверки: backend/tests/seed_drops.py N. Проверено testing agent (iteration_8.json, 100%).
- Баг «кнопки перестают нажиматься»: причина — залипание body{pointer-events:none} от Radix (диалог из DropdownMenu / размонтирование модалки). Исправлено: Header «Пополнить» через onSelect+setTimeout; глобальный components/PointerEventsGuard.jsx в App.js снимает залипший lock, когда нет открытых слоёв. Проверено testing agent (iteration_7.json, 7/7).

## Проверка
- /app/test_reports/iteration_3.json: backend 20/20 (tests/test_iteration_livechat_cryptobot.py), frontend-флоу гостя/админа/модалки пройдены. Старые тесты test_xrocket.py (47) и jest XrocketTopUp/TopUpModal.promo проходят.

## Backlog
P1: указать webhook CryptoBot в приложении (<PUBLIC_APP_URL>/api/payments/cryptobot/webhook) на проде; без него зачисление идёт через фоновую сверку (до ~60 c).
P1: чат гостя не переносится в аккаунт после входа (разные owner).
P2: звук/браузерное уведомление о новом сообщении; WebSocket вместо polling; ReceiverStep.jsx можно удалить.

## Сессия 2026-06 (производительность / зависание)
Запрос: «Долго грузятся изображения, после быстрых перемещений по меню сайт умирает (F5/мышь/клавиатура не отвечают)».
Причины и исправления:
- GPU: полноэкранный фон с `filter: blur(7px)` + полноэкранный `backdrop-filter` + `backdrop-filter` на каждой панели/сайдбаре/колесе → на слабых GPU композитор зависал. Фон теперь заблюрен офлайн (`src/assets/bg-dust2-blur.webp`, 16 KB, скрипт `scripts/optimize_images.py`), полноэкранные blur-слои убраны; по просьбе пользователя «стекло» панелей/сайдбара/колеса возвращено (blur 12px, только ≥1024px, класс .blox-glass), фон с сочностью saturate 1.32 запечён в картинку; убраны `will-change` на 60 карточках дропов, анимация box-shadow в reel, drop-shadow-фильтр на зоне колеса.
- Картинки: 40+ PNG 420×420 (60–110 KB) с bloxstrike.net → локальные WebP 256px (~7–13 KB) в `frontend/public/items/`, маппинг `lib/img.js: skinImg()` (старые URL из БД тоже маппятся), `loading="lazy"`, `decoding="async"`, width/height.
- JS: React.lazy для Tos/Privacy/Profile/PublicProfile/Admin/AuthCallback (+Suspense), лента дропов рендерит только нужный вариант (сайдбар ИЛИ мобильная полоса, `hooks/useMediaQuery`), DropCard memo, `refreshDrops` не обновляет state без изменений, шрифт Rubik через <link> вместо CSS @import, лишний Inter убран.
- Прод: `server.py` отдаёт /static, /items, /payments, /sounds с `Cache-Control: immutable`, index.html — `no-cache`.
- Preview-окружение: backend/.env заполнен заглушками (PUBLIC_APP_URL, DISCORD_*, JWT_SECRET, ADMIN_SEED_HASH); тестовый вход через JWT — см. memory/test_credentials.md.
- Проверено testing agent (iteration_9.json): 100% backend/frontend, 0 запросов к bloxstrike.net, 0 console errors, после 20+ быстрых переходов страница отвечает, pointer-events не залипает.

## Backlog (перф)
P2: заменить polling дропов (5 с) на WebSocket/SSE; P2: source-map-explorer по main.js (282 KB gzip — motion/react + radix); P2: пере-конвертировать изображения при добавлении новых скинов (`python3 scripts/optimize_images.py`).

## 2026-06 — Починка сборки Railway / удаление Emergent
- Убран `emergentintegrations==0.2.0` из backend/requirements.txt (в коде не использовался) — причина падения `pip install` в Dockerfile.
- Удалены все следы Emergent из фронтенда: скрипт `assets.emergent.sh/emergent-main.js` и PostHog (`ap.emergent.sh`) из public/index.html, devDependencies `@emergentbase/*` из package.json, блок visual-edits из craco.config.js, testId `home-emergent-link`.
- Проверено: `pip install -r requirements.txt` в чистом venv, `yarn build`, smoke-тесты backend/frontend (test_reports/iteration_3.json) — всё зелёное.
- Preview: backend/.env заполнен заглушками (Discord OAuth не работает в preview), админ-фраза — см. memory/test_credentials.md.

## 2026-06 — UX-правки
- «Лучший дроп» считается за 24 часа (BEST_DROP_WINDOW в server.py), карточка обновляется автоматически (refreshDrops каждые 5 с + таймер истечения по server_time). Тексты RU/EN обновлены.
- Глобальный запрет выделения текста/изображений и drag на всех страницах (App.css: user-select:none для html/body/*, ::selection прозрачный; App.js: document-level dragstart/selectstart блокировка). Поля ввода остаются редактируемыми.
- Полоса прокрутки страницы скрыта (html scrollbar-width:none + ::-webkit-scrollbar display:none), прокрутка сохранена; фон больше не «прыгает».

## 2026-06 — Чаты как единый центр пополнения/вывода
- Мин. пополнение скинами 200 RAP (backend MIN_DEPOSIT_RAP, ChatCreateIn/DepositIn ge=200, быстрые кнопки 200/250/500/1000/2500, тексты TOS/i18n).
- Лайв-чат: 1 чат на человека (create_chat переиспользует), пользователь может «Завершить чат» и «Открыть заново», кд 3 мин (toggle_at, 429 + Retry-After, таймер в UI). Сообщение в закрытый чат → 409. Виджет переделан в палитру сайта (chat-surface, m-* контролы, кот-аватар), без центрального блока; тосты — стеклянные (.blox-toast).
- Админка: вкладки «Ожидают пополнения/Зачислено/Отклонено/Отменённые/Выводы» удалены. Вкладка «Чаты» — консоль: список (поиск по нику/Discord/Roblox, фильтры, зелёная точка онлайна у ника, «ждёт N мин», баланс; сортировка — кто дольше ждёт первым), диалог, карточка игрока + «Пополнение скинами» (preview/confirm через confirm_deposit → банк) + «Вывод скинов» (сгруппировано, итог, «Всё выдано», отмена по одному с причиной). Endpoints: /admin/search, /admin/chats/{id}/deposit[/preview], /admin/chats/{id}/withdrawals/done, /chats/{id}/close|reopen. Presence — из коллекции presence (120 с).
- animate.css: плавные fadeIn для секций/лайв-дропа, тюнинг длительности, hover-эффекты карточек, prefers-reduced-motion.
