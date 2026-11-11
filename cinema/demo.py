"""Keep the explicitly enabled educational demo usable after seed dates expire."""
import io
import logging
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def refresh_demo_schedule():
    if not settings.DEMO_MODE:
        return
    key = f"demo-schedule:{timezone.localdate().isoformat()}"
    if not cache.add(key, True, timeout=21600):
        return
    try:
        from cinema.management.commands.seed_demo import Command, DEMO_HALLS
        from cinema.models import Hall
        with transaction.atomic():
            # Serialize workers before reading existing intervals; never delete sessions or bookings.
            list(Hall.objects.select_for_update().filter(number__in=[h[0] for h in DEMO_HALLS]).order_by('pk'))
            Command(stdout=io.StringIO()).seed_sessions()
    except Exception:
        cache.delete(key)
        logger.exception("Could not refresh educational demo schedule")
