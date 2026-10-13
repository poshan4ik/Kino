"""Централизованная бизнес-логика бронирования, оплаты и возврата.

Все вьюхи (API hold/pay, HTML-форма, serializer create) обязаны идти через
этот модуль, чтобы лимиты/проверки не расходились.

Публичные сервисы:
    create_booking     — атомарное удержание мест («всё или ничего»)
    confirm_payment    — оплата брони, создание билета со штрихкодом uuid4
    cancel_booking     — отмена брони и освобождение места
    refund_ticket      — возврат билета (нельзя после начала сеанса)
    check_ticket       — проверка/погашение билета контролёром
    expire_old_bookings — массовое истечение просроченных броней
"""
from datetime import datetime, timedelta
from uuid import uuid4

from django.conf import settings
from django.db import transaction, connection
from django.db.utils import IntegrityError
from django.utils import timezone

from .models import (
    Booking, BookingStatus, Payment, PaymentStatus,
    Session, Seat, Ticket, TicketStatus, log_audit,
)

ACTIVE_BOOKING_STATUSES = [
    BookingStatus.CREATED, BookingStatus.PENDING_PAYMENT,
    BookingStatus.PAID, BookingStatus.USED,
]


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


def create_booking(user, session, seat_ids):
    """Атомарно удерживает места на BOOKING_HOLD_MINUTES («всё или ничего»).

    transaction.atomic() + select_for_update(); нельзя занятые места,
    прошедший сеанс, места чужого зала; лимит BOOKING_MAX_SEATS мест.
    Сумма не принимается извне — фиксируется на сеансе.
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
                    status=BookingStatus.PENDING_PAYMENT,
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


# Обратная совместимость: старое имя сервиса
create_hold = create_booking


def confirm_payment(booking, method, actor):
    """Оплачивает бронь и создаёт Ticket + Completed Payment.

    Нельзя оплатить дважды, просроченную или отменённую бронь.
    Цена берётся с сеанса (сумма не из запроса), штрихкод — uuid4.
    Статус Booking → paid и Ticket → active ставит сигнал payment_post_save.
    """
    if booking.status not in [BookingStatus.PENDING_PAYMENT]:
        raise BookingError('Бронирование не ожидает оплаты')
    if booking.expires_at and booking.expires_at < timezone.now():
        raise BookingError('Время удержания мест истекло — обновите выбор')
    if session_start_at(booking.session) <= timezone.now():
        raise BookingError('Сеанс уже начался — оплата невозможна')

    with transaction.atomic():
        ticket = Ticket.objects.create(
            booking=booking,
            price=booking.session.get_price_for_category(booking.seat.category),
            barcode=str(uuid4()).replace('-', '').upper()[:20],
            status=TicketStatus.ACTIVE,
        )
        Payment.objects.create(
            ticket=ticket,
            amount=ticket.price,
            method=method,
            status=PaymentStatus.COMPLETED,
            completed_at=timezone.now(),
        )
        log_audit(actor, 'confirm_payment',
                  f'Оплата брони #{booking.id} ({booking.session.movie.title}), '
                  f'билет {ticket.barcode}, {ticket.price} руб.')
    return ticket


def refund_ticket(booking, actor):
    """Возврат: билет → refunded, платежи → refunded, бронь → cancelled.

    Нельзя вернуть после начала сеанса.
    """
    if session_start_at(booking.session) <= timezone.now():
        raise BookingError('Нельзя вернуть билет после начала сеанса')
    if booking.status in [BookingStatus.CANCELLED, BookingStatus.EXPIRED]:
        raise BookingError('Бронь уже отменена')
    if booking.status == BookingStatus.USED:
        raise BookingError('Билет уже использован — возврат невозможен')

    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=booking.pk)
        if booking.status in [BookingStatus.CANCELLED, BookingStatus.EXPIRED]:
            raise BookingError('Бронь уже отменена')
        if booking.status == BookingStatus.USED:
            raise BookingError('Билет уже использован — возврат невозможен')

        if hasattr(booking, 'ticket'):
            ticket = booking.ticket
            ticket.set_status(TicketStatus.REFUNDED)
            Payment.objects.filter(ticket=ticket, status__in=[
                PaymentStatus.PENDING, PaymentStatus.COMPLETED,
            ]).update(status=PaymentStatus.REFUNDED)

        booking.set_status(BookingStatus.CANCELLED)

    log_audit(
        actor, 'refund_booking',
        f'Возврат брони #{booking.id} ({booking.session.movie.title}), '
        f'место {booking.seat.row}/{booking.seat.number}',
    )
    return booking


# Обратная совместимость
refund_booking = refund_ticket


def cancel_booking(booking, actor, force=False):
    """Отмена брони. Клиент может отменить только свою непогашенную бронь
    до начала сеанса; персонал — любую (force=True)."""
    if booking.status in [BookingStatus.USED, BookingStatus.CANCELLED, BookingStatus.EXPIRED]:
        raise BookingError('Нельзя отменить это бронирование')
    if not force:
        if session_start_at(booking.session) <= timezone.now():
            raise BookingError('Сеанс уже начался — отмена невозможна')

    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=booking.pk)
        if booking.status in [BookingStatus.USED, BookingStatus.CANCELLED, BookingStatus.EXPIRED]:
            raise BookingError('Нельзя отменить это бронирование')
        if hasattr(booking, 'ticket'):
            ticket = booking.ticket
            ticket.set_status(TicketStatus.CANCELLED)
            Payment.objects.filter(
                ticket=ticket, status=PaymentStatus.PENDING,
            ).update(status=PaymentStatus.FAILED)
        booking.set_status(BookingStatus.CANCELLED)

    log_audit(
        actor, 'cancel_booking',
        f'Отмена брони #{booking.id} ({booking.session.movie.title}), '
        f'место {booking.seat.row}/{booking.seat.number}',
    )
    return booking


def check_ticket(ticket):
    """Проверка билета контролёром: валидный помечается использованным.

    Повторная проверка, возвращённый/аннулированный — BookingError
    с понятным сообщением; неизвестный штрихкод — Ticket.DoesNotExist.
    Возвращает (ticket, message).
    """
    if ticket.status == TicketStatus.USED:
        raise BookingError('Билет уже использован')
    if ticket.status in [TicketStatus.REFUNDED, TicketStatus.CANCELLED]:
        raise BookingError('Билет аннулирован или возвращён')
    ticket.mark_used()
    return ticket, 'Билет действителен, вход разрешён'


def expire_old_bookings():
    """Отменяет брони с истёкшим expires_at (created/pending_payment).

    Возвращает количество отменённых.
    """
    now = timezone.now()
    expired = Booking.objects.filter(
        status__in=[BookingStatus.CREATED, BookingStatus.PENDING_PAYMENT],
        expires_at__lt=now,
    )
    # Материализуем ДО update(): QuerySet ленивый, после update()
    # повторный запрос вернул бы уже пустой результат
    bookings = list(expired)
    if not bookings:
        return 0
    Booking.objects.filter(
        id__in=[b.id for b in bookings]
    ).update(status=BookingStatus.EXPIRED)
    return len(bookings)


def issue_ticket(booking, method, actor):
    """Совместимость: старое имя confirm_payment (см. confirm_payment)."""
    return confirm_payment(booking, method, actor)
