# АИС «Аврора» — Автоматизированная информационная система кинотеатра

Полноценный веб-проект на Django + DRF + Bootstrap 5 с кастомной дизайн-системой.

## 🎬 Функционал

- **Афиша фильмов** — публичная страница с поиском и фильтрами по жанру/дате
- **Бронирование мест** — интерактивная схема зала с выбором мест
- **Касса кассира** — быстрый поиск сеансов, продажа/возврат билетов
- **Контроль билетов** — сканирование штрихкодов, проверка действительности
- **Панель менеджера** — дашборд с метриками, графики продаж, загрузка залов
- **Личный кабинет клиента** — история броней, билеты, платежи
- **Админка Django** — полное управление всеми сущностями

## 👥 Роли пользователей

| Роль | Права |
|------|-------|
| **Клиент** | Просмотр афиши, бронирование, покупка билетов, личный кабинет |
| **Кассир** | Поиск сеансов, продажа билетов кассой, возврат билетов |
| **Контролёр** | Проверка билетов по штрихкоду, контроль входа |
| **Менеджер** | CRUD фильмов/жанров/залов, дашборд, отчёты |
| **Администратор** | Полный доступ, управление пользователями |

## 🛠 Стек технологий

- **Backend**: Python 3.11+, Django 4.2, Django REST Framework 3.14
- **Database**: PostgreSQL (продакшн) / SQLite (разработка)
- **Frontend**: Django Templates, Bootstrap 5, Chart.js
- **Auth**: Session + Token Authentication
- **Deployment**: Gunicorn, Nginx (рекомендуется)

## 📁 Структура проекта

```
cinema_project/
├── cinema_project/          # Настройки Django
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── cinema/                  # Основное приложение
│   ├── models.py           # Все модели данных
│   ├── views.py            # DRF ViewSets
│   ├── serializers.py      # DRF Serializers
│   ├── permissions.py      # Кастомные permissions
│   ├── urls.py             # API маршруты
│   ├── admin.py            # Админка
│   ├── apps.py
│   └── migrations/
├── templates/               # Django шаблоны
│   ├── base.html           # Базовый шаблон с дизайн-системой
│   ├── home.html           # Афиша
│   ├── movie_detail.html   # Страница фильма
│   ├── booking.html        # Выбор мест
│   ├── profile.html        # Личный кабинет
│   ├── cashier.html        # Касса
│   ├── controller.html     # Контроль билетов
│   ├── manager.html        # Панель менеджера
│   ├── login.html          # Вход
│   └── register.html       # Регистрация
├── static/
│   ├── css/main.css        # Кастомные стили (дизайн-система)
│   └── js/main.js          # Клиентский JS
├── media/                   # Загруженные файлы (постеры)
├── manage.py
├── requirements.txt
├── .env                     # Переменные окружения
└── README.md
```

## 🚀 Быстрый старт

### 1. Клонирование и окружение

```bash
git clone <repository-url>
cd cinema_project

# Создание виртуального окружения
python -m venv venv
source venv/bin/activate  # Linux/macOS
# или
venv\Scripts\activate     # Windows

# Установка зависимостей
pip install -r requirements.txt
```

### 2. Настройка переменных окружения

Скопируйте `.env.example` в `.env` и отредактируйте:

```bash
cp .env.example .env
```

Основные переменные:
```env
DJANGO_SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Для PostgreSQL (продакшн)
USE_SQLITE=False
POSTGRES_DB=cinema_db
POSTGRES_USER=cinema_user
POSTGRES_PASSWORD=secure_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

### 3. Миграции и суперпользователь

```bash
# Применение миграций
python manage.py migrate

# Создание суперпользователя (администратор)
python manage.py createsuperuser

# (Опционально) Загрузка тестовых данных
python manage.py loaddata fixtures/initial_data.json
```

### 4. Запуск сервера разработки

```bash
python manage.py runserver
```

Откройте http://127.0.0.1:8000/

## 🔧 Команды управления

```bash
# Проверка проекта
python manage.py check

# Создание миграций после изменений моделей
python manage.py makemigrations cinema

