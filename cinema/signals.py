from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from .models import Booking, BookingStatus, Ticket, TicketStatus, Payment, PaymentStatus


@receiver(pre_save, sender=Booking)
def booking_pre_save(sender, instance, **kwargs):
    """Автоустановка expires_at при создании брони"""
    if not instance.pk and not instance.expires_at:
        from datetime import timedelta
        instance.expires_at = timezone.now() + timedelta(minutes=15)


@receiver(post_save, sender=Payment)
def payment_post_save(sender, instance, created, **kwargs):
    """При завершении платежа обновляем статус брони и билета"""
    if created and instance.status == PaymentStatus.COMPLETED:
        ticket = instance.ticket
        booking = ticket.booking
        
        if booking.can_set_status(BookingStatus.PAID):
            booking.set_status(BookingStatus.PAID)
        
        # Возврат билета в «активный» допустим только из «аннулирован»
        if ticket.can_set_status(TicketStatus.ACTIVE):
            ticket.set_status(TicketStatus.ACTIVE)


@receiver(post_save, sender=Ticket)
def ticket_post_save(sender, instance, created, **kwargs):
    """При использовании билета обновляем бронь"""
    if not created and instance.status == TicketStatus.USED:
        booking = instance.booking
        if booking.can_set_status(BookingStatus.USED):
            booking.set_status(BookingStatus.USED)
