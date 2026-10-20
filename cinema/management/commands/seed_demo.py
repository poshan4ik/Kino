"""Идемпотентное наполнение демо-данными: роли, жанры, фильмы с постерами, залы, сеансы, брони."""
from datetime import datetime, time, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from cinema.models import Booking, Genre, Hall, Movie, Review, Session, Ticket, TicketType, User

DEMO_USERS = [
    ('admin', 'admin12345', 'admin', 'Администратор', 'Демо'),
    ('client', 'client12345', 'client', 'Тест', 'Клиент'),
    ('demo', 'demo12345', 'client', 'Демо', 'Пользователь'),
    ('cashier', 'cashier12345', 'cashier', 'Кассир', 'Демо'),
    ('controller', 'controller12345', 'controller', 'Контролёр', 'Демо'),
    ('manager', 'manager12345', 'manager', 'Менеджер', 'Демо'),
]

DEMO_GENRES = [
    'Боевик', 'Комедия', 'Драма', 'Фантастика', 'Триллер', 'Мультфильм', 'Приключения', 'Ужасы',
]

DEMO_MOVIES = [
    # (title, genre, duration, age_rating, status, trailer)
    ('Дюна: Часть вторая', 'Фантастика', 166, 12, 'active',
     'https://www.youtube.com/watch?v=Way9Dexny3w'),
    ('Oppenheimer', 'Драма', 180, 18, 'active',
     'https://www.youtube.com/watch?v=uYPbbksJxIg'),
    ('Человек-паук: Паутина вселенных', 'Мультфильм', 140, 6, 'active',
     'https://www.youtube.com/watch?v=4GYSwY0zt1U'),
    ('Дэдпул и Wolverine', 'Боевик', 128, 18, 'active',
     'https://www.youtube.com/watch?v=73_1biulkYk'),
    ('Оппенгеймер: Империя атома', 'Триллер', 150, 16, 'active',
     'https://www.youtube.com/watch?v=2fD2nyBSH5w'),
    ('Каскадёры', 'Боевик', 106, 12, 'active',
     'https://www.youtube.com/watch?v=XaVz5O1Ycxc'),
    ('Плохие парни до конца', 'Комедия', 110, 16, 'active',
     'https://www.youtube.com/watch?v=S4QfGHw41Z0'),
    ('Годзилла и Конг: Новая империя', 'Приключения', 115, 12, 'active',
     'https://www.youtube.com/watch?v=lV1OOlGwExM'),
    ('Дюна: Часть третья', 'Фантастика', 170, 12, 'upcoming',
     'https://www.youtube.com/watch?v=Way9Dexny3w'),
]

# (number, type, capacity) — разные размеры залов
DEMO_HALLS = [
    (1, '2D', 80),
    (2, 'IMAX', 120),
]

# Базовые цены сеанса: VIP-категория мест дороже (стандарт/комфорт/VIP)
DEMO_PRICES = [
    (250, 400, 650),   # будни дешевле
    (300, 450, 700),
    (350, 520, 800),   # выходные дороже
]

REVIEW_TEXTS = [
    'Отличное кино, советую!',
    'Зрелищно и увлекательно.',
    'Неплохо, но могло быть лучше.',
    'Зашёл с семьёй — всем понравилось.',
]

POSTER_COLORS = [
    (30, 60, 110), (120, 40, 60), (40, 100, 70), (90, 70, 30),
    (70, 40, 110), (30, 90, 100), (110, 60, 30), (50, 50, 90),
]


