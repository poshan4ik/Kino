"""Новые тесты: модели, сервисы бронирования/оплаты/возврата, права, дашборд, страницы."""
from datetime import date, datetime, time, timedelta
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from rest_framework.test import APIClient

from .. import services
from ..models import (
    Booking, BookingStatus, Hall, Movie, Seat, Session, Ticket, TicketStatus,
    Payment, PaymentStatus,
)
from .base import CinemaFixture


# ── Модели ─────────────────────────────────────────────

class ModelConstraintTests(CinemaFixture):
    """Уникальность место+сеанс, пересечение сеансов, переходы статусов"""

    def test_unique_seat_session_for_active_bookings(self):
        self.make_booking()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Booking.objects.create(
                    client=self.cashier, session=self.session, seat=self.seat1,
                    status=BookingStatus.PENDING_PAYMENT,
                )

    def test_session_overlap_rejected(self):
        # Существующий сеанс: 12:00 + 100 мин + 20 буфер = конец 14:00.
        # Старт в 14:00 допустим, 13:00 — пересечение.
        Session.objects.create(
            movie=self.movie, hall=self.hall,
            date=self.session.date, time=time(14, 0),
        )
        with self.assertRaises(ValidationError):
            Session.objects.create(
                movie=self.movie, hall=self.hall,
                date=self.session.date, time=time(13, 0),
            )

    def test_session_end_equals_start_allowed(self):
        # Конец одного сеанса = начало следующего — допустимо
        s1 = Session.objects.create(
            movie=self.movie, hall=self.hall,
            date=date.today() + timedelta(days=2), time=time(10, 0),
        )
        next_start = (
            datetime.combine(s1.date, s1.time)
            + timedelta(minutes=s1.get_duration_min() + 20)
        ).time()
        s2 = Session(
            movie=self.movie, hall=self.hall,
            date=s1.date, time=next_start,
        )
        s2.clean()  # не должно бросать
        s2.save()
        self.assertIsNotNone(s2.pk)

    def test_night_session_overlap_across_dates_rejected(self):
        # Ночной сеанс 23:50 (конец за полночь) пересекается с утренним (+1 день)
        today = date.today()
        night = Session.objects.create(
            movie=self.movie, hall=self.hall,
            date=today, time=time(23, 50),
        )
        with self.assertRaises(ValidationError):
            Session.objects.create(
                movie=self.movie, hall=self.hall,
                date=today + timedelta(days=1), time=time(0, 10),
            )
        # Обратно: сначала утренний, потом ночной
        morning = Session.objects.create(
            movie=self.movie, hall=self.hall,
            date=today + timedelta(days=3), time=time(0, 10),
        )
        with self.assertRaises(ValidationError):
            Session.objects.create(
                movie=self.movie, hall=self.hall,
                date=today + timedelta(days=2), time=time(23, 50),
            )
        self.assertTrue(
            Session.objects.filter(
                pk__in=[night.pk, morning.pk]
            ).count() == 2
        )

    def test_invalid_status_transition_raises(self):
        booking = self.make_booking(status=BookingStatus.PAID)
        booking.set_status(BookingStatus.USED)
        with self.assertRaises(ValidationError):
            booking.set_status(BookingStatus.PAID)  # used → paid недопустимо


# ── Бронирование ───────────────────────────────────────

class BookingServiceTests(CinemaFixture):
    """create_booking: успех, занято, прошедший сеанс, чужой зал, лимит"""

    def test_create_booking_success(self):
        bookings, expires_at = services.create_booking(
            self.client_user, self.session, [self.seat1.id]
        )
        self.assertEqual(len(bookings), 1)
        self.assertEqual(bookings[0].status, BookingStatus.PENDING_PAYMENT)
        self.assertIsNotNone(expires_at)

    def test_create_booking_seat_taken(self):
        services.create_booking(self.client_user, self.session, [self.seat1.id])
        with self.assertRaises(services.BookingError) as ctx:
            services.create_booking(self.cashier, self.session, [self.seat1.id])
        self.assertEqual(ctx.exception.status, 409)

    def test_create_booking_past_session_rejected(self):
        past = Session.objects.create(
            movie=self.movie, hall=self.hall,
            date=date.today() - timedelta(days=1), time=time(12, 0),
        )
        with self.assertRaises(services.BookingError):
            services.create_booking(self.client_user, past, [self.seat1.id])

    def test_create_booking_foreign_hall_seat_rejected(self):
        other_hall = Hall.objects.create(number=99, capacity=10)
        foreign = Seat.objects.create(hall=other_hall, row=1, number=1)
        with self.assertRaises(services.BookingError):
            services.create_booking(self.client_user, self.session, [foreign.id])

    def test_create_booking_seat_limit(self):
        seats = [
            Seat.objects.create(hall=self.hall, row=2, number=i).id
            for i in range(1, 13)  # 12 мест > лимита 10
        ]
        with self.assertRaises(services.BookingError) as ctx:
            services.create_booking(self.client_user, self.session, seats)
        self.assertIn('Максимум', ctx.exception.message)


