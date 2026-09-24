# BLOXGRADE — PRD / состояние

## Сессия 8 (2026-09-24): /staff = консоль чатов как у админа
Запрос: «/staff неудобный — нужен точно такой же чат как у админ, запрет к выводам скинов, убрать передачи, пусть берёт сколько угодно чатов, каждая выдача RAP — только с приложенным скрином трейда».
- /staff: ChatSidebar + Conversation (переиспользованы из админки, быстрые команды read-only) + карточка игрока + «Пополнение скинами» (предметы, скрин трейда обязателен, отметки → «Отправить на подтверждение»). Вывода скинов и начисления монет нет.
- Backend: /api/staff/chats, /summary, /{id}/messages|accept|close|attachments|evidence|report|return, /api/staff/commands. Чат закрепляется за сотрудником атомарно (chats.staff_id); видны свободные чаты и свои; лимита нет. Заявка создаётся по требованию при загрузке скрина/отчёта. Решение о зачислении по-прежнему принимает владелец (Telegram или /admin).
- Передачи владельцу убраны из кабинета (POST /api/staff/transfers удалён).

## Сессия 7 (2026-09-23): блокер сборки Railway + модуль сотрудников с подтверждением через Telegram
Исходный запрос: найден блокер сборки на f5e172c — Dockerfile копирует frontend/yarn.lock, которого нет в Git. Затем: приём скинов сотрудниками (/staff), отчёты со скриншотами, решение владельца в Telegram/в /admin, учёт реальных скинов, смены, статистика, защита от двойного зачисления, сохранность при сбросе экономики. «Без лишних вопросов изучай и делай».

### Сборка
- Причина: автокоммит Emergent не включает yarn.lock (в .gitignore он не исключён). frontend/yarn.lock сгенерирован под текущий package.json (`yarn install --frozen-lockfile` → up-to-date) и закоммичен явно.
- Dockerfile: `COPY frontend/package.json frontend/yarn.lock* ./`; при наличии lockfile — `--frozen-lockfile`, без него — обычная установка с предупреждением (COPY больше не падает).

- Повторный отказ Railway (лог со старой строкой `COPY ... yarn.lock ./` без `*`): собирался старый снимок/Redeploy старого деплоя. Чистая сборка GitHub HEAD проходит (yarn --frozen-lockfile, yarn build, pip). Найден второй блокер: в requirements.txt не было python-multipart → сервер падал при старте в чистом образе; добавлен python-multipart==0.0.32, запуск uvicorn из чистого venv проверен (/api/health 200).

### Модуль сотрудников (backend)
- staff_core.py: сотрудники (по Discord ID + Roblox-аккаунт приёма), атомарное взятие заявки, неизменяемые версии отчётов (staff_reports), approve/revision/reject с блокировкой через deposits.staff_state="review" и staff_report_id, возвраты и передачи (staff_moves), audit (staff_audit), восстановление после сбоя, хук сброса экономики (staff_manual, отмена очереди Telegram).
- Зачисление: план из отчёта → deposits processing → существующий settle_deposit (идемпотентный, продолжается при старте).
- staff_evidence.py: GridFS bucket staff_evidence, PNG/JPEG по сигнатуре, ≤5 МБ, 1–6 на отчёт, доступ — владелец и загрузивший сотрудник.
- staff_shifts.py: одна открытая смена (unique partial index is_open), паузы, heartbeat/потеря связи, флаг >12 ч, исправление владельцем с причиной, дни Asia/Qyzylorda с разбиением через полночь.
- staff_stats.py: принято/одобрено/обработано/на проверке/доработка/отклонено/передано/возвращено/остаток/время за сегодня, период, всё время.
- staff_telegram.py: отдельный бот (STAFF_TG_BOT_TOKEN, STAFF_TG_OWNER_ID, STAFF_TG_WEBHOOK_SECRET), outbox с повтором и backoff, альбом скриншотов (фолбэк — документы) + карточка с кнопками Подтвердить (2 шага) / На доработку / Отклонить (причина force_reply), только from.id и chat.id владельца, дедуп update_id, устаревшие кнопки отклоняются. Если токен совпадает с TELEGRAM_BOT_TOKEN (DonationAlerts) — «общий режим»: обновления приходят на /api/telegram/webhook и делегируются.
- staff_routes.py: /api/staff/*, /api/admin/staff*, /api/admin/staff-reviews|staff-reports|staff-moves|staff-shifts|staff-evidence|staff-manual|staff-audit|staff-telegram, /api/staff-telegram/webhook.
- server.py: старые маршруты подтверждения/отклонения (deposits confirm/reject, chat deposit) отдают 409 для заявок сотрудников; отмена игроком — только до начала передачи.

### Frontend
- /staff (StaffPage): смена, очередь, мои заявки, рабочее место (чат + пошаговый отчёт на Stepper), возврат, передачи, статистика.
- /admin → «Сотрудники»: проверка (отчёты, передачи/возвраты, ждут возврата, ручной разбор), сотрудники и учёт (добавление, отключение, статистика с периодами и переходами, исправление смен), карточка Telegram.

### Проверка
- test_reports/iteration_4.json: backend 15/15 (backend/tests/test_staff_intake.py), frontend 100%.
- Telegram-доставка в preview отключена (без STAFF_TG_OWNER_ID), живую отправку/кнопки не проверяли.

### Backlog
- P0: на Railway задать STAFF_TG_* и проверить полный сценарий с телефона.
- P1: создать отдельного бота в @BotFather (сейчас выдан токен @BloxGrade_bot — это бот DonationAlerts).
- P2: переназначение заявки другому сотруднику; уведомление в Telegram о передачах и возвратах; не показывать отрицательный остаток (показывать отметку «Расхождение»).

(История прошлых сессий — в git-истории этого файла.)