def make_poster(path: Path, title: str, color):
    """Простая заглушка постера 400x600 через Pillow."""
    from PIL import Image, ImageDraw, ImageFont

    width, height = 400, 600
    img = Image.new('RGB', (width, height), color)
    draw = ImageDraw.Draw(img)

    # Градиентные полосы
    r, g, b = color
    for i in range(0, height, 4):
        shade = int(i / height * 60)
        draw.line([(0, i), (width, i)], fill=(min(r + shade, 255), min(g + shade, 255), min(b + shade, 255)))

    # Рамка
    draw.rectangle([(12, 12), (width - 12, height - 12)], outline=(240, 240, 240), width=2)

    font = None
    for font_path in ('C:/Windows/Fonts/arialbd.ttf', 'C:/Windows/Fonts/arial.ttf'):
        if Path(font_path).exists():
            try:
                font = ImageFont.truetype(font_path, 28)
                break
            except OSError:
                pass
    if font is None:
        font = ImageFont.load_default()

    # Перенос заголовка по словам
    words, lines, current = title.split(), [], ''
    for word in words:
        candidate = f'{current} {word}'.strip()
        if draw.textlength(candidate, font=font) <= width - 60:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)

    y = height // 2 - len(lines) * 18
    for line in lines[:6]:
        x = (width - draw.textlength(line, font=font)) / 2
        draw.text((x, y), line, fill=(245, 245, 245), font=font)
        y += 36

    draw.text((24, height - 48), 'ДЕМО', fill=(220, 220, 160), font=font)
    img.save(path, 'JPEG', quality=85)


