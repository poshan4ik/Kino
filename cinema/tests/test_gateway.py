"""Тесты платёжного шлюза Kaspi/Халык (intent + подписанный webhook)."""
import json
import uuid
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .. import payments
from ..models import Payment, PaymentIntent
from .base import CinemaFixture


def make_payload(intent, status='success', amount=None, tx=None):
    return {
        'provider': intent.provider,
        'external_id': str(intent.external_id),
        'status': status,
        'amount': str(amount if amount is not None else intent.amount),
        'transaction_id': tx or f'{intent.provider}-TESTTX0000000001',
        'timestamp': '2026-10-18T12:00:00+06:00',
    }


class PaymentIntentTests(CinemaFixture):
    """Создание intent и редирект в демо-шлюз."""

    def setUp(self):
        super().setUp()
        self.booking = self.make_booking(
            status='pending_payment',
            expires_at=timezone.now() + timedelta(minutes=14),
        )

    def test_create_intent_amount_from_server(self):
        intent = payments.create_intent(self.booking, 'kaspi')
        self.assertEqual(intent.amount, Decimal('300.00'))
        self.assertEqual(intent.status, PaymentIntent.STATUS_PENDING)
        self.assertEqual(intent.provider, 'kaspi')

    def test_create_intent_rejects_unknown_provider(self):
        with self.assertRaises(payments.PaymentGatewayError):
            payments.create_intent(self.booking, 'visa')

    def test_create_intent_rejects_expired_booking(self):
        self.booking.expires_at = timezone.now() - timedelta(minutes=1)
        self.booking.save(update_fields=['expires_at'])
        with self.assertRaises(payments.PaymentGatewayError):
            payments.create_intent(self.booking, 'kaspi')

    def test_pay_post_with_kaspi_redirects_to_gateway(self):
        self.client.force_login(self.client_user)
        resp = self.client.post(
            reverse('pay_booking', args=[self.booking.id]), {'method': 'kaspi'},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/pay/gateway/', resp.url)
        intent = PaymentIntent.objects.get()
        self.assertIn(str(intent.external_id), resp.url)

    def test_pay_post_with_halyk_creates_intent(self):
        self.client.force_login(self.client_user)
        self.client.post(
            reverse('pay_booking', args=[self.booking.id]), {'method': 'halyk'},
        )
        intent = PaymentIntent.objects.get()
        self.assertEqual(intent.provider, 'halyk')

    def test_api_pay_kaspi_returns_gateway_redirect(self):
        self.client.force_login(self.client_user)
        resp = self.client.post('/api/bookings/pay/', {
            'booking_ids': [self.booking.id], 'method': 'kaspi',
        }, content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        intent = PaymentIntent.objects.get()
        self.assertEqual(intent.booking_id, self.booking.id)
        self.assertEqual(intent.provider, 'kaspi')
        self.assertIn(str(intent.external_id), resp.data['redirect'])
        self.assertIn('/pay/gateway/', resp.data['redirect'])
        # бронь ещё не оплачена — ждём webhook
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'pending_payment')

    def test_api_pay_halyk_creates_intent_for_each_booking(self):
        b2 = self.make_booking(
            user=None, seat=self.seat2,
            status='pending_payment',
            expires_at=timezone.now() + timedelta(minutes=14),
        )
        self.client.force_login(self.client_user)
        resp = self.client.post('/api/bookings/pay/', {
            'booking_ids': [self.booking.id, b2.id], 'method': 'halyk',
        }, content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        intents = list(PaymentIntent.objects.order_by('booking_id'))
        self.assertEqual(len(intents), 2)
        self.assertEqual([i.provider for i in intents], ['halyk', 'halyk'])
        self.assertTrue(
            any(str(i.external_id) in resp.data['redirect'] for i in intents),
            resp.data['redirect'],
        )
        self.assertEqual(len(resp.data['external_ids']), 2)

    def test_api_pay_kaspi_denied_for_cash_only_gate(self):
        # 'cash' для клиента по-прежнему запрещён
        self.client.force_login(self.client_user)
        resp = self.client.post('/api/bookings/pay/', {
            'booking_ids': [self.booking.id], 'method': 'cash',
        }, content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_gateway_page_owner_sees_amount(self):
        intent = payments.create_intent(self.booking, 'kaspi')
        self.client.force_login(self.client_user)
        resp = self.client.get(
            reverse('payment_gateway', args=[intent.external_id]),
        )
        self.assertEqual(resp.status_code, 200)
        # ru-локализация: Decimal 300.00 → «300,00»
        self.assertContains(resp, '300,00')
        self.assertContains(resp, 'Kaspi Gold')

    def test_gateway_page_denied_for_other_user(self):
        intent = payments.create_intent(self.booking, 'kaspi')
        from ..models import User
        other = User.objects.create_user(
            username='other1', password='pass123457', role='client')
        self.client.force_login(other)
        resp = self.client.get(
            reverse('payment_gateway', args=[intent.external_id]),
        )
        self.assertEqual(resp.status_code, 403)


class GatewaySuccessTests(CinemaFixture):
    """Полный цикл: кнопка «Оплатить» → success → Ticket + Payment."""

    def setUp(self):
        super().setUp()
        self.booking = self.make_booking(
            status='pending_payment',
            expires_at=timezone.now() + timedelta(minutes=14),
        )

    def _decide(self, intent, decision):
        self.client.force_login(self.client_user)
        return self.client.post(
            reverse('payment_gateway_decide', args=[intent.external_id]),
            {'decision': decision},
        )

    def test_kaspi_success_creates_ticket_and_payment(self):
        intent = payments.create_intent(self.booking, 'kaspi')
        resp = self._decide(intent, 'success')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/ticket/', resp.url)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'paid')
        ticket = self.booking.ticket
        payment = Payment.objects.get(ticket=ticket)
        self.assertEqual(payment.method, 'kaspi')
        self.assertEqual(payment.status, 'completed')
        self.assertTrue(payment.transaction_id.startswith('kaspi-'))
        intent.refresh_from_db()
        self.assertEqual(intent.status, PaymentIntent.STATUS_SUCCESS)
        self.assertIsNotNone(intent.processed_at)

    def test_halyk_success_creates_ticket_and_payment(self):
        intent = payments.create_intent(self.booking, 'halyk')
        resp = self._decide(intent, 'success')
        self.assertIn('/ticket/', resp.url)
        payment = Payment.objects.get()
        self.assertEqual(payment.method, 'halyk')

    def test_declined_keeps_booking_pending(self):
        intent = payments.create_intent(self.booking, 'kaspi')
        resp = self._decide(intent, 'declined')
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f'/pay/{self.booking.id}/', resp.url)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'pending_payment')
        self.assertFalse(hasattr(self.booking, 'ticket'))
        intent.refresh_from_db()
        self.assertEqual(intent.status, PaymentIntent.STATUS_FAILED)

    def test_cannot_pay_twice(self):
        intent = payments.create_intent(self.booking, 'kaspi')
        self._decide(intent, 'success')
        # Повторная попытка закрытой брони
        resp = self._decide(intent, 'success')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Payment.objects.count(), 1)


