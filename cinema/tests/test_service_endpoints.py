"""Служебные страницы: вход/выход, SEO, Swagger, 404."""
from django.urls import reverse

from .base import CinemaFixture


class AuthPagesTests(CinemaFixture):
    """Вход/регистрация/выход: страницы и редиректы."""

    def test_login_page_200(self):
        resp = self.client.get(reverse('login'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'АВРОРА')

    def test_register_page_200(self):
        resp = self.client.get(reverse('register'))
        self.assertEqual(resp.status_code, 200)

    def test_login_redirects_client_to_profile(self):
        resp = self.client.post(reverse('login'), {
            'username': 'client1', 'password': 'pass123457',
        })
        self.assertRedirects(resp, reverse('profile'))

    def test_login_wrong_password_shows_error(self):
        resp = self.client.post(reverse('login'), {
            'username': 'client1', 'password': 'wrongpass1',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Пожалуйста', resp.context['form'].errors['__all__'][0])

    def test_logout_post_redirects_home(self):
        self.client.force_login(self.client_user)
        resp = self.client.post(reverse('logout'))
        self.assertRedirects(resp, reverse('home'))

    def test_anonymous_home_contains_login_links(self):
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'href="/login/"', resp.content)

    def test_authenticated_home_shows_profile_chip(self):
        self.client.force_login(self.client_user)
        resp = self.client.get('/')
        self.assertIn(b'href="/profile/"', resp.content)


class ServiceEndpointsTests(CinemaFixture):
    """robots.txt, sitemap.xml, Swagger, 404."""

    def test_robots_txt(self):
        resp = self.client.get('/robots.txt')
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('User-agent: *', body)
        self.assertIn('Disallow: /manager/', body)
        self.assertIn('Sitemap:', body)

    def test_sitemap_xml(self):
        resp = self.client.get('/sitemap.xml')
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('<urlset', body)
        self.assertIn(f'/film/{self.movie.id}/', body)

    def test_openapi_schema_ok(self):
        resp = self.client.get('/api/schema/')
        self.assertEqual(resp.status_code, 200)

    def test_swagger_ui_ok(self):
        resp = self.client.get('/api/docs/')
        self.assertEqual(resp.status_code, 200)

    def test_page_not_found_404(self):
        resp = self.client.get('/nepopa/no-date/123/')
        self.assertEqual(resp.status_code, 404)

    def test_movie_reviews_api_key_named_reviews(self):
        from django.utils import timezone

        from ..models import Review, Ticket, TicketStatus
        booking = self.make_booking(status='used')
        Ticket.objects.create(
            booking=booking, price=300, barcode='APIREV1',
            status=TicketStatus.USED, used_at=timezone.now(),
        )
        Review.objects.create(
            user=self.client_user, movie=self.movie, rating=4,
            comment='Норм', )
        resp = self.client.get(f'/api/movies/{self.movie.id}/reviews/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['count'], 1)
        self.assertEqual(resp.data['rating'], 4.0)
        self.assertEqual(len(resp.data['reviews']), 1)
