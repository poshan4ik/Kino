"""Тесты страниц и служебных эндпоинтов: профайл, staff-разделы, SEO, Swagger.

Отчёт (п.2.4–2.5, 3.4–3.5): рабочие места персонала, кабинет клиента,
фильтрация афиши (дата → жанр → название), экспорт CSV; страницы должны
отдавать 200 нужной роли и 403 чужой.
"""
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from ..models import Booking, BookingStatus, TicketType
from .. import services
from .base import CinemaFixture


class HomepageFilterTests(CinemaFixture):
    """Афиша: серверное сужение выборки по GET-параметрам (?q=, ?genre=, ?date=)."""

    def test_homepage_no_filters_shows_movie(self):
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Тестовый фильм')

    def test_homepage_search_q_found(self):
        resp = self.client.get('/', {'q': 'Тестовый'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Тестовый фильм')

    def test_homepage_search_q_miss(self):
        resp = self.client.get('/', {'q': 'Несуществующееназвание'})
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'Тестовый фильм')

    def test_homepage_genre_filter(self):
        resp = self.client.get('/', {'genre': 'Фантастика'})
        self.assertContains(resp, 'Тестовый фильм')
        resp = self.client.get('/', {'genre': 'Комедия'})
        self.assertNotContains(resp, 'Тестовый фильм')

    def test_homepage_date_filter(self):
        resp = self.client.get('/', {'date': self.session.date.isoformat()})
        self.assertContains(resp, 'Тестовый фильм')
        other = (self.session.date + timedelta(days=5)).isoformat()
        resp = self.client.get('/', {'date': other})
        self.assertNotContains(resp, 'Тестовый фильм')


class BookingPageRenderTests(CinemaFixture):
    """GET /booking/{id}/: схема зала, категории цен и типы билетов."""

    def setUp(self):
        super().setUp()
        self.child_type = TicketType.objects.create(
            code='child', name='Детский', discount_percent=50)

    def test_booking_page_renders_seat_map(self):
        self.client.force_login(self.client_user)
        resp = self.client.get(f'/booking/{self.session.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Выберите места на схеме')
        self.assertContains(resp, 'class="seat standard"')

    def test_booking_page_lists_ticket_types(self):
        self.client.force_login(self.client_user)
        resp = self.client.get(f'/booking/{self.session.id}/')
        self.assertContains(resp, 'Детский')
        self.assertContains(resp, '−50%')

    def test_booking_page_requires_login(self):
        resp = self.client.get(f'/booking/{self.session.id}/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp['Location'])

    def test_booking_page_unknown_session_404(self):
        self.client.force_login(self.client_user)
        resp = self.client.get('/booking/999999/')
        self.assertEqual(resp.status_code, 404)

    def test_hold_minutes_from_settings_not_hardcode(self):
        """Таймер удержания берётся из настроек (в ТЗ отчёта — 14 минут)."""
        from django.conf import settings
        self.assertEqual(settings.BOOKING_HOLD_MINUTES, 14)
        self.client.force_login(self.client_user)
        resp = self.client.get(f'/booking/{self.session.id}/')
        self.assertIn('BOOKING_HOLD_MINUTES', resp.context)
        self.assertEqual(
            resp.context['BOOKING_HOLD_MINUTES'], settings.BOOKING_HOLD_MINUTES
        )
        self.assertContains(resp, f'держится {settings.BOOKING_HOLD_MINUTES} минут')


class ProfilePageTests(CinemaFixture):
    """Кабинет: активные брони, отмена брони, история, доступ."""

    def test_profile_requires_login(self):
        resp = self.client.get('/profile/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp['Location'])

    def test_profile_shows_pending_booking_with_cancel(self):
        self.make_booking(status='pending_payment')
        self.client.force_login(self.client_user)
        resp = self.client.get('/profile/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Ожидает оплаты')
        self.assertContains(resp, 'Отменить')

    def test_profile_shows_active_ticket(self):
        booking = self.make_booking(
            expires_at=timezone.now() + timedelta(minutes=10)
        )
        ticket = services.confirm_payment(booking, 'card', self.client_user)
        self.client.force_login(self.client_user)
        resp = self.client.get('/profile/')
        self.assertContains(resp, ticket.barcode)
        self.assertContains(resp, 'Открыть билет')

    def test_profile_cancel_own_booking_flow(self):
        booking = self.make_booking(status='pending_payment')
        self.client.force_login(self.client_user)
        resp = self.client.post(
            reverse('profile_cancel_booking', args=[booking.id])
        )
        self.assertRedirects(resp, reverse('profile'))
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.CANCELLED)
        self.assertIn(
            self.seat1.id,
            [s.id for s in self.session.get_available_seats()],
        )

    def test_profile_cancel_foreign_booking_404(self):
        booking = self.make_booking(user=self.cashier, seat=self.seat2)
        self.client.force_login(self.client_user)
        resp = self.client.post(
            reverse('profile_cancel_booking', args=[booking.id])
        )
        self.assertEqual(resp.status_code, 404)


class StaffPagesRoleTests(CinemaFixture):
    """Staff-разделы: доступ по ролям и рендер без ошибок (п.3.5)."""

    def test_manager_sees_all_staff_pages(self):
        self.client.force_login(self.manager)
        for url_name in [
            'staff_movies', 'staff_sessions', 'staff_halls',
            'staff_bookings', 'staff_tickets', 'staff_clients',
            'staff_sales', 'staff_reports', 'staff_users',
        ]:
            resp = self.client.get(reverse(url_name))
            self.assertEqual(resp.status_code, 200, url_name)

    def test_admin_sees_all_staff_pages(self):
        self.client.force_login(self.admin)
        for url_name in [
            'staff_movies', 'staff_sessions', 'staff_halls',
            'staff_bookings', 'staff_tickets', 'staff_clients',
            'staff_sales', 'staff_reports', 'staff_users',
        ]:
            resp = self.client.get(reverse(url_name))
            self.assertEqual(resp.status_code, 200, url_name)

    def test_cashier_allowed_and_denied(self):
        self.client.force_login(self.cashier)
        for url_name in ['staff_bookings', 'staff_tickets',
                         'staff_clients', 'staff_sales']:
            resp = self.client.get(reverse(url_name))
            self.assertEqual(resp.status_code, 200, url_name)
        for url_name in ['staff_movies', 'staff_sessions', 'staff_halls',
                         'staff_reports', 'staff_users']:
            resp = self.client.get(reverse(url_name))
            self.assertEqual(resp.status_code, 403, url_name)

    def test_controller_allowed_and_denied(self):
        self.client.force_login(self.controller)
        resp = self.client.get(reverse('staff_bookings'))
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get(reverse('staff_tickets'))
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get(reverse('staff_clients'))
        self.assertEqual(resp.status_code, 403)

    def test_client_denied_everywhere(self):
        self.client.force_login(self.client_user)
        for url_name in [
            'staff_movies', 'staff_sessions', 'staff_halls',
            'staff_bookings', 'staff_tickets', 'staff_clients',
            'staff_sales', 'staff_reports', 'staff_users',
        ]:
            resp = self.client.get(reverse(url_name))
            self.assertEqual(resp.status_code, 403, url_name)

    def test_bookings_page_status_filter(self):
        booking = self.make_booking(status='pending_payment')
        self.client.force_login(self.manager)
        resp = self.client.get(reverse('staff_bookings'), {'status': 'paid'})
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, f'#{booking.id}')
        resp = self.client.get(reverse('staff_bookings'))
        self.assertContains(resp, f'#{booking.id}')
