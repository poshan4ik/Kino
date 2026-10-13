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


class SecurityRegressionTests(CinemaFixture):
    """Этап 3: закрытие критичных уязвимостей безопасности"""

    def test_update_me_cannot_escalate_role(self):
        api = APIClient()
        api.force_authenticate(user=self.client_user)
        resp = api.patch('/api/users/update_me/', {'role': 'admin'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.client_user.refresh_from_db()
        self.assertEqual(self.client_user.role, 'client')

    def test_anonymous_cannot_create_admin(self):
        api = APIClient()
        resp = api.post('/api/users/', {
            'username': 'hacker', 'password': 'x' * 9,
            'email': 'h@e.ru', 'role': 'admin',
        }, format='json')
        self.assertIn(resp.status_code, [401, 403])
        self.assertFalse(User.objects.filter(username='hacker').exists())

    def test_client_cannot_list_users(self):
        api = APIClient()
        api.force_authenticate(user=self.client_user)
        resp = api.get('/api/users/')
        self.assertEqual(resp.status_code, 403)

    def test_manager_can_list_users(self):
        api = APIClient()
        api.force_authenticate(user=self.manager)
        resp = api.get('/api/users/')
        self.assertEqual(resp.status_code, 200)

    def test_client_cannot_see_foreign_bookings(self):
        Booking.objects.create(
            client=self.cashier, session=self.session, seat=self.seat1,
            status='pending_payment',
        )
        own = self.make_booking(seat=self.seat2)
        api = APIClient()
        api.force_authenticate(user=self.client_user)
        resp = api.get('/api/bookings/')
        self.assertEqual(resp.status_code, 200)
        results = resp.data['results'] if isinstance(resp.data, dict) else resp.data
        ids = [b['id'] for b in results]
        self.assertIn(own.id, ids)
        self.assertEqual(len(ids), 1)

    def test_client_cannot_see_foreign_tickets(self):
        booking = Booking.objects.create(
            client=self.cashier, session=self.session, seat=self.seat1,
            status='pending_payment',
        )
        from . import services
        services.confirm_payment(booking, 'cash', self.cashier)
        api = APIClient()
        api.force_authenticate(user=self.client_user)
        resp = api.get('/api/tickets/')
        self.assertEqual(resp.status_code, 200)
        results = resp.data['results'] if isinstance(resp.data, dict) else resp.data
        self.assertEqual(len(results), 0)

    def test_health_ok(self):
        resp = self.client.get('/health/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('status', resp.json())


class HoldFlowTests(CinemaFixture):
    """Этап 3: сервис бронирования — прошедший сеанс, лимит, чужой зал, гонка"""

    def test_hold_past_session_rejected(self):
        past = Session.objects.create(
            movie=self.movie, hall=self.hall,
            date=date.today() - timedelta(days=1), time=time(12, 0),
        )
        api = APIClient()
        api.force_authenticate(user=self.client_user)
        resp = api.post('/api/bookings/hold/', {
            'session': past.id, 'seats': [self.seat1.id],
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('начался', str(resp.data))

    def test_hold_foreign_hall_seat_rejected(self):
        other_hall = Hall.objects.create(number=2, type='3D', capacity=10)
        foreign = Seat.objects.create(hall=other_hall, row=1, number=1)
        api = APIClient()
        api.force_authenticate(user=self.client_user)
        resp = api.post('/api/bookings/hold/', {
            'session': self.session.id, 'seats': [foreign.id],
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_hold_seat_limit_enforced(self):
        seats = []
        for i in range(3, 14):
            seats.append(Seat.objects.create(hall=self.hall, row=2, number=i))
        api = APIClient()
        api.force_authenticate(user=self.client_user)
        resp = api.post('/api/bookings/hold/', {
            'session': self.session.id, 'seats': [s.id for s in seats],
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Максимум', str(resp.data))

    def test_hold_seats_all_or_nothing_on_conflict(self):
        self.make_booking(seat=self.seat1)
        api = APIClient()
        api.force_authenticate(user=self.client_user)
        resp = api.post('/api/bookings/hold/', {
            'session': self.session.id, 'seats': [self.seat1.id, self.seat2.id],
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(
            Booking.objects.filter(session=self.session, seat=self.seat2).exists()
        )

    def test_concurrent_hold_second_fails(self):
        from . import services
        from .models import Seat as SeatModel
        seats = []
        for i in range(3, 5):
            seats.append(SeatModel.objects.create(hall=self.hall, row=1, number=i))
        services.create_hold(self.client_user, self.session, [s.id for s in seats])
        with self.assertRaises(services.BookingError):
            services.create_hold(self.cashier, self.session, [s.id for s in seats])


class PayRefundTests(CinemaFixture):
    """Этап 3/4: оплата, повторная оплата, возврат и права ролей"""

    def setUp(self):
        super().setUp()
        self.api = APIClient()
        self.api.force_authenticate(user=self.client_user)
        self.booking = self.make_booking(
            status='pending_payment',
            expires_at=timezone.now() + timedelta(minutes=10),
        )

    def _pay(self, user=None, method='online', ids=None):
        api = APIClient()
        api.force_authenticate(user=user or self.client_user)
        return api.post('/api/bookings/pay/', {
            'booking_ids': ids or [self.booking.id], 'method': method,
        }, format='json')

    def test_pay_online_creates_ticket_and_payment(self):
        resp = self._pay()
        self.assertEqual(resp.status_code, 201)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'paid')
        self.assertTrue(Ticket.objects.filter(booking=self.booking).exists())
        self.assertTrue(Payment.objects.filter(
            ticket__booking=self.booking, status='completed').exists())

    def test_double_pay_rejected(self):
        self._pay()
        resp = self._pay()
        self.assertEqual(resp.status_code, 400)

    def test_pay_expired_hold_rejected(self):
        self.booking.expires_at = timezone.now() - timedelta(minutes=1)
        self.booking.save(update_fields=['expires_at'])
        resp = self._pay()
        self.assertEqual(resp.status_code, 400)
        self.assertIn('истекло', str(resp.data))

    def test_client_cannot_pay_foreign_booking(self):
        Booking.objects.create(
            client=self.cashier, session=self.session, seat=self.seat2,
            status='pending_payment',
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        foreign_id = Booking.objects.exclude(pk=self.booking.pk).first().id
        resp = self._pay(ids=[foreign_id])
        self.assertEqual(resp.status_code, 403)

    def test_refund_by_cashier(self):
        self._pay()
        api = APIClient()
        api.force_authenticate(user=self.cashier)
        resp = api.post(f'/api/bookings/{self.booking.id}/refund/')
        self.assertEqual(resp.status_code, 200)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'cancelled')
        self.assertEqual(self.booking.ticket.status, 'refunded')
        self.assertEqual(Payment.objects.filter(
            ticket__booking=self.booking, status='refunded').count(), 1)

    def test_controller_cannot_refund(self):
        self._pay()
        api = APIClient()
        api.force_authenticate(user=self.controller)
        resp = api.post(f'/api/bookings/{self.booking.id}/refund/')
        self.assertEqual(resp.status_code, 403)

    def test_client_cannot_refund_others(self):
        self._pay()
        booking2 = Booking.objects.create(
            client=self.cashier, session=self.session, seat=self.seat2,
            status='paid',
        )
        resp = self.api.post(f'/api/bookings/{booking2.id}/refund/')
        self.assertEqual(resp.status_code, 403)

    def test_refund_after_session_start_rejected(self):
        self._pay()
        Session.objects.filter(pk=self.session.pk).update(
            date=date.today() - timedelta(days=1), time=time(1, 0))
        api = APIClient()
        api.force_authenticate(user=self.cashier)
        resp = api.post(f'/api/bookings/{self.booking.id}/refund/')
        self.assertEqual(resp.status_code, 400)

    def test_client_cancel_own_pending(self):
        resp = self.api.post(
            f'/api/bookings/{self.booking.id}/cancel_own/')
        self.assertEqual(resp.status_code, 200)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'cancelled')

    def test_client_cancel_foreign_forbidden(self):
        Booking.objects.create(
            client=self.cashier, session=self.session, seat=self.seat2,
            status='pending_payment',
        )
        other = Booking.objects.exclude(pk=self.booking.pk).first()
        resp = self.api.post(f'/api/bookings/{other.id}/cancel_own/')
        # чужая бронь невидима клиенту (queryset отфильтрован) — 404
        self.assertEqual(resp.status_code, 404)


class TicketCheckTests(CinemaFixture):
    """Проверка билетов контроллёром по штрихкоду"""

    def setUp(self):
        super().setUp()
        self.booking = self.make_booking(status='pending_payment')
        from . import services
        self.ticket = services.confirm_payment(self.booking, 'cash', self.cashier)
        self.api = APIClient()
        self.api.force_authenticate(user=self.controller)

    def test_valid_ticket_marks_used(self):
        resp = self.api.post('/api/tickets/check_by_barcode/', {
            'barcode': self.ticket.barcode,
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['valid'])
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'used')

    def test_used_ticket_rejected(self):
        self.ticket.mark_used()
        resp = self.api.post('/api/tickets/check_by_barcode/', {
            'barcode': self.ticket.barcode,
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.data['valid'])

    def test_unknown_barcode_404(self):
        resp = self.api.post('/api/tickets/check_by_barcode/', {
            'barcode': 'NOPE123',
        }, format='json')
        self.assertEqual(resp.status_code, 404)

    def test_client_cannot_check(self):
        api = APIClient()
        api.force_authenticate(user=self.client_user)
        resp = api.post('/api/tickets/check_by_barcode/', {
            'barcode': self.ticket.barcode,
        }, format='json')
        self.assertEqual(resp.status_code, 403)


class DashboardReportTests(CinemaFixture):
    """Дашборд, отчёты и CSV-экспорт (менеджер/админ)"""

    def setUp(self):
        super().setUp()
        self.booking = self.make_booking(status='pending_payment')
        from . import services
        self.ticket = services.confirm_payment(self.booking, 'cash', self.cashier)

    def test_dashboard_forbidden_for_client(self):
        api = APIClient()
        api.force_authenticate(user=self.client_user)
        resp = api.get('/api/dashboard/stats/')
        self.assertEqual(resp.status_code, 403)

    def test_dashboard_totals(self):
        api = APIClient()
        api.force_authenticate(user=self.manager)
        resp = api.get('/api/dashboard/stats/')
        self.assertEqual(resp.status_code, 200)
        data = resp.data
        self.assertEqual(float(data['revenue']), float(self.ticket.price))
        self.assertEqual(data['tickets_sold'], 1)

    def test_reports_page_and_csv_export(self):
        self.client.force_login(self.manager)
        resp = self.client.get(reverse('staff_reports'))
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get(reverse('staff_reports_export'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv; charset=utf-8')
        body = resp.content.decode('utf-8-sig')
        self.assertIn('Фильм', body)

    def test_reports_period_filter(self):
        self.client.force_login(self.manager)
        today = timezone.localdate()
        resp = self.client.get(reverse('staff_reports'), {
            'date_from': (today - timedelta(days=3)).isoformat(),
            'date_to': today.isoformat(),
        })
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get(reverse('staff_reports'), {
            'date_from': '2020-01-01', 'date_to': '2020-01-31',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'За период продаж нет')


class ProfileFunctionTests(CinemaFixture):
    """Смена пароля и редактирование профиля (Этап 4)"""

    def test_password_change_ok(self):
        self.client.force_login(self.client_user)
        resp = self.client.post(reverse('profile_password'), {
            'old_password': 'pass123457',
            'new_password1': 'newpass12345',
            'new_password2': 'newpass12345',
        })
        self.assertRedirects(resp, reverse('profile'))
        self.client_user.refresh_from_db()
        self.assertTrue(self.client_user.check_password('newpass12345'))

    def test_password_change_wrong_old(self):
        self.client.force_login(self.client_user)
        resp = self.client.post(reverse('profile_password'), {
            'old_password': 'wrongpass1',
            'new_password1': 'newpass12345',
            'new_password2': 'newpass12345',
        })
        self.assertEqual(resp.status_code, 302)
        self.client_user.refresh_from_db()
        self.assertTrue(self.client_user.check_password('pass123457'))

    def test_profile_edit(self):
        self.client.force_login(self.client_user)
        resp = self.client.post(reverse('profile_edit'), {
            'first_name': 'Иван', 'last_name': 'Петров',
            'email': 'ivan@example.com', 'phone': '+77001234567',
        })
        self.assertRedirects(resp, reverse('profile'))
        self.client_user.refresh_from_db()
        self.assertEqual(self.client_user.first_name, 'Иван')
        self.assertEqual(self.client_user.phone, '+77001234567')


class SeedDemoCommandTests(CinemaFixture):
    """Идемпотентность seed_demo (Этап 4)"""

    def test_seed_demo_twice_idempotent(self):
        call_command('seed_demo', verbosity=0)
        users = User.objects.count()
        sessions = Session.objects.count()
        movies = Movie.objects.count()
        call_command('seed_demo', verbosity=0)
        self.assertEqual(User.objects.count(), users)
        self.assertEqual(Session.objects.count(), sessions)
        self.assertEqual(Movie.objects.count(), movies)
        self.assertTrue(User.objects.filter(username='admin').exists())
        self.assertTrue(User.objects.filter(username='manager').exists())


class ExtraCoverageTests(CinemaFixture):
    """Регистрация (RegisterForm) и тег admin_stats"""

    def _form_data(self, **overrides):
        data = {
            'username': 'newuser1',
            'first_name': 'Иван',
            'last_name': 'Иванов',
            'email': 'new@example.com',
            'phone': '+77001234567',
            'password1': 'StrongPass123',
            'password2': 'StrongPass123',
            'terms': True,
        }
        data.update(overrides)
        return data

    def test_register_form_valid_creates_client(self):
        from .forms import RegisterForm
        form = RegisterForm(data=self._form_data())
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(user.role, 'client')
        self.assertEqual(user.phone, '+77001234567')
        self.assertTrue(user.check_password('StrongPass123'))

    def test_register_form_duplicate_email(self):
        from .forms import RegisterForm
        User.objects.create_user(
            username='taken', password='x' * 9, email='new@example.com')
        form = RegisterForm(data=self._form_data())
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_register_form_bad_phone(self):
        from .forms import RegisterForm
        form = RegisterForm(data=self._form_data(phone='12345'))
        self.assertFalse(form.is_valid())
        self.assertIn('phone', form.errors)

    def test_register_form_requires_terms(self):
        from .forms import RegisterForm
        form = RegisterForm(data=self._form_data(terms=False))
        self.assertFalse(form.is_valid())
        self.assertIn('terms', form.errors)

    def test_register_form_phone_cleanup(self):
        from .forms import RegisterForm
        form = RegisterForm(data=self._form_data(phone='+7 (700) 123-45-67'))
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(user.phone, '+77001234567')

    def test_admin_stats_tag(self):
        from .templatetags.admin_stats import admin_stats
        self.make_booking(status='paid')
        stats = admin_stats()
        self.assertIn('movies', stats)
        self.assertIn('sessions_today', stats)
        self.assertIn('bookings_active', stats)
        self.assertEqual(stats['movies'], 1)
        self.assertEqual(stats['bookings_active'], 0)


class RoleMatrixTests(CinemaFixture):
    """Матрица ролей: ключевые эндпоинты × роли (200/401/403)"""

    ANON_ALLOWED_GET = ['/', '/login/', '/register/', '/health/',
                        '/api/movies/', '/api/genres/', '/api/sessions/']

    def test_anon_allowed_endpoints(self):
        for url in self.ANON_ALLOWED_GET:
            resp = self.client.get(url)
            self.assertIn(resp.status_code, [200, 302], url)

    def test_anon_denied_endpoints(self):
        for url in ['/api/bookings/', '/api/tickets/', '/api/payments/',
                    '/api/users/', '/api/dashboard/stats/', '/profile/']:
            resp = self.client.get(url)
            self.assertIn(resp.status_code, [401, 403, 302], url)

    def matrix_get(self, url, expected):
        for user_key, want in expected.items():
            user = getattr(self, user_key)
            api = APIClient()
            api.force_authenticate(user=user)
            resp = api.get(url)
            self.assertEqual(
                resp.status_code, want,
                f'{url} для {user_key}: {resp.status_code} != {want}',
            )

    def test_users_endpoint_matrix(self):
        self.matrix_get('/api/users/', {
            'client_user': 403, 'cashier': 403, 'controller': 403,
            'manager': 200, 'admin': 200,
        })

    def test_dashboard_matrix(self):
        self.matrix_get('/api/dashboard/stats/', {
            'client_user': 403, 'cashier': 403, 'controller': 403,
            'manager': 200, 'admin': 200,
        })

    def test_bookings_endpoint_all_roles_200(self):
        self.matrix_get('/api/bookings/', {
            'client_user': 200, 'cashier': 200, 'controller': 200,
            'manager': 200, 'admin': 200,
        })

    def test_staff_pages_matrix(self):
        self.client.force_login(self.cashier)
        self.assertEqual(self.client.get('/manager/').status_code, 403)
        self.client.force_login(self.controller)
        self.assertEqual(self.client.get('/cashier/').status_code, 403)
        self.assertEqual(self.client.get('/manager/').status_code, 403)
        self.client.force_login(self.controller)
        self.assertEqual(self.client.get('/controller/').status_code, 200)
        self.client.force_login(self.admin)
        for url in ['/manager/', '/cashier/', '/controller/']:
            self.assertEqual(self.client.get(url).status_code, 200, url)
