from django.test import override_settings
from django.core.cache import cache
from django.utils import timezone
from xml.etree import ElementTree

from .base import CinemaFixture
from cinema.demo import refresh_demo_schedule
from cinema.models import Movie, Session
from cinema.management.commands.seed_demo import DEMO_MOVIES


@override_settings(SITE_URL="https://kino-aurora.onrender.com", DEMO_MODE=False)
class SearchMetadataTests(CinemaFixture):
    def test_canonical_ignores_query_and_alias(self):
        home = self.client.get("/?q=test")
        self.assertContains(home, 'rel="canonical" href="https://kino-aurora.onrender.com/"')
        alias = self.client.get(f"/movie/{self.movie.pk}/")
        self.assertContains(alias, f'rel="canonical" href="https://kino-aurora.onrender.com/film/{self.movie.pk}/"')
        self.assertNotContains(alias, 'name="robots" content="noindex')

    def test_sitemap_includes_upcoming_not_archived(self):
        upcoming = Movie.objects.create(title="Soon", genre=self.genre, duration=90, age_rating=12, status="upcoming")
        hidden = Movie.objects.create(title="Old", genre=self.genre, duration=90, age_rating=12, status="archived")
        response = self.client.get("/sitemap.xml")
        root = ElementTree.fromstring(response.content)
        locations = [node.text for node in root.findall("{*}url/{*}loc")]
        self.assertIn(f"https://kino-aurora.onrender.com/film/{upcoming.pk}/", locations)
        self.assertNotIn(f"https://kino-aurora.onrender.com/film/{hidden.pk}/", locations)
        self.assertContains(self.client.get("/robots.txt"), "Sitemap: https://kino-aurora.onrender.com/sitemap.xml")

    @override_settings(GOOGLE_SITE_VERIFICATION="google-token", YANDEX_VERIFICATION="yandex-token")
    def test_webmaster_tokens_and_private_pages(self):
        self.assertContains(self.client.get("/"), 'name="google-site-verification" content="google-token"')
        login = self.client.get("/login/")
        self.assertContains(login, 'name="robots" content="noindex, nofollow"')
        self.assertNotContains(login, 'name="google-site-verification"')

    @override_settings(DEMO_MODE=True)
    def test_demo_is_clearly_labelled(self):
        self.assertContains(self.client.get("/"), "Учебный демонстрационный сайт")


class DemoScheduleTests(CinemaFixture):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.movie.title = DEMO_MOVIES[0][0]
        self.movie.save()

    @override_settings(DEMO_MODE=False)
    def test_real_site_is_untouched(self):
        refresh_demo_schedule()
        self.assertEqual(Session.objects.count(), 1)

    @override_settings(DEMO_MODE=True)
    def test_demo_refresh_is_idempotent_and_preserves_existing_sessions(self):
        refresh_demo_schedule()
        count = Session.objects.count()
        self.assertGreater(count, 1)
        self.assertTrue(Session.objects.filter(pk=self.session.pk).exists())
        cache.clear()
        refresh_demo_schedule()
        self.assertEqual(Session.objects.count(), count)
        self.assertEqual(Session.objects.filter(date__gte=timezone.localdate()).count(), count)
