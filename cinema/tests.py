from datetime import date, time, timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from rest_framework.test import APIClient

from .models import User, Genre, Movie, Hall, Seat, Session, Booking, Ticket, Payment, Favorite, Review


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

    def make_booking(self, user=None, seat=None, status='pending_payment', expires_at=None):
        return Booking.objects.create(
            client=user or self.client_user,
            session=self.session,
            seat=seat or self.seat1,
            status=status,
            expires_at=expires_at,
        )


class BookingUniqueConstraintTests(CinemaFixture):
    """П.1: нельзя создать два активных Booking на одну пару (session, seat)"""

    def test_second_active_booking_raises_integrity_error(self):
        self.make_booking()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Booking.objects.create(
                    client=self.cashier,
                    session=self.session,
                    seat=self.seat1,
                    status='pending_payment',
                )

    def test_old_cancelled_booking_does_not_block(self):
        self.make_booking(status='cancelled')
        booking = self.make_booking()
        self.assertIsNotNone(booking.pk)
        self.assertEqual(
            Booking.objects.filter(
                session=self.session, seat=self.seat1,
                status__in=['created', 'pending_payment', 'paid', 'used'],
            ).count(), 1,
        )


class BookingApiErrorTests(CinemaFixture):
    """П.1: API возвращает понятную ошибку (400, не 500), если место занято"""

    def setUp(self):
        super().setUp()
        self.api = APIClient()
        self.api.force_authenticate(user=self.client_user)

    def test_create_booking_on_taken_seat_returns_400(self):
        self.make_booking()
        resp = self.api.post('/api/bookings/', {
            'session': self.session.id, 'seat': self.seat1.id,
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('забронировано', str(resp.data))
        self.assertEqual(Booking.objects.filter(
            session=self.session, seat=self.seat1,
            status__in=['created', 'pending_payment', 'paid', 'used'],
        ).count(), 1)

    def test_html_booking_all_or_nothing(self):
        """Если часть мест занята — не создаётся ни одной брони"""
        self.make_booking()  # seat1 занято
        self.client.force_login(self.client_user)
        resp = self.client.post(f'/booking/{self.session.id}/', {
            'seats': f'{self.seat1.id},{self.seat2.id}',
        })
        self.assertEqual(resp.status_code, 302)
        # seat2 не должен был забронироваться (всё или ничего)
        self.assertFalse(
            Booking.objects.filter(session=self.session, seat=self.seat2).exists()
        )

    def test_html_booking_success(self):
        self.client.force_login(self.client_user)
        self.client.post(f'/booking/{self.session.id}/', {
            'seats': f'{self.seat1.id},{self.seat2.id}',
        })
        self.assertEqual(
            Booking.objects.filter(
                session=self.session,
                seat__in=[self.seat1, self.seat2],
            ).count(), 2,
        )


class ExpireBookingsCommandTests(CinemaFixture):
    """П.2: регресс-тест на баг с ленивым QuerySet в expire_bookings"""

    def test_expires_and_prints_list(self):
        b1 = self.make_booking(expires_at=timezone.now() - timedelta(hours=1))
        out = StringIO()
        call_command('expire_bookings', stdout=out)
        b1.refresh_from_db()
        self.assertEqual(b1.status, 'expired')
        output = out.getvalue()
        self.assertIn('Успешно отменено 1', output)
        # Список отменённых выводится (старый баг: вывод после update пуст)
        self.assertIn(f'Отменено: #{b1.id}', output)

    def test_dry_run_does_not_change_status(self):
        b1 = self.make_booking(expires_at=timezone.now() - timedelta(hours=1))
        out = StringIO()
        call_command('expire_bookings', '--dry-run', stdout=out)
        b1.refresh_from_db()
        self.assertEqual(b1.status, 'pending_payment')
        self.assertIn('[DRY RUN]', out.getvalue())


class AccessControlTests(CinemaFixture):
    """П.8: клиент не может зайти в Manager/Cashier/Controller"""

    def test_client_gets_403(self):
        self.client.force_login(self.client_user)
        for url in ['/manager/', '/cashier/', '/controller/']:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 403, url)

    def test_anonymous_redirected_to_login(self):
        for url in ['/manager/', '/cashier/', '/controller/']:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 302, url)
            self.assertIn('/login/', resp['Location'])

    def test_staff_has_access(self):
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get('/manager/').status_code, 200)
        self.client.force_login(self.cashier)
        self.assertEqual(self.client.get('/cashier/').status_code, 200)


class ConfirmPaymentTests(CinemaFixture):
    """П.3 и П.8: confirm_payment переводит Booking → paid и создаёт Ticket"""

    def setUp(self):
        super().setUp()
        self.api = APIClient()
        self.api.force_authenticate(user=self.cashier)
        self.booking = self.make_booking(status='pending_payment')

    def test_confirm_payment_creates_ticket_and_pays(self):
        resp = self.api.post(
            f'/api/bookings/{self.booking.id}/confirm_payment/',
            {'method': 'cash'}, format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'paid')
        ticket = Ticket.objects.get(booking=self.booking)
        self.assertEqual(ticket.status, 'active')
        payment = Payment.objects.get(ticket=ticket)
        self.assertEqual(payment.status, 'completed')
        self.assertEqual(self.booking.ticket, ticket)

    def test_confirm_payment_requires_pending_status(self):
        self.booking.status = 'paid'
        self.booking.save()
        resp = self.api.post(
            f'/api/bookings/{self.booking.id}/confirm_payment/',
            {'method': 'cash'}, format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(Ticket.objects.filter(booking=self.booking).exists())


class FavoriteReviewTests(CinemaFixture):
    """П.9–10: избранное и отзывы/рейтинг через API"""

    def setUp(self):
        super().setUp()
        self.api = APIClient()
        self.api.force_authenticate(user=self.client_user)

    def test_favorite_toggle_and_list(self):
        resp = self.api.post(f'/api/favorites/{self.movie.id}/')
        self.assertEqual(resp.status_code, 201)
        resp = self.api.post(f'/api/favorites/{self.movie.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Favorite.objects.filter(
            user=self.client_user, movie=self.movie).count(), 1)
        resp = self.api.get('/api/favorites/')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(any(
            f['movie'] == self.movie.id for f in resp.data
        ))
        resp = self.api.delete(f'/api/favorites/{self.movie.id}/')
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(Favorite.objects.filter(
            user=self.client_user, movie=self.movie).exists())

    def test_anonymous_cannot_add_favorite(self):
        api = APIClient()
        resp = api.post(f'/api/favorites/{self.movie.id}/')
        self.assertIn(resp.status_code, [401, 403])

    def test_review_create_update_and_rating_summary(self):
        resp = self.api.post('/api/reviews/', {
            'movie': self.movie.id, 'rating': 5, 'comment': 'Отлично',
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        # повторная оценка обновляет, а не дублирует
        resp = self.api.post('/api/reviews/', {
            'movie': self.movie.id, 'rating': 3, 'comment': 'Нормально',
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Review.objects.filter(
            user=self.client_user, movie=self.movie).count(), 1)
        resp = self.api.get(f'/api/movies/{self.movie.id}/reviews/')
        data = resp.data
        self.assertEqual(data['rating'], 3.0)
        self.assertEqual(data['count'], 1)

    def test_review_rating_out_of_range_rejected(self):
        resp = self.api.post('/api/reviews/', {
            'movie': self.movie.id, 'rating': 9,
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_home_and_detail_pages_render(self):
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'fav-btn')
        self.client.force_login(self.client_user)
        resp = self.client.get(f'/movie/{self.movie.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'reviewForm')
