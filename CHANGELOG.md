# Changelog

## [Unreleased] — полный аудит и доработка (Этапы 0–8)

### Этап 0 — Аудит
- `AUDIT.md`: критичные уязвимости (PATCH role→admin, анонимный POST /api/users/, hold на прошедший сеанс, утечка чужих данных, отсутствие возврата), N+1 в `/api/movies/` и дашборде, ложь в README (Bootstrap/Chart.js, fixtures).

### Этап 1 — Репозиторий
- `requirements.txt` с полными пинами, расширенный `.env.example`, `LICENSE` (MIT), честный `README.md`, `.gitignore`.

### Этап 2 — Settings и безопасность
- Все секреты/хосты/БД через env (`DJANGO_SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `DATABASE_URL`), `dj-database-url`, WhiteNoise, security-блок при DEBUG=False (SSL, secure-cookies, HSTS), DRF: пагинация, троттлинги, `IsAuthenticated` по умолчанию, Swagger (`/api/docs/`), логирование, бизнес-лимиты в settings.
- `/health/` с проверкой БД, троттлинг логина/регистрации.
- `TIME_ZONE=Asia/Almaty`, `timezone.localdate()` вместо `date.today()`.

### Этап 3 — Логика и баги
- Новый `cinema/services.py`: атомарный холд («всё или ничего», `select_for_update`), отмена, возврат (нельзя после начала сеанса), единые проверки (прошедший сеанс, лимит мест, принадлежность залу).
- `role`/`is_active` read-only для пользователя; `UserAdminSerializer` для staff-CRUD.
- Дашборд: 7-дневный график 2 агрегатами вместо 14 запросов; `/api/movies/` без N+1 (prefetch сеансов).
- `IsCashierRole`: confirm_payment/cancel/refund/expire_old — без контролёра.
- `Session.clean`: буфер `SESSION_BUFFER_MINUTES` из настроек.

### Этап 4 — Недостающие функции
- Возврат билетов (`refund`), отмена своей брони (`cancel_own` + кнопка в профиле), смена пароля и редактирование профиля в личном кабинете.
- Отчёты: период `?date_from=&date_to=`, CSV-экспорт (`/manager/reports/export/`, UTF-8 BOM, `;`).
- Команды `seed_demo` (идемпотентный демо-набор с выводом паролей) и `ensure_admin` (суперпользователь из env, без пароля в коде).

### Этап 5 — Тесты
- 57 тестов (было 17): регресс безопасности, гонка броней, оплата/повторная/возврат, проверка билетов, дашборд/отчёты, профиль, seed_demo, матрица ролей.
- Coverage по `cinema/`: **82%** (цель ≥75%).
- QA-батареи: smoke 46/46, control 62/62.

### Этап 6 — Фронтенд
- Легенда схемы зала, loading-состояния («Бронируем…», «Оплата…»), адаптив 1280→375, чистка CSS/JS.
- `MAX_SEATS` синхронизирован с сервером (10) через context processor.

### Этап 7 — Деплой
- `build.sh`, `Procfile` (web+release), `render.yaml` (web+postgres, генерация секрета), `.python-version`, `Dockerfile`, `docker-compose.yml`.
- `check --deploy --fail-level ERROR` — 0 ошибок; `collectstatic` проходит (WhiteNoise).

### Этап 8 — Документация
- `docs/ER.md` (Mermaid ER + статусная машина), `docs/ROLES.md` (матрица прав), `docs/API.md`, этот `CHANGELOG.md`.

### Исправленные критичные уязвимости
1. `PATCH /api/users/update_me/` больше не меняет `role` (read-only).
2. Анонимный `POST /api/users/` закрыт (create только staff, троттлинг auth).
3. Hold на прошедший сеанс отклоняется.
4. Клиент больше не видит чужие брони/билеты/пользователей.
5. Возврат билета реализован (`refund`) с проверками и аудитом.
