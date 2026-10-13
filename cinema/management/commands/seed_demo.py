"""Идемпотентное наполнение демо-данными: роли, жанры, фильмы, залы, сеансы."""
from datetime import datetime, time, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from cinema.models import Genre, Hall, Movie, Review, Session, User

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
    # (title, genre, duration, age_rating, status, poster)
    ('Дюна: Часть вторая', 'Фантастика', 166, 12, 'active', 'movie_1.jpg'),
    ('Oppenheimer', 'Драма', 180, 18, 'active', 'movie_2.jpg'),
    ('Человек-паук: Паутина вселенных', 'Мультфильм', 140, 6, 'active', 'movie_3.jpg'),
    ('Дэдпул и Wolverine', 'Боевик', 128, 18, 'active', 'movie_4.jpg'),
    ('Оппенгеймер: Империя атома', 'Триллер', 150, 16, 'active', 'movie_5.jpg'),
    ('Каскадёры', 'Боевик', 106, 12, 'active', 'movie_6.jpg'),
    ('Плохие парни до конца', 'Комедия', 110, 16, 'active', 'movie_7.jpg'),
    ('Годзилла и Конг: Новая империя', 'Приключения', 115, 12, 'active', 'movie_8.jpg'),
    ('Дюна: Часть третья', 'Фантастика', 170, 12, 'upcoming', 'movie_1.jpg'),
]

DEMO_HALLS = [
    # (number, type, capacity)
    (1, '2D', 80),
    (2, 'IMAX', 120),
    (3, 'VIP', 40),
]

REVIEW_TEXTS = [
    'Отличное кино, советую!',
    'Зрелищно и увлекательно.',
    'Неплохо, но могло быть лучше.',
    'Зашёл с семьёй — всем понравилось.',
]


class Command(BaseCommand):
    help = 'Идемпотентное создание демо-данных (роли, жанры, фильмы, залы, сеансы)'

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
                self.stdout.write(f'  + пользователь {username} ({role})')
            else:
                self.stdout.write(f'  = пользователь {username} уже существует')

        self.stdout.write(self.style.SUCCESS('Пользователи готовы (пароли см. выше)'))

        # ── Жанры ─────────────────────────────────────
        for name in DEMO_GENRES:
            Genre.objects.get_or_create(name=name)
        self.stdout.write(f'  жанров: {Genre.objects.count()}')

        # ── Фильмы ────────────────────────────────────
        poster_dir = Path(settings.MEDIA_ROOT) / 'posters'
        for title, genre_name, duration, age, status, poster in DEMO_MOVIES:
            genre = Genre.objects.get(name=genre_name)
            movie, created = Movie.objects.get_or_create(
                title=title,
                defaults={
                    'genre': genre,
                    'duration': duration,
                    'age_rating': age,
                    'status': status,
                    'description': f'Демо-описание фильма «{title}».',
                },
            )
            if created and poster:
                src = poster_dir / poster
                if src.exists() and not movie.poster:
                    movie.poster.name = f'posters/{poster}'
                    movie.save(update_fields=['poster'])
        self.stdout.write(f'  фильмов: {Movie.objects.count()}')

        # ── Залы с местами ─────────────────────────────
        for number, hall_type, capacity in DEMO_HALLS:
            hall, created = Hall.objects.get_or_create(
                number=number,
                defaults={'type': hall_type, 'capacity': capacity},
            )
            if created or not hall.seats.exists():
                hall.generate_seats()
                self.stdout.write(f'  + зал {number} ({hall_type}), мест: {hall.seats.count()}')

        # ── Сеансы на 7 дней ───────────────────────────
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

        self.stdout.write(self.style.SUCCESS('Демо-данные готовы (идемпотентно).'))

    def seed_sessions(self):
        """Сеансы на ближайшие 7 дней с проверкой пересечений в зале."""
        from django.core.exceptions import ValidationError

        halls = list(Hall.objects.order_by('number'))
        movies = list(Movie.objects.filter(status='active').order_by('id'))
        if not halls or not movies:
            return

        slots = [time(11, 0), time(14, 30), time(18, 30), time(22, 0)]
        today = timezone.localdate()
        created_count = 0
        buffer = getattr(settings, 'SESSION_BUFFER_MINUTES', 20)

        # Занятые интервалы по залам: {hall_id: [(start_dt, end_dt)]}
        occupied = {h.id: [] for h in halls}
        for s in Session.objects.filter(date__gte=today, is_active=True).select_related('movie'):
            start = datetime.combine(s.date, s.time)
            end = start + timedelta(minutes=s.movie.duration + buffer)
            occupied.setdefault(s.hall_id, []).append((start, end))

        for day_offset in range(7):
            day = today + timedelta(days=day_offset)
            for idx, movie in enumerate(movies):
                hall = halls[(idx + day_offset) % len(halls)]
                slot = slots[(idx * 2 + day_offset) % len(slots)]
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
                    defaults={'is_active': True},
                )
                if created:
                    created_count += 1
                    occupied.setdefault(hall.id, []).append((start, end))

        self.stdout.write(f'  новых сеансов: {created_count}')