class Command(BaseCommand):
    help = 'Идемпотентное создание демо-данных (роли, жанры, фильмы, залы, сеансы, брони)'

    def handle(self, *args, **options):
        self.stdout.write('Создание демо-данных…')

        # ── Пользователи ──────────────────────────────
        for username, password, role, first, last in DEMO_USERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'role': role,
                    'first_name': first,
                    'last_name': last,
                    'email': f'{username}@aurora.kz',
                },
            )
            if created:
                user.set_password(password)
                user.save()
            if role == 'admin' and not (user.is_staff and user.is_superuser):
                user.is_staff = True
                user.is_superuser = True
                user.save()
            self.stdout.write(f'  {'+' if created else '='} {username} ({role})')

        self.stdout.write(self.style.SUCCESS('Демо-аккаунты:'))
        for username, password, role, *_ in DEMO_USERS:
            self.stdout.write(f'    {username} / {password}  — {role}')

        # ── Жанры ─────────────────────────────────────
        for name in DEMO_GENRES:
            Genre.objects.get_or_create(name=name)
        self.stdout.write(f'  жанров: {Genre.objects.count()}')

        # ── Типы билетов (скидки настраиваются в админке) ─
        for code, name, discount in [
            ('adult', 'Взрослый', 0),
            ('child', 'Детский', 50),
            ('student', 'Студенческий', 20),
        ]:
            TicketType.objects.get_or_create(
                code=code,
                defaults={'name': name, 'discount_percent': discount, 'is_active': True},
            )
        self.stdout.write(f'  типов билетов: {TicketType.objects.count()}')

        # ── Фильмы с постерами и трейлерами ───────────
        poster_dir = Path(settings.MEDIA_ROOT) / 'posters'
        poster_dir.mkdir(parents=True, exist_ok=True)
        for i, (title, genre_name, duration, age, status, trailer) in enumerate(DEMO_MOVIES):
            genre = Genre.objects.get(name=genre_name)
            movie, created = Movie.objects.get_or_create(
                title=title,
                defaults={
                    'genre': genre,
                    'duration': duration,
                    'age_rating': age,
                    'status': status,
                    'trailer_url': trailer,
                    'description': (
                        f'Демо-описание фильма «{title}». Жанр — {genre_name.lower()}, '
                        f'{duration} минут, {age}+.'
                    ),
                },
            )
            poster_name = f'posters/movie_{i + 1}.jpg'
            if not movie.poster:
                poster_path = Path(settings.MEDIA_ROOT) / poster_name
                if not poster_path.exists():
                    make_poster(poster_path, title, POSTER_COLORS[i % len(POSTER_COLORS)])
                movie.poster.name = poster_name
                movie.save(update_fields=['poster'])
        self.stdout.write(f'  фильмов: {Movie.objects.count()}')

        # ── Залы с местами (разные размеры) ───────────
        for number, hall_type, capacity in DEMO_HALLS:
            hall, created = Hall.objects.get_or_create(
                number=number,
                defaults={'type': hall_type, 'capacity': capacity},
            )
            if created or not hall.seats.exists():
                hall.generate_seats()
            self.stdout.write(f'  зал {number} ({hall_type}), мест: {hall.seats.count()}')

        # ── Сеансы на 7 дней с разными ценами ─────────
        self.seed_sessions()
        self.stdout.write(f'  сеансов: {Session.objects.count()}')

        # ── Отзывы от demo-клиентов ────────────────────
        demo_client = User.objects.filter(role='client').first()
        if demo_client:
            active_movies = list(Movie.objects.filter(status='active')[:4])
            for i, movie in enumerate(active_movies):
                Review.objects.get_or_create(
                    user=demo_client, movie=movie,
                    defaults={
                        'rating': 5 - (i % 3),
                        'comment': REVIEW_TEXTS[i % len(REVIEW_TEXTS)],
                    },
                )

        # ── Демо-брони и оплаченные билеты ────────────
        self.seed_bookings()

        self.stdout.write(self.style.SUCCESS('Демо-данные готовы (идемпотентно).'))

    def seed_sessions(self):
        """Сеансы на ближайшие 10 дней для ВСЕХ фильмов, без пересечений."""
        halls = list(Hall.objects.order_by('number'))
        movies = list(Movie.objects.order_by('id'))
        if not halls or not movies:
            return

        slots = [time(11, 0), time(13, 30), time(16, 0), time(18, 30), time(21, 0)]
        today = timezone.localdate()
        created_count = 0
        buffer = getattr(settings, 'SESSION_BUFFER_MINUTES', 20)

        # Занятые интервалы по залам: {hall_id: [(start_dt, end_dt)]}
        occupied = {h.id: [] for h in halls}
        for s in Session.objects.filter(date__gte=today, is_active=True).select_related('movie'):
            start = datetime.combine(s.date, s.time)
            end = start + timedelta(minutes=s.get_duration_min() + buffer)
            occupied.setdefault(s.hall_id, []).append((start, end))

        for day_offset in range(10):
            day = today + timedelta(days=day_offset)
            # Выходные — дороже
            price_idx = 2 if day.weekday() >= 5 else (day_offset % 2)
            p_std, p_comf, p_vip = DEMO_PRICES[price_idx]
            for idx, movie in enumerate(movies):
                hall = halls[(idx // len(slots)) % len(halls)]
                slot = slots[idx % len(slots)]
                start = datetime.combine(day, slot)
                end = start + timedelta(minutes=movie.duration + buffer)

                clash = any(
                    start < other_end and end > other_start
                    for other_start, other_end in occupied.get(hall.id, [])
                )
                if clash:
                    continue

                _, created = Session.objects.get_or_create(
                    movie=movie, hall=hall, date=day, time=slot,
                    defaults={
                        'is_active': True,
                        'price_standard': p_std,
                        'price_comfort': p_comf,
                        'price_vip': p_vip,
                    },
                )
                if created:
                    created_count += 1
                    occupied.setdefault(hall.id, []).append((start, end))

        self.stdout.write(f'  новых сеансов: {created_count}')

    def seed_bookings(self):
        """Демо-брони и оплаченные билеты (идемпотентно)."""
        from cinema import services

        clients = list(User.objects.filter(role='client').order_by('id')[:3])
        if not clients:
            return

        future_sessions = list(
            Session.objects.filter(
                date__gte=timezone.localdate(), is_active=True
            ).select_related('movie', 'hall').order_by('date', 'time')[:15]
        )

        bookings_created = tickets_created = 0
        for i, session in enumerate(future_sessions):
            client = clients[i % len(clients)]
            if Booking.objects.filter(client=client, session=session).exists():
                continue
            seats = list(session.get_available_seats()[:1])
            if not seats:
                continue
            try:
                bookings, _ = services.create_booking(client, session, [seats[0].id])
            except services.BookingError:
                continue
            bookings_created += 1
            # Каждую вторую бронь оплачиваем — дашборд и продажи не пустые
            if i % 2 == 0:
                try:
                    services.confirm_payment(bookings[0], 'card', client)
                    tickets_created += 1
                except services.BookingError:
                    pass

        self.stdout.write(
            f'  демо-броней: {bookings_created}, оплаченных билетов: {tickets_created} '
            f'(всего броней: {Booking.objects.count()}, билетов: {Ticket.objects.count()})'
        )
