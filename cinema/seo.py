"""Public URLs and template metadata for search engines."""
from django.conf import settings
from django.urls import reverse


def public_url(request, path):
    origin = settings.SITE_URL or request.build_absolute_uri("/").rstrip("/")
    return origin.rstrip("/") + path


def metadata(request):
    match = request.resolver_match
    route = match.url_name if match else None
    canonical = ""
    if route == "home":
        canonical = public_url(request, reverse("home"))
    elif route in {"film", "movie_detail"}:
        canonical = public_url(request, reverse("film", kwargs={"pk": match.kwargs["pk"]}))
    return {
        "seo_canonical_url": canonical,
        "google_site_verification": settings.GOOGLE_SITE_VERIFICATION,
        "yandex_verification": settings.YANDEX_VERIFICATION,
        "demo_mode": settings.DEMO_MODE,
    }