# ── Оплата ─────────────────────────────────────────────

class PaymentServiceTests(CinemaFixture):
    """confirm_payment: успех, повторная оплата, просрочка"""

    def setUp(self):
        super().setUp()
        self.booking = self.make_booking(
            expires_at=timezone.now() + timedelta(minutes=10)
        )

    def test_confirm_payment_success(self):
        ticket = services.confirm_payment(self.booking, 'cash', self.cashier)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.PAID)
        self.assertEqual(ticket.status, TicketStatus.ACTIVE)
        self.assertTrue(ticket.barcode)
        self.assertEqual(ticket.price, self.session.price_standard)
        payment = Payment.objects.get(ticket=ticket)
        self.assertEqual(payment.status, PaymentStatus.COMPLETED)
        self.assertEqual(payment.amount, ticket.price)

    def test_double_payment_rejected(self):
        services.confirm_payment(self.booking, 'cash', self.cashier)
        with self.assertRaises(services.BookingError):
            services.confirm_payment(self.booking, 'cash', self.cashier)

    def test_expired_hold_payment_rejected(self):
        self.booking.expires_at = timezone.now() - timedelta(minutes=1)
        self.booking.save(update_fields=['expires_at'])
        with self.assertRaises(services.BookingError) as ctx:
            services.confirm_payment(self.booking, 'cash', self.cashier)
        self.assertIn('истекло', ctx.exception.message)


# ── Возврат и истечение ────────────────────────────────

class RefundExpireTests(CinemaFixture):
    """Возврат до/после начала сеанса; expire_bookings освобождает места"""

    def test_refund_before_session_start(self):
        booking = self.make_booking(
            expires_at=timezone.now() + timedelta(minutes=10)
        )
        services.confirm_payment(booking, 'cash', self.cashier)
        result = services.refund_ticket(booking, self.cashier)
        result.refresh_from_db()
        self.assertEqual(result.status, BookingStatus.CANCELLED)
        self.assertEqual(result.ticket.status, TicketStatus.REFUNDED)
        # Место снова свободно
        self.assertIn(self.seat1.id, [s.id for s in self.session.get_available_seats()])

    def test_refund_after_session_start_rejected(self):
        past = Session.objects.create(
            movie=self.movie, hall=self.hall,
            date=date.today() - timedelta(hours=1), time=time(0, 0),
        )
        booking = Booking.objects.create(
            client=self.client_user, session=past, seat=self.seat1,
            status=BookingStatus.PAID,
        )
        Ticket.objects.create(
            booking=booking, price=100, barcode='TESTREFUND1',
            status=TicketStatus.ACTIVE,
        )
        with self.assertRaises(services.BookingError) as ctx:
            services.refund_ticket(booking, self.cashier)
        self.assertIn('начала сеанса', ctx.exception.message)

    def test_expire_bookings_frees_seats(self):
        booking = self.make_booking(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        # Место занято до истечения
        self.assertNotIn(self.seat1.id, [s.id for s in self.session.get_available_seats()])
        count = services.expire_old_bookings()
        self.assertEqual(count, 1)
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.EXPIRED)
        self.assertIn(self.seat1.id, [s.id for s in self.session.get_available_seats()])


# ── Проверка билетов ───────────────────────────────────

class CheckTicketServiceTests(CinemaFixture):
    """check_ticket: валидный, повторный, возвращённый, неизвестный"""

    def setUp(self):
        super().setUp()
        self.booking = self.make_booking(
            expires_at=timezone.now() + timedelta(minutes=10)
        )
        self.ticket = services.confirm_payment(self.booking, 'cash', self.cashier)

    def test_valid_ticket_marks_used(self):
        ticket, message = services.check_ticket(self.ticket)
        self.assertEqual(ticket.status, TicketStatus.USED)
        self.assertIn('действителен', message)

    def test_repeat_check_rejected(self):
        services.check_ticket(self.ticket)
        with self.assertRaises(services.BookingError) as ctx:
            services.check_ticket(self.ticket)
        self.assertIn('уже использован', ctx.exception.message)

    def test_refunded_ticket_rejected(self):
        self.ticket.set_status(TicketStatus.REFUNDED)
        with self.assertRaises(services.BookingError) as ctx:
            services.check_ticket(self.ticket)
        self.assertIn('возвращён', ctx.exception.message)

    def test_unknown_barcode_404_via_api(self):
        api = APIClient()
        api.force_authenticate(user=self.controller)
        resp = api.post(
            '/api/tickets/check_by_barcode/', {'barcode': 'NOPE999'}, format='json'
        )
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(resp.data['valid'])
        self.assertIn('не найден', resp.data['message'])


# ── Права ──────────────────────────────────────────────

