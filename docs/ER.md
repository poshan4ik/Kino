# ER-диаграмма (Mermaid)

```mermaid
erDiagram
    User ||--o{ Booking : "бронирует"
    User ||--o{ Review : "оставляет"
    User ||--o{ Favorite : "избранное"
    User ||--o{ AuditLog : "действия"

    Genre ||--o{ Movie : "содержит"

    Movie ||--o{ Session : "сеансы"
    Movie ||--o{ Review : "отзывы"
    Movie ||--o{ Favorite : "избранное"

    Hall ||--o{ Seat : "места"
    Hall ||--o{ Session : "зал"

    Session ||--o{ Booking : "брони"

    Seat ||--o{ Booking : "место"

    Booking ||--o| Ticket : "1 к 1 (после оплаты)"
    Ticket ||--o{ Payment : "платежи"

    User {
        int id PK
        string username UK
        string role "client|cashier|controller|manager|admin"
        string phone
        bool is_active
    }
    Genre {
        int id PK
        string name UK
    }
    Movie {
        int id PK
        string title
        int genre_id FK
        int duration "мин"
        int age_rating
        string status "draft|upcoming|active|archived"
        string poster
    }
    Hall {
        int id PK
        int number UK
        string type "2D|3D|IMAX|VIP"
        int capacity
    }
    Seat {
        int id PK
        int hall_id FK
        int row
        int number
        string category "standard|comfort|vip"
    }
    Session {
        int id PK
        int movie_id FK
        int hall_id FK
        date date
        time time
        decimal price_standard
        decimal price_comfort
        decimal price_vip
        bool is_active
    }
    Booking {
        int id PK
        int client_id FK
        int session_id FK
        int seat_id FK
        string status "created|pending_payment|paid|used|cancelled|expired"
        datetime expires_at "холд ~15 мин"
    }
    Ticket {
        int id PK
        int booking_id FK UK "OneToOne"
        decimal price
        string barcode UK
        string status "active|used|refunded|cancelled"
        datetime used_at
    }
    Payment {
        int id PK
        int ticket_id FK
        decimal amount
        string method "cash|card|online"
        string status "pending|completed|failed|refunded"
        datetime completed_at
    }
    Review {
        int id PK
        int user_id FK
        int movie_id FK
        int rating "1..5"
    }
    Favorite {
        int id PK
        int user_id FK
        int movie_id FK
    }
    AuditLog {
        int id PK
        int user_id FK
        string action
        string details
    }
```

## Ключевые ограничения

| Ограничение | Где |
|---|---|
| Одна активная бронь на пару (session, seat) — `UniqueConstraint` по активным статусам | `Booking.Meta` |
| Один отзыв на пользователя на фильм — `UniqueConstraint(user, movie)` | `Review.Meta` |
| OneToOne: бронь → билет | `Ticket.booking` |
| `Session.clean`: пересечение сеансов в зале запрещено (конец одного ≤ начала следующего), буфер `SESSION_BUFFER_MINUTES` (по умолчанию 20 мин) | `Session.clean` |
| Холд мест: `BOOKING_MAX_SEATS=10` за раз, `BOOKING_HOLD_MINUTES=15`, «всё или ничего» атомарно (`select_for_update`) | `cinema/services.py` |

## Статусная машина брони

```
created ──→ pending_payment ──→ paid ──→ used
    │              │               │
    ▼              ▼               ▼
 expired        cancelled      cancelled (возврат → Ticket.refunded,
 (истёк холд)   (отмена)        Payment.refunded)
```
