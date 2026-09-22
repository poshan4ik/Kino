from django.core.management.base import BaseCommand
from django.utils import timezone
from cinema.models import Booking


class Command(BaseCommand):
    help = 'Автоматически отменяет просроченные бронирования (статус created/pending_payment, истёкший expires_at)'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать что будет отменено, но не выполнять отмену',
        )
    
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        now = timezone.now()
        
        expired_bookings = Booking.objects.filter(
            status__in=['created', 'pending_payment'],
            expires_at__lt=now
        ).select_related('session', 'session__movie', 'seat', 'client')
        
        count = expired_bookings.count()
        
        if count == 0:
            self.stdout.write(
                self.style.SUCCESS('Просроченных бронирований не найдено')
            )
            return
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(f'[DRY RUN] Найдено {count} просроченных бронирований:')
            )
            for booking in expired_bookings:
                self.stdout.write(
                    f'  #{booking.id} | {booking.client.username} | '
                    f'{booking.session.movie.title} | '
                    f'Ряд {booking.seat.row} Место {booking.seat.number} | '
                    f'Истёк {booking.expires_at.strftime("%d.%m.%Y %H:%M")}'
                )
        else:
            expired_bookings.update(status='expired')
            self.stdout.write(
                self.style.SUCCESS(f'Успешно отменено {count} просроченных бронирований')
            )
            
            for booking in expired_bookings:
                self.stdout.write(
                    f'  Отменено: #{booking.id} | {booking.client.username} | '
                    f'{booking.session.movie.title}'
                )