class PermissionMatrixTests(CinemaFixture):
    """Аноним/клиент/кассир/контролёр/менеджер на ключевых эндпоинтах"""

    def test_anonymous_gets_403_on_bookings(self):
        resp = APIClient().get('/api/bookings/')
        self.assertEqual(resp.status_code, 403)
        self.assertIn('error', resp.data)

    def test_client_sees_only_own_bookings(self):
        self.make_booking(user=self.client_user)
        self.make_booking(user=self.cashier, seat=self.seat2)
        api = APIClient()
        api.force_authenticate(user=self.client_user)
        resp = api.get('/api/bookings/')
        self.assertEqual(resp.status_code, 200)
        results = resp.data['results'] if isinstance(resp.data, dict) else resp.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['client'], self.client_user.id)

    def test_cashier_can_confirm_payment_client_cannot(self):
        booking = self.make_booking(
            expires_at=timezone.now() + timedelta(minutes=10)
        )
        url = f'/api/bookings/{booking.id}/confirm_payment/'
        api = APIClient()
        api.force_authenticate(user=self.client_user)
        resp = api.post(url, {'method': 'cash'}, format='json')
        self.assertEqual(resp.status_code, 403)
        api.force_authenticate(user=self.cashier)
        resp = api.post(url, {'method': 'cash'}, format='json')
        self.assertEqual(resp.status_code, 200)

    def test_controller_cannot_confirm_payment(self):
        booking = self.make_booking(
            expires_at=timezone.now() + timedelta(minutes=10)
        )
        api = APIClient()
        api.force_authenticate(user=self.controller)
        resp = api.post(
            f'/api/bookings/{booking.id}/confirm_payment/', {}, format='json'
        )
        self.assertEqual(resp.status_code, 403)

    def test_manager_dashboard_ok_client_forbidden(self):
        api = APIClient()
        api.force_authenticate(user=self.client_user)
        resp = api.get('/api/dashboard/stats/')
        self.assertEqual(resp.status_code, 403)
        api.force_authenticate(user=self.manager)
        resp = api.get('/api/dashboard/stats/')
        self.assertEqual(resp.status_code, 200)

    def test_client_cannot_change_role(self):
        api = APIClient()
        api.force_authenticate(user=self.client_user)
        resp = api.patch('/api/users/update_me/', {'role': 'admin'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.client_user.refresh_from_db()
        self.assertEqual(self.client_user.role, 'client')


# ── Дашборд и страницы ─────────────────────────────────

class DashboardTotalsTests(CinemaFixture):
    """Дашборд: суммы считаются верно"""

    def test_revenue_counts_only_completed_payments(self):
        booking1 = self.make_booking(
            expires_at=timezone.now() + timedelta(minutes=10)
        )
        services.confirm_payment(booking1, 'cash', self.cashier)
        booking2 = self.make_booking(
            seat=self.seat2, expires_at=timezone.now() + timedelta(minutes=10)
        )
        ticket2 = services.confirm_payment(booking2, 'card', self.cashier)
        # Возвращённый платёж не должен попадать в выручку
        Payment.objects.filter(ticket=ticket2).update(status=PaymentStatus.REFUNDED)

        api = APIClient()
        api.force_authenticate(user=self.manager)
        resp = api.get('/api/dashboard/stats/')
        self.assertEqual(resp.status_code, 200)
        expected = float(
            Payment.objects.filter(
                status=PaymentStatus.COMPLETED,
                completed_at__date=timezone.localdate(),
            ).aggregate(total=Sum('amount'))['total'] or 0
        )
        self.assertEqual(float(resp.data['revenue']), expected)
        self.assertGreater(expected, 0)

    def test_sales_report_filters_by_period(self):
        booking = self.make_booking(
            expires_at=timezone.now() + timedelta(minutes=10)
        )
        services.confirm_payment(booking, 'cash', self.cashier)
        api = APIClient()
        api.force_authenticate(user=self.manager)
        today = timezone.localdate().isoformat()
        resp = api.get(f'/api/dashboard/sales_report/?date_from={today}&date_to={today}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['daily']), 1)


class PagesAndSeedTests(CinemaFixture):
    """Афиша/страница фильма отдают 200; seed_demo идемпотентен"""

    def test_homepage_200(self):
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)

    def test_movie_page_200(self):
        resp = self.client.get(f'/film/{self.movie.id}/')
        self.assertEqual(resp.status_code, 200)

    def test_seed_demo_twice_idempotent(self):
        out = StringIO()
        call_command('seed_demo', stdout=out)
        movies_after_first = Movie.objects.count()
        sessions_after_first = Session.objects.count()
        bookings_after_first = Booking.objects.count()
        call_command('seed_demo', stdout=out)
        self.assertEqual(Movie.objects.count(), movies_after_first)
        self.assertEqual(Session.objects.count(), sessions_after_first)
        self.assertEqual(Booking.objects.count(), bookings_after_first)