class WebhookSignatureTests(CinemaFixture):
    """HTTP-webhook: подпись, сумма, идемпотентность."""

    def setUp(self):
        super().setUp()
        self.booking = self.make_booking(
            status='pending_payment',
            expires_at=timezone.now() + timedelta(minutes=14),
        )
        self.intent = payments.create_intent(self.booking, 'kaspi')
        self.url = reverse('payment_webhook', args=['kaspi'])

    def _post(self, payload, signature=None):
        sig = signature if signature is not None else payments.sign_payload(payload)
        return self.client.post(
            self.url, data=json.dumps(payload), content_type='application/json',
            headers={'X-Signature': sig} if sig else {},
        )

    def test_valid_signature_pays_booking(self):
        resp = self._post(make_payload(self.intent, 'success'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('ticket_id', data)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'paid')

    def test_invalid_signature_rejected_403(self):
        resp = self._post(make_payload(self.intent, 'success'), signature='deadbeef')
        self.assertEqual(resp.status_code, 403)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'pending_payment')

    def test_missing_signature_rejected_403(self):
        payload = make_payload(self.intent, 'success')
        resp = self.client.post(
            self.url, data=json.dumps(payload), content_type='application/json',
        )
        self.assertEqual(resp.status_code, 403)

    def test_amount_mismatch_rejected_400(self):
        resp = self._post(make_payload(self.intent, 'success', amount='100.00'))
        self.assertEqual(resp.status_code, 400)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'pending_payment')

    def test_unknown_external_id_404(self):
        payload = make_payload(self.intent, 'success')
        payload['external_id'] = str(uuid.uuid4())
        resp = self._post(payload)
        self.assertEqual(resp.status_code, 404)

    def test_idempotent_double_webhook(self):
        resp1 = self._post(make_payload(self.intent, 'success'))
        resp2 = self._post(make_payload(self.intent, 'success'))
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.json()['detail'], 'already_processed')
        self.assertEqual(Payment.objects.count(), 1)

    def test_declined_webhook(self):
        resp = self._post(make_payload(self.intent, 'declined'))
        self.assertEqual(resp.status_code, 200)
        self.intent.refresh_from_db()
        self.assertEqual(self.intent.status, PaymentIntent.STATUS_FAILED)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'pending_payment')

    def test_provider_mismatch_400(self):
        payload = make_payload(self.intent, 'success')
        payload['provider'] = 'halyk'
        resp = self.client.post(
            self.url, data=json.dumps(payload), content_type='application/json',
            headers={'X-Signature': payments.sign_payload(payload)},
        )
        self.assertEqual(resp.status_code, 400)

    def test_invalid_status_400(self):
        resp = self._post(make_payload(self.intent, 'refunded'))
        self.assertEqual(resp.status_code, 400)

    def test_expired_booking_conflict_409(self):
        self.booking.expires_at = timezone.now() - timedelta(minutes=1)
        self.booking.save(update_fields=['expires_at'])
        resp = self._post(make_payload(self.intent, 'success'))
        self.assertEqual(resp.status_code, 409)
        self.intent.refresh_from_db()
        self.assertEqual(self.intent.status, PaymentIntent.STATUS_PENDING)

    def test_sign_verify_roundtrip(self):
        payload = make_payload(self.intent, 'success')
        self.assertTrue(payments.verify_signature(payload, payments.sign_payload(payload)))
        self.assertFalse(payments.verify_signature(payload, 'bad-signature'))
