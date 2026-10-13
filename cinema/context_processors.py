"""Глобальные бизнес-лимиты для шаблонов."""


def booking_limits(request):
    from django.conf import settings
    return {
        'BOOKING_MAX_SEATS': settings.BOOKING_MAX_SEATS,
        'BOOKING_HOLD_MINUTES': settings.BOOKING_HOLD_MINUTES,
    }
