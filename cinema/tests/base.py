"""Базовая фикстура и общий контекст для тестов (Python 3.14 + Django 4.2)."""
from datetime import date, time, timedelta

from django.test import TestCase
from django.utils import timezone

from ..models import User, Genre, Movie, Hall, Seat, Session, Booking


def _context_copy(self):
    duplicate = self.__class__.__new__(self.__class__)
    duplicate.__dict__.update(self.__dict__)
    duplicate.dicts = self.dicts[:]
    return duplicate


from django.template.context import BaseContext  # noqa: E402

BaseContext.__copy__ = _context_copy


class CinemaFixture(TestCase):
    """Базовая фикстура: жанр, фильм, зал с местами, сеанс, пользователи"""

    def setUp(self):
        self.genre = Genre.objects.create(name='Фантастика')
        self.movie = Movie.objects.create(
            title='Тестовый фильм', genre=self.genre,
            duration=100, age_rating=16, status='active',
        )
        self.hall = Hall.objects.create(number=1, type='2D', capacity=20)
        self.seat1 = Seat.objects.create(hall=self.hall, row=1, number=1)
        self.seat2 = Seat.objects.create(hall=self.hall, row=1, number=2)
        self.session = Session.objects.create(
            movie=self.movie, hall=self.hall,
            date=date.today() + timedelta(days=1), time=time(12, 0),
        )
        self.client_user = User.objects.create_user(
            username='client1', password='pass123457', role='client')
        self.cashier = User.objects.create_user(
            username='cashier1', password='pass123457', role='cashier')
        self.manager = User.objects.create_user(
            username='manager1', password='pass123457', role='manager')
        self.controller = User.objects.create_user(
            username='controller1', password='pass123457', role='controller')
        self.admin = User.objects.create_user(
            username='admin1', password='pass123457', role='admin',
            is_staff=True, is_superuser=True)

    def make_booking(self, user=None, seat=None, status='pending_payment', expires_at=None):
        return Booking.objects.create(
            client=user or self.client_user,
            session=self.session,
            seat=seat or self.seat1,
            status=status,
            expires_at=expires_at,
        )
