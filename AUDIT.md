# AUDIT.md — аудит АИС «Аврора» (этап 0)

Дата: 13.10.2026 · Django 4.2 · Python 3.14 (локально) · SQLite

## Команды этапа 0

| Команда | Результат |
|---|---|
| `manage.py check` | 0 issues |
| `manage.py makemigrations --check --dry-run` | No changes detected |
| `manage.py migrate` на чистой SQLite | OK, 22 таблицы |
| `runserver` | OK, главная 200 |

## Критично

1. **Эскалирование привилегий через `PATCH /api/users/update_me/`** — подтверждено экспериментально: клиент шлёт `{"role": "admin"}` и становится админом (UserSerializer: `role` writable, экшн доступен любому аутентифицированному).
2. **Анонимное создание админа через `POST /api/users/`** — подтверждено: `role` входит в поля `UserCreateSerializer`, create-действие `AllowAny`; аноним создаёт пользователя с ролью `admin` (201).
3. **Бронирование прошедшего сеанса** — подтверждено: `POST /api/bookings/hold/` успешно бронирует сеанс с `date < today` (нет проверки времени начала ни в hold, ни в `BookingCreateSerializer`, ни в HTML-POST).
4. **Клиент видит всех пользователей** — `GET /api/users/` (list/retrieve) доступен любому аутентифицированному: видны username/email/телефоны всех (подтверждено: 200, 7 записей).
5. **Нет возврата билетов** — статусы `refunded` у Ticket и Payment существуют, но ни одна вьюха их не выставляет; `cancel` аннулирует билет, но не возвращает деньги/статус платежа.

## Важно

6. **Лимит мест разный**: API `hold`/`pay` — 6, HTML-booking — 8; в ТЗ/плане — единый настраиваемый (напр. 10). Нет настройки в settings.
7. **Буфер уборки зашит в код**: `Session.clean` — `+20` минут хардкодом; требуется настраиваемая переменная; сравнение naive-дат при `USE_TZ=True`.
8. **`date.today()` вместо `timezone.localdate()`** во всех вьюхах (HomeView, CashierView, ManagerView, Dashboard…) — при `USE_TZ=True` и переносе TIME_ZONE на Asia/Almaty отчёты/фильтры будут «уплывать».
9. **N+1 в `GET /api/movies/`**: 47 запросов на страницу — `MovieListSerializer.get_next_sessions` делает запрос на фильм (+ `hall` без select_related). Предупреждение `UnorderedObjectListWarning` (пагинация).
10. **N+1 в дашборде менеджера**: `s.hall.seats.count()` в цикле по сеансам (`/manager/` — 30 запросов).
11. **`GET /api/users/` без ordering** — пагинация DRF предупреждает о неконсистентности (нет `Meta.ordering` у User).
12. **Нет throttling DRF** (аноним/юзер, отдельно строже на логин/регистрацию) и **нет `/health/`**.
13. **Нет Whitenoise/сбора статики для прода**: `STATIC_ROOT` есть, middleware нет; медиа только через DEBUG-статику.
14. **Нет Security-флагов при DEBUG=False**: SSL-redirect, secure cookies, HSTS, `X_FRAME_OPTIONS`, `CSRF_TRUSTED_ORIGINS`.
15. **Нет логирования**.
16. **requirements.txt неполный**: нет Pillow (обязателен для ImageField — чистая установка падает), whitenoise, coverage, drf-spectacular, dj-database-url; версии не зафиксированы.
17. **README не соответствует реальности**: заявлены Bootstrap 5 и Chart.js — в шаблонах их нет (grep: 0 совпадений); упомянут `fixtures/initial_data.json` — файла нет; нет staff-страниц `templates/staff/`, `staff_base.html`, admin-темы, `staff.js`, 404/500, `.env.example` в дереве.
18. **Нет LICENSE** (README обещает MIT).
19. **Отсутствуют функции**: `seed_demo`, экспорт CSV, смена пароля/редактирование профиля из кабинета, Swagger (`/api/docs/`), `ensure_admin` для деплоя.
20. **Дубли лимитов/validation**: логика «удержания» продублирована в трёх местах (`hold`, HTML POST, `BookingCreateSerializer.create`) — расхождения уже случились (п.6).

## Мелочи

21. Мёртвый код: `IsClientOrReadOnly`, `ReadOnly`, `IsAdmin` из `permissions.py` импортируются в views, но не используются.
22. `Session.clean` не учитывает сеансы, пересекающие полночь (фильтр по `date=self.date`).
23. `expire_bookings`: `update()` не снимает `expires_at`; команда не журналируется в AuditLog.
24. `DashboardViewSet.stats` — цикл из 14 отдельных агрегирующих запросов (7 дней × revenue+tickets) — можно одним группированным.
25. `GenreSerializer.get_movies_count` — count() на жанр (N+1 на `/api/genres/`, масштаб мал).
26. `RegisterForm.clean_phone` пропускает и `7…` и `+7…`, но и 11 цифр без `+` — терпимо.
27. `MovieViewSet.queryset` и `get_queryset` дублируются (первый не используется роутером при переопределении).
28. Python 3.14 + Django 4.2: официально не поддерживается (нужен monkeypatch `BaseContext.__copy__` для test-клиента). Для прода фиксировать Python 3.11/3.12.

## N+1 — замеры (CaptureQueriesContext)

| Страница | Запросов | Вердикт |
|---|---:|---|
| `GET /` (аноним) | 5 | норма |
| `GET /` (клиент) | 11 | норма |
| `GET /profile/` | 8 | норма |
| `GET /movie/1/` | 10 | норма |
| `GET /booking/1/` | 9 | норма |
| `GET /manager/` | 30 | N+1: seats.count() в цикле |
| `GET /manager/reports/` | 8 | норма |
| `GET /api/movies/` | 47 | N+1: next_sessions на фильм |
| `GET /api/sessions/` | 8 | норма |

## Отсутствующие файлы (упомянуты или требуются)

- `LICENSE` (MIT)
- `fixtures/initial_data.json` (упомянут в README) → заменяется `seed_demo`
- `Pillow` в requirements (ImageField)
- `Procfile` / `render.yaml` / `Dockerfile` / `docker-compose.yml` / `build.sh` / `.python-version`
- `docs/` (ER, ROLES, API), `CHANGELOG.md`
- `/health/`, `/api/docs/` (Swagger)
