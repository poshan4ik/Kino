# API (v1, префикс `/api/`)

Swagger: `/api/docs/` · Схема OpenAPI: `/api/schema/` · Health: `/health/`

Аутентификация: сессионная (cookies) или `Authorization: Bearer` (JWT не настроен — используется сессионная; DRF-проверка `IsAuthenticated`).

Троттлинги: аноним 60/мин, пользователь 120/мин, логин 10/5мин, регистрация 5/10мин.

## Эндпоинты

| Метод | Путь | Доступ | Описание |
|---|---|---|---|
| GET | `/api/users/me/` | авторизован | текущий пользователь |
| PATCH | `/api/users/update_me/` | авторизован | своё имя/email/телефон (**role read-only**) |
| GET/POST,GET/PATCH/DELETE | `/api/users/` | менеджер/админ | CRUD пользователей (role пишется здесь) |
| GET | `/api/genres/` | публично | жанры |
| GET | `/api/movies/` | публично | фильмы (фильтры: genre,status,age_rating; поиск, сортировка) |
| POST,PATCH,DELETE | `/api/movies/` | менеджер/админ | управление фильмами |
| GET | `/api/movies/{id}/sessions/` | публично | будущие сеансы фильма |
| GET | `/api/movies/{id}/reviews/` | публично | рейтинг и отзывы |
| GET | `/api/halls/` | публично | залы |
| POST | `/api/halls/{id}/generate_seats/` | менеджер/админ | генерация мест |
| GET | `/api/sessions/` | публично | сеансы (фильтры: movie,hall,date,is_active) |
| GET | `/api/sessions/{id}/seats/` | публично | схема мест с ценами и занятостью |
| GET | `/api/bookings/` | авторизован | свои брони (персонал — все) |
| POST | `/api/bookings/` | авторизован | создать бронь (устаревшее — используйте hold) |
| POST | `/api/bookings/hold/` | авторизован | атомарный холд мест: `{session, seats:[id]}` → 201/400/404 |
| POST | `/api/bookings/pay/` | авторизован | оплата: `{booking_ids:[…], method}` → билеты 201 |
| POST | `/api/bookings/{id}/confirm_payment/` | кассир+ | кассовое подтверждение оплаты |
| POST | `/api/bookings/{id}/cancel/` | кассир+ | отмена брони (персонал) |
| POST | `/api/bookings/{id}/cancel_own/` | владелец | отмена своей брони до сеанса |
| POST | `/api/bookings/{id}/refund/` | кассир/менеджер/админ | возврат: билет/платежи → refunded |
| POST | `/api/bookings/expire_old/` | кассир+ | принудительный expire истёкших холдов |
| GET | `/api/tickets/` | авторизован | свои билеты |
| POST | `/api/tickets/{barcode}/validate_ticket/` | контролёр+ | разовая проверка/вход |
| POST | `/api/tickets/check_by_barcode/` | контролёр+ | поиск и погашение по штрихкоду |
| GET | `/api/payments/` | авторизован | свои платежи |
| GET | `/api/dashboard/stats/` | менеджер/админ | KPI, график 7 дней, загрузка залов |
| GET | `/api/dashboard/sales_report/` | менеджер/админ | отчёт по фильмам/залам/способам, `?date_from=&date_to=` |
| GET | `/api/favorites/` | авторизован | избранное |
| POST/DELETE | `/api/favorites/{movie_id}/` | авторизован | добавить/убрать |
| POST | `/api/reviews/` | авторизован | отзыв/оценка (одна на фильм, 1–5) |

## Коды ошибок

- `400` — бизнес-ошибка (место занято, лимит мест, сеанс начался, холд истёк, неверный статус)
- `401/403` — не авторизован / нет роли
- `404` — ресурс не найден или чужой (для клиента брони других пользователей не видны)
- `429` — превышен троттлинг

## Примеры

```bash
# Холд двух мест
curl -X POST /api/bookings/hold/ -H 'Content-Type: application/json' \
  -d '{"session": 12, "seats": [101, 102]}'

# Оплата онлайн
curl -X POST /api/bookings/pay/ -H 'Content-Type: application/json' \
  -d '{"booking_ids": [5, 6], "method": "online"}'

# Возврат (кассир)
curl -X POST /api/bookings/5/refund/
```
