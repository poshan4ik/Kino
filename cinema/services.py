"""Централизованная бизнес-логика бронирования, оплаты и возврата.

Все вьюхи (API hold/pay, HTML-форма, serializer create) обязаны идти через
этот модуль, чтобы лимиты/проверки не расходились.
"""
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction, connection
from django.db.utils import IntegrityError
from django.utils import timezone

from .models import Booking, Payment, Session, Seat, Ticket, log_audit

ACTIVE_BOOKING_STATUSES = ['created', 'pending_payment', 'paid', 'used']


class BookingError(Exception):
    """Бизнес-ошибка бронирования с HTTP-кодом."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def session_start_at(session):
    """Локальное время начала сеанса (aware)."""
    naive = datetime.combine(session.date, session.time)
    return timezone.make_aware(naive, timezone.get_current_timezone())


def validate_session_bookable(session):
    if not session.is_active:
        raise BookingError('Сеанс неактивен')
    if session_start_at(session) <= timezone.now():
        raise BookingError('Сеанс уже начался — бронирование недоступно')


def validate_seat_ids(session, seat_ids):
    if not seat_ids:
        raise BookingError('Не выбрано ни одного места')
    if len(seat_ids) != len(set(seat_ids)):
        raise BookingError('Некорректный выбор мест')
    if len(seat_ids) > settings.BOOKING_MAX_SEATS:
        raise BookingError(f'Максимум {settings.BOOKING_MAX_SEATS} мест за раз')
    found = Seat.objects.filter(id__in=seat_ids, hall=session.hall).count()
    if found != len(seat_ids):
        raise BookingError('Некорректный выбор мест (место не принадлежит залу сеанса)')


def create_hold(user, session, seat_ids):
    """Атомарно удерживает места на BOOKING_HOLD_MINUTES («всё или ничего»).

    Возвращает (bookings, expires_at).
    """
    validate_session_bookable(session)
    validate_seat_ids(session, seat_ids)
    expires_at = timezone.now() + timedelta(minutes=settings.BOOKING_HOLD_MINUTES)

    class SeatTaken(BookingError):
        def __init__(self):
            super().__init__('Одно или несколько мест уже заняты')

    try:
        with transaction.atomic():
            seats_qs = Seat.objects.filter(id__in=seat_ids, hall=session.hall).order_by('id')
            if connection.features.has_select_for_update:
                seats_qs = seats_qs.select_for_update()
            seats = list(seats_qs)

            booked_qs = Booking.objects.filter(
                session=session, seat__in=seats, status__in=ACTIVE_BOOKING_STATUSES
            )
            if connection.features.has_select_for_update:
                booked_qs = booked_qs.select_for_update()
            if booked_qs.exists():
                raise SeatTaken()

            bookings = [
                Booking.objects.create(
                    client=user,
                    session=session,
                    seat=seat,
                    status='pending_payment',
                    expires_at=expires_at,
                )
                for seat in seats
            ]
    except SeatTaken:
        raise
    except IntegrityError:
        raise BookingError(
            'Это место только что забронировали, выберите другое'
        )

    return bookings, expires_at


def refund_booking(booking, actor):
    """Возврат: билет → refunded, платежи → refunded, бронь → cancelled.

    Нельзя вернуть после начала сеанса.
    """
    if session_start_at(booking.session) <= timezone.now():
        raise BookingError('Нельзя вернуть билет после начала сеанса')
    if booking.status in ['cancelled', 'expired']:
        raise BookingError('Бронь уже отменена')
    if booking.status == 'used':
        raise BookingError('Билет уже использован — возврат невозможен')

    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=booking.pk)
        if booking.status in ['cancelled', 'expired']:
            raise BookingError('Бронь уже отменена')
        if booking.status == 'used':
            raise BookingError('Билет уже использован — возврат невозможен')

        if hasattr(booking, 'ticket'):
            ticket = booking.ticket
            ticket.status = 'refunded'
            ticket.save(update_fields=['status'])
            Payment.objects.filter(ticket=ticket).exclude(
                status='refunded'
            ).update(status='refunded')

        booking.status = 'cancelled'
        booking.save(update_fields=['status'])

    log_audit(
        actor, 'refund_booking',
        f'Возврат брони #{booking.id} ({booking.session.movie.title}), '
        f'место {booking.seat.row}/{booking.seat.number}',
    )
    return booking


def cancel_booking(booking, actor, force=False):
    """Отмена брони. Клиент может отменить только свою непогашенную бронь
    до начала сеанса; персонал — любую (force=True)."""
    if booking.status in ['used', 'cancelled', 'expired']:
        raise BookingError('Нельзя отменить это бронирование')
    if not force:
        if session_start_at(booking.session) <= timezone.now():
            raise BookingError('Сеанс уже начался — отмена невозможна')

    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=booking.pk)
        if booking.status in ['used', 'cancelled', 'expired']:
            raise BookingError('Нельзя отменить это бронирование')
        if hasattr(booking, 'ticket'):
            ticket = booking.ticket
            ticket.status = 'cancelled'
            ticket.save(update_fields=['status'])
            Payment.objects.filter(ticket=ticket, status='pending').update(
                status='failed'
            )
        booking.status = 'cancelled'
        booking.save(update_fields=['status'])

    log_audit(
        actor, 'cancel_booking',
        f'Отмена брони #{booking.id} ({booking.session.movie.title}), '
        f'место {booking.seat.row}/{booking.seat.number}',
    )
    return booking
