# Модели данных — АИС «Аврора»

Источник истины: `cinema/models.py`.

## Статусы и переходы (единое место правил)

Правила переходов заданы словарём `STATUS_TRANSITIONS` в `cinema/models.py`.
Любой переход статуса выполняется только через `set_status()` (миксин
`StatusTransitionMixin`); недопустимый переход поднимает `ValidationError`.

```
Бронь (booking):   created → pending_payment → paid → used
                   created/pending_payment → cancelled/expired
                   paid → cancelled (возврат)
Билет (ticket):    active → used / refunded / cancelled
Платёж (payment):  pending → completed / failed / refunded
                   completed → refunded
```

Терминальные статусы (`used`, `cancelled`, `expired`, `refunded`, `failed`)
переходов не имеют.

## Схема связей

```
Genre 1──∞ Movie 1──∞ Session ∞──1 Hall 1──∞ Seat
                  │                │
                  │                └──∞ Booking ∞──1 User (client)
                  │                        │  OneToOne
                  │                        └── Ticket 1──∞ Payment
                  └──∞ Review ∞──1 User    Ticket ∞──∞ User (favorites через Movie)

User 1──∞ AuditLog
```

## Модели

### User (`AbstractUser`)
Поля: `role` (client/cashier/controller/manager/admin), `phone`.
Связи: `bookings`, `favorites`, `reviews`, `audit_logs`.
Хелперы: `is_client/is_cashier/is_controller/is_manager/is_admin`.

### Genre
`name` (unique), `description`. Связь: `movies` (1→∞).

### Movie
`title`, `genre` (FK→Genre, PROTECT), `duration` (мин, ≥1),
`age_rating` (0–21), `description`, `poster`, `trailer_url`,
`status` (draft/active/ended/upcoming), `created_at`, `updated_at`.
Ограничения: `duration ≥ 1`, `0 ≤ age_rating ≤ 21`.
Связи: `sessions` (1→∞), `reviews`, `favorited_by`.

### Hall
`number` (unique), `type` (2D/3D/VIP/IMAX), `capacity` (≥1), `description`.
Связи: `seats`, `sessions`. Метод `generate_seats()`.

### Seat
`hall` (FK), `row`, `number`, `category` (standard/comfort/vip).
Уникальность: `(hall, row, number)`.

### Session
`movie` (FK), `hall` (FK), `date`, `time`, `duration_min` (снимок
длительности фильма), `price_standard/price_comfort/price_vip`
(DecimalField, ≥0), `is_active`, `created_at`.
Ограничения БД: цены ≥0, `duration_min ≥ 1` (конец сеанса > начала),
`unique(hall, date, time)`.
Индексы: `(date, time)`, `(is_active, date)`, `(movie, date)`.
`clean()`: пересечение сеансов в зале (конец одного = начало другого
допустимо; учитывается буфер `SESSION_BUFFER_MINUTES`).
`save()` заполняет `duration_min` из фильма, если не задан.

### Booking
`client` (FK→User), `session` (FK), `seat` (FK),
`status` (**BookingStatus** TextChoices), `created_at`, `expires_at`.
Ограничения БД: `unique(session, seat)` для активных статусов
(created/pending_payment/paid/used).
Индексы: `(status, created_at)`, `(expires_at)`.
Методы: `is_expired()`, `expire()` (pending→expired через `set_status`).

### Ticket
`booking` (OneToOne), `price` (DecimalField, фиксируется на момент
покупки, ≥0), `barcode` (unique), `status` (**TicketStatus**),
`issued_at`, `used_at`.
Индекс: `(status, issued_at)`.
Метод: `mark_used()` — `active→used` (+ бронь `paid→used`).

### Payment
`ticket` (FK), `amount` (DecimalField, ≥0), `method` (cash/card/online),
`status` (**PaymentStatus**), `transaction_id`, `created_at`, `completed_at`.
Индекс: `(status, created_at)`.

### AuditLog
`user` (FK, SET_NULL, nullable), `action`, `details`, `created_at`.
Индексы: `(-created_at)`, `(action, -created_at)`.
Фабрика: `log_audit(user, action, details)` — не роняет основную операцию.

### Favorite
`user` (FK), `movie` (FK), `created_at`. Уникальность: `(user, movie)`.

### Review
`user` (FK), `movie` (FK), `rating` (1–5), `comment`, `created_at`.
Уникальность: `(user, movie)`; ограничение `1 ≤ rating ≤ 5`.
