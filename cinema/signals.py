from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from .models import Booking, Ticket, Payment


@receiver(pre_save, sender=Booking)
def booking_pre_save(sender, instance, **kwargs):
    """Автоустановка expires_at при создании брони"""
    if not instance.pk and not instance.expires_at:
        from datetime import timedelta
        instance.expires_at = timezone.now() + timedelta(minutes=15)


@receiver(post_save, sender=Payment)
def payment_post_save(sender, instance, created, **kwargs):
    """При завершении платежа обновляем статус брони и билета"""
    if created and instance.status == 'completed':
        ticket = instance.ticket
        booking = ticket.booking
        
        if booking.status in ['created', 'pending_payment']:
            booking.status = 'paid'
            booking.save(update_fields=['status'])
        
        if ticket.status != 'active':
            ticket.status = 'active'
            ticket.save(update_fields=['status'])


@receiver(post_save, sender=Ticket)
def ticket_post_save(sender, instance, created, **kwargs):
    """При использовании билета обновляем бронь"""
    if not created and instance.status == 'used':
        booking = instance.booking
        if booking.status != 'used':
            booking.status = 'used'
            booking.save(update_fields=['status'])