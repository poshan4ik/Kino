from django import template
from django.db.models import Sum

register = template.Library()


@register.simple_tag
def admin_stats():
    """Сводка для главной страницы админки (сегодня)."""
    from django.utils import timezone
    from decimal import Decimal

    from cinema.models import Booking, Movie, Payment, Session, Ticket, User

    today = timezone.localdate()
    revenue = (
        Payment.objects.filter(created_at__date=today, status='completed')
        .aggregate(s=Sum('amount'))['s'] or Decimal('0')
    )
    return {
        'movies': Movie.objects.filter(status='active').count(),
        'sessions_today': Session.objects.filter(date=today, is_active=True).count(),
        'tickets_today': Ticket.objects.filter(booking__session__date=today).count(),
        'bookings_active': Booking.objects.filter(
            status__in=['created', 'pending_payment']
        ).count(),
        'revenue_today': revenue,
        'clients': User.objects.filter(role='client').count(),
    }
