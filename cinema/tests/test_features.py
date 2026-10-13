"""Тесты поздних фич: билет с QR, таймер оплаты, дашборд/CSV,
типы билетов, отзывы, журнал действий."""
from datetime import date, time, timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from ..models import (
    Booking, BookingStatus, Payment, PaymentStatus, Review, Ticket,
    TicketStatus, TicketType, AuditLog,
)
from .. import services
from .base import CinemaFixture


class TicketPageTests(CinemaFixture):
    """Страница билета с QR: доступна только владельцу."""

    def setUp(self):
        super().setUp()
        self.booking = self.make_booking(status='paid')
        self.ticket = Ticket.objects.create(
            booking=self.booking, price=300, barcode='TESTBARCODE1',
        )

    def test_owner_sees_ticket_page_with_qr(self):
        self.client.force_login(self.client_user)
        resp = self.client.get(reverse('ticket_detail', args=[self.ticket.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'data:image/png;base64')
        self.assertContains(resp, 'TESTBARCODE1')

    def test_other_client_forbidden(self):
        other = self.client_user.__class__.objects.create_user(
            username='other1', password='pass123457', role='client')
        self.client.force_login(other)
        resp = self.client.get(reverse('ticket_detail', args=[self.ticket.id]))
        self.assertEqual(resp.status_code, 403)

    def test_cashier_can_open_foreign_ticket(self):
        self.client.force_login(self.cashier)
        resp = self.client.get(reverse('ticket_detail', args=[self.ticket.id]))
        self.assertEqual(resp.status_code, 200)


class PaymentPageTests(CinemaFixture):
    """Страница оплаты с таймером удержания."""

    def setUp(self):
        super().setUp()
        self.booking = self.make_booking(
            status='pending_payment',
            expires_at=timezone.now() + timedelta(minutes=14),
        )

    def test_payment_page_shows_timer_and_price(self):
        self.client.force_login(self.client_user)
        resp = self.client.get(reverse('pay_booking', args=[self.booking.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Место удерживается')
        self.assertContains(resp, '300')

    def test_payment_page_post_creates_ticket(self):
        self.client.force_login(self.client_user)
        resp = self.client.post(reverse('pay_booking', args=[self.booking.id]))
        self.booking.refresh_from_db()
        self.assertTrue(hasattr(self.booking, 'ticket'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('ticket', resp.url)

    def test_expired_booking_redirects_to_seats(self):
        self.booking.expires_at = timezone.now() - timedelta(minutes=1)
        self.booking.save(update_fields=['expires_at'])
        self.client.force_login(self.client_user)
        resp = self.client.get(reverse('pay_booking', args=[self.booking.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'выберите места заново', status_code=200)


class TicketTypePriceTests(CinemaFixture):
    """Типы билетов: скидка считается на сервере."""

    def setUp(self):
        super().setUp()
        self.child = TicketType.objects.create(
            code='child', name='Детский', discount_percent=50)

    def test_calculate_price_with_discount(self):
        price = services.calculate_ticket_price(Decimal('300.00'), self.child)
        self.assertEqual(price, Decimal('150.00'))

    def test_confirm_payment_applies_discount(self):
        booking = self.make_booking(
            status='pending_payment', ticket_type=self.child,
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        ticket = services.confirm_payment(booking, 'online', self.client_user)
        self.assertEqual(ticket.price, Decimal('150.00'))


class ReviewPermissionTests(CinemaFixture):
    """Отзывы: только после посещения сеанса (использованный билет)."""

    def setUp(self):
        super().setUp()
        self.url = '/api/reviews/'

    def test_review_without_ticket_rejected(self):
        self.client.force_login(self.client_user)
        resp = self.client.post(self.url, {
            'movie': self.movie.id, 'rating': 5, 'comment': 'Отлично',
        }, content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_review_with_used_ticket_accepted(self):
        booking = self.make_booking(status='used')
        Ticket.objects.create(
            booking=booking, price=300, barcode='USED123',
            status=TicketStatus.USED, used_at=timezone.now(),
        )
        self.client.force_login(self.client_user)
        resp = self.client.post(self.url, {
            'movie': self.movie.id, 'rating': 5, 'comment': 'Отлично',
        }, content_type='application/json')
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(Review.objects.filter(
            user=self.client_user, movie=self.movie, rating=5).exists())


class DashboardChartTests(CinemaFixture):
    """Дашборд менеджера: Chart.js + фильтр + CSV."""

    def test_manager_dashboard_renders_chart_data(self):
        self.client.force_login(self.manager)
        resp = self.client.get(reverse('manager'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'salesChart')
        self.assertContains(resp, 'topChart')
        self.assertContains(resp, 'hallsChart')
        self.assertContains(resp, 'Экспорт CSV')
        self.assertIn('chart_labels', resp.context)

    def test_manager_dashboard_period_filter(self):
        self.client.force_login(self.manager)
        resp = self.client.get(reverse('manager'), {
            'date_from': '2026-01-01', 'date_to': '2026-01-31',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['date_from'].isoformat(), '2026-01-01')

    def test_csv_export_manager_ok_client_forbidden(self):
        self.client.force_login(self.manager)
        resp = self.client.get(reverse('staff_reports_export'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/csv', resp['Content-Type'])

        self.client.force_login(self.client_user)
        resp = self.client.get(reverse('staff_reports_export'))
        self.assertEqual(resp.status_code, 403)


class AuditLogTests(CinemaFixture):
    """Журнал действий: проверка билета журналируется."""

    def test_check_ticket_writes_audit(self):
        booking = self.make_booking(status='paid')
        ticket = Ticket.objects.create(
            booking=booking, price=300, barcode='AUDIT123')
        services.check_ticket(ticket, actor=self.controller)
        self.assertTrue(AuditLog.objects.filter(
            action='check_ticket', user=self.controller).exists())