# Сбор статики (для продакшена)
python manage.py collectstatic

# Запуск тестов
python manage.py test

# Очистка просроченных броней (можно добавить в cron)
python manage.py expire_bookings
```

## 🌐 API Endpoints

Базовый URL: `/api/`

### Публичные (без авторизации)
- `GET /api/genres/` — список жанров
- `GET /api/movies/` — список фильмов (с фильтрами `?genre=&status=&search=`)
- `GET /api/movies/{id}/` — детали фильма
- `GET /api/movies/{id}/sessions/` — сеансы фильма
- `GET /api/halls/` — список залов
- `GET /api/sessions/` — сеансы (фильтры `?date_from=&date_to=&movie=&hall=`)
- `GET /api/sessions/by_date/?date=2024-01-15` — сеансы на дату
- `GET /api/sessions/{id}/seats/` — схема зала для сеанса

### Авторизованные (токен/сессия)
- `GET /api/users/me/` — профиль текущего пользователя
- `PATCH /api/users/update_me/` — обновление профиля
- `POST /api/bookings/` — создание бронирования
- `GET /api/bookings/` — мои бронирования
- `POST /api/bookings/{id}/confirm_payment/` — оплата (кассир+)
- `POST /api/bookings/{id}/cancel/` — отмена брони
- `POST /api/bookings/expire_old/` — автоотмена старых (кассир+)
- `GET /api/tickets/` — мои билеты
- `POST /api/tickets/check_by_barcode/` — проверка билета (контролёр+)
- `POST /api/payments/` — создание платежа (кассир+)

### Менеджер/Админ
- `GET /api/dashboard/stats/` — метрики дашборда
- `GET /api/dashboard/sales_report/` — отчёт по продажам
- CRUD для: `/api/movies/`, `/api/genres/`, `/api/halls/`, `/api/seats/`, `/api/sessions/`

## 🎨 Дизайн-система

CSS-переменные (в `static/css/main.css`):

```css
:root {
  --bg: #14151a;          /* фон страницы */
  --surface: #1f212b;      /* карточки */
  --surface-2: #262935;    /* карточки hover */
  --border: #31353f;
  --text: #f4f3f0;
  --text-muted: #9195a3;
  --red: #e5304c;          /* основной акцент */
  --red-dim: #b8253c;      /* hover для красного */
  --gold: #eeb84a;         /* вторичный акцент */
}
```

Шрифты:
- **Bebas Neue** — заголовки, логотип, названия фильмов
- **Inter** — основной текст, UI

Компоненты:
- `.session-pill` — пилюля-кнопка (border-radius: 999px)
- `.film-card` — карточка фильма (border-radius: 14px)
- `.seat` — место в схеме зала
- `.badge-status-*` — цветные бейджи статусов

## 📊 Админка

Доступна по `/admin/`. Все модели зарегистрированы с удобными фильтрами, поиском и действиями:
- Автогенерация мест для залов
- Массовое изменение статусов
- Фильтры по датам, ролям, статусам

## 🔒 Безопасность

- CSRF защита на всех формах
- Разграничение доступа по ролям (DRF permissions + template tags)
- Уникальные ограничения на уровне БД (место + сеанс)
- Валидация пересечения сеансов в зале
- Автоотмена броней по таймауту (15 мин)
- Хеширование паролей (PBKDF2)

## 🧪 Тестирование

```bash
# Запуск всех тестов
python manage.py test

# Конкретное приложение
python manage.py test cinema
```

## 📦 Деплой (Production)

1. Настройте PostgreSQL
2. Установите `USE_SQLITE=False` в `.env`
3. Сгенерируйте `DJANGO_SECRET_KEY`
4. Настройте `ALLOWED_HOSTS`
5. Соберите статику: `python manage.py collectstatic`
6. Настройте Gunicorn + Nginx
7. Настройте SSL (Let's Encrypt)
8. Добавьте cron для `expire_bookings`

## 📄 Лицензия

MIT License — свободное использование, модификация и распространение.

---

**АИС «Аврора»** — современное решение для автоматизации кинотеатра 🎬