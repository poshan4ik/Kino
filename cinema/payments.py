"""Интеграция с онлайн-оплатой Kaspi / Халык (демо-шлюз + webhook).

Провайдер после оплаты шлёт подписанный HMAC-SHA256 webhook; наш endpoint
верифицирует подпись, сверяет сумму и идемпотентно закрывает PaymentIntent
через services.confirm_payment (Ticket + Payment + booking paid).
"""
import hashlib
import hmac
import json
import uuid
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.utils import timezone

from . import services
from .models import BookingStatus, Payment, PaymentIntent, log_audit

SIGNATURE_HEADER = 'X-Signature'
PROVIDERS = ('kaspi', 'halyk')


class PaymentGatewayError(Exception):
    """Ошибка обработки платежа; code — HTTP-статус для webhook."""

    def __init__(self, message, code=400):
        super().__init__(message)
        self.message = message
        self.code = code


def _secret():
    secret = getattr(settings, 'PAYMENT_WEBHOOK_SECRET', '') or settings.SECRET_KEY
    return secret.encode('utf-8')


def canonical_payload(payload: dict) -> bytes:
    """Канонизация JSON: сортированные ключи, без пробелов."""
    return json.dumps(payload, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False).encode('utf-8')


def sign_payload(payload: dict) -> str:
    """HMAC-SHA256 hex-подпись канонического payload."""
    return hmac.new(_secret(), canonical_payload(payload), hashlib.sha256).hexdigest()


def verify_signature(payload: dict, signature: str) -> bool:
    if not signature:
        return False
    return hmac.compare_digest(sign_payload(payload), signature.strip().lower())


def booking_amount(booking) -> Decimal:
    """Сумма брони — только с сервера (базовая цена × скидка)."""
    base_price = booking.session.get_price_for_category(booking.seat.category)
    return services.calculate_ticket_price(base_price, booking.ticket_type)


def create_intent(booking, provider) -> PaymentIntent:
    """Создаёт намерение оплаты для pending-брони, проверяет срок удержания."""
    if provider not in PROVIDERS:
        raise PaymentGatewayError('Неизвестный платёжный провайдер', 400)
    if booking.status != BookingStatus.PENDING_PAYMENT:
        raise PaymentGatewayError('Бронирование не ожидает оплаты', 400)
    if booking.is_expired():
        raise PaymentGatewayError('Время удержания мест истекло', 400)

    intent = PaymentIntent.objects.create(
        booking=booking,
        provider=provider,
        amount=booking_amount(booking),
    )
    log_audit(booking.client, 'create_payment_intent',
              f'Намерение оплаты {intent.external_id} ({provider}) '
              f'на {intent.amount} руб., бронь #{booking.id}')
    return intent


def process_webhook(provider: str, payload: dict, signature: str) -> dict:
    """Верифицирует подпись и идемпотентно обрабатывает результат платежа.

    Возвращает dict-ответ; исключения PaymentGatewayError несут HTTP-код.
    """
    if provider not in PROVIDERS:
        raise PaymentGatewayError('Неизвестный провайдер', 404)
    if not isinstance(payload, dict):
        raise PaymentGatewayError('Некорректный payload', 400)
    if payload.get('provider') != provider:
        raise PaymentGatewayError('Провайдер в payload не совпадает', 400)
    if not verify_signature(payload, signature):
        raise PaymentGatewayError('Неверная подпись webhook', 403)

    external_id = payload.get('external_id')
    if not external_id:
        raise PaymentGatewayError('Нет external_id', 400)
    try:
        intent = PaymentIntent.objects.select_for_update().get(
            external_id=uuid.UUID(str(external_id)), provider=provider,
        )
    except (ValueError, TypeError, PaymentIntent.DoesNotExist):
        raise PaymentGatewayError('Неизвестное намерение оплаты', 404)

    status = payload.get('status')
    if status not in ('success', 'declined'):
        raise PaymentGatewayError('Недопустимый статус платежа', 400)

    # Сверка суммы (payload.amount против суммы intent, с точностью до копеек)
    try:
        amount = Decimal(str(payload.get('amount')))
    except (InvalidOperation, TypeError):
        raise PaymentGatewayError('Некорректная сумма', 400)
    if amount != intent.amount:
        raise PaymentGatewayError('Сумма платежа не совпадает', 400)

    # Идемпотентность: повторный webhook не меняет результат
    if intent.status != PaymentIntent.STATUS_PENDING:
        response = {
            'status': intent.status,
            'external_id': str(intent.external_id),
            'detail': 'already_processed',
        }
        booking = intent.booking
        if intent.status == PaymentIntent.STATUS_SUCCESS and hasattr(booking, 'ticket'):
            response['ticket_id'] = booking.ticket.id
        return response

    intent.payload = payload
    transaction_id = str(payload.get('transaction_id') or '')

    if status == 'declined':
        intent.status = PaymentIntent.STATUS_FAILED
        intent.transaction_id = transaction_id
        intent.processed_at = timezone.now()
        intent.save(update_fields=['payload', 'status', 'transaction_id', 'processed_at'])
        log_audit(intent.booking.client, 'payment_intent_failed',
                  f'Платёж {intent.external_id} ({provider}) отклонён провайдером')
        return {
            'status': intent.status,
            'external_id': str(intent.external_id),
            'detail': 'declined',
        }

    # success → закрываем через штатный сервис (Ticket + Payment + booking paid)
    from django.db import transaction as db_transaction
    try:
        with db_transaction.atomic():
            ticket = services.confirm_payment(
                intent.booking, provider, intent.booking.client,
            )
            intent.status = PaymentIntent.STATUS_SUCCESS
            intent.transaction_id = transaction_id
            intent.processed_at = timezone.now()
            intent.save(update_fields=['payload', 'status', 'transaction_id', 'processed_at'])
            # Проставим transaction_id в созданном Payment
            Payment.objects.filter(ticket=ticket).update(transaction_id=transaction_id)
    except services.BookingError as exc:
        raise PaymentGatewayError(exc.message, 409)

    return {
        'status': intent.status,
        'external_id': str(intent.external_id),
        'ticket_id': ticket.id,
        'detail': 'paid',
    }
