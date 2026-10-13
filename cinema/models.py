from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


class BookingStatus(models.TextChoices):
    CREATED = 'created', 'Создано'
    PENDING_PAYMENT = 'pending_payment', 'Ожидает оплаты'
    PAID = 'paid', 'Оплачено'
    USED = 'used', 'Использовано'
    CANCELLED = 'cancelled', 'Отменено'
    EXPIRED = 'expired', 'Просрочено'


class TicketStatus(models.TextChoices):
    ACTIVE = 'active', 'Активен'
    USED = 'used', 'Использован'
    REFUNDED = 'refunded', 'Возвращён'
    CANCELLED = 'cancelled', 'Аннулирован'


class PaymentStatus(models.TextChoices):
    PENDING = 'pending', 'Ожидает'
    COMPLETED = 'completed', 'Завершён'
    FAILED = 'failed', 'Неудача'
    REFUNDED = 'refunded', 'Возвращён'


# Единое место правил переходов статусов:
# pending → paid → used; pending → cancelled/expired; paid → refunded
# (по брони возврат = cancelled, по билету/платежу = refunded).
STATUS_TRANSITIONS = {
    'booking': {
        BookingStatus.CREATED.value: {
            BookingStatus.PENDING_PAYMENT.value,
            BookingStatus.PAID.value,
            BookingStatus.CANCELLED.value,
        },
        BookingStatus.PENDING_PAYMENT.value: {
            BookingStatus.PAID.value,
            BookingStatus.CANCELLED.value,
            BookingStatus.EXPIRED.value,
        },
        BookingStatus.PAID.value: {
            BookingStatus.USED.value,
            BookingStatus.CANCELLED.value,  # возврат
        },
        BookingStatus.USED.value: set(),
        BookingStatus.CANCELLED.value: set(),
        BookingStatus.EXPIRED.value: set(),
    },
    'ticket': {
        TicketStatus.ACTIVE.value: {
            TicketStatus.USED.value,
            TicketStatus.REFUNDED.value,
            TicketStatus.CANCELLED.value,
        },
        TicketStatus.USED.value: set(),
        TicketStatus.REFUNDED.value: set(),
        TicketStatus.CANCELLED.value: set(),
    },
    'payment': {
        PaymentStatus.PENDING.value: {
            PaymentStatus.COMPLETED.value,
            PaymentStatus.FAILED.value,
            PaymentStatus.REFUNDED.value,
        },
        PaymentStatus.COMPLETED.value: {PaymentStatus.REFUNDED.value},
        PaymentStatus.FAILED.value: set(),
        PaymentStatus.REFUNDED.value: set(),
    },
}


class StatusTransitionMixin:
    """Проверка допустимых переходов статуса по таблице STATUS_TRANSITIONS."""

    status_kind = None

    def get_allowed_transitions(self):
        return STATUS_TRANSITIONS.get(self.status_kind, {}).get(self.status, set())

    def can_set_status(self, new_status):
        return new_status in self.get_allowed_transitions()

    def check_status_transition(self, new_status):
        if not self.can_set_status(new_status):
            raise ValidationError(
                f'Недопустимый переход статуса ({self.status_kind}): '
                f'{self.status} → {new_status}'
            )
        return new_status

    def set_status(self, new_status, update_fields=('status',)):
        self.check_status_transition(new_status)
        self.status = new_status
        if self.pk:
            self.save(update_fields=list(update_fields))
        return self


class User(AbstractUser):
    ROLE_CHOICES = [
        ('client', 'Клиент'),
        ('cashier', 'Кассир'),
        ('controller', 'Контролёр'),
        ('manager', 'Менеджер'),
        ('admin', 'Администратор'),
    ]
    
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='client', verbose_name='Роль')
    phone = models.CharField(max_length=20, blank=True, verbose_name='Телефон')
    
    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'
        ordering = ['username']
    
    def __str__(self):
        return f'{self.username} ({self.get_role_display()})'
    
    def is_client(self):
        return self.role == 'client'
    
    def is_cashier(self):
        return self.role == 'cashier'
    
    def is_controller(self):
        return self.role == 'controller'
    
    def is_manager(self):
        return self.role in ['manager', 'admin']
    
    def is_admin(self):
        return self.role == 'admin'


class Genre(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name='Название')
    description = models.TextField(blank=True, verbose_name='Описание')
    
    class Meta:
        verbose_name = 'Жанр'
        verbose_name_plural = 'Жанры'
        ordering = ['name']
    
    def __str__(self):
        return self.name


class Movie(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Черновик'),
        ('active', 'В прокате'),
        ('ended', 'Прокат завершён'),
        ('upcoming', 'Ожидается'),
    ]
    
    title = models.CharField(max_length=255, verbose_name='Название')
    genre = models.ForeignKey(Genre, on_delete=models.PROTECT, related_name='movies', verbose_name='Жанр')
    duration = models.PositiveIntegerField(validators=[MinValueValidator(1)], verbose_name='Длительность (мин)')
    age_rating = models.PositiveIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(21)],
        verbose_name='Возрастное ограничение'
    )
    description = models.TextField(blank=True, verbose_name='Описание')
    poster = models.ImageField(upload_to='posters/', blank=True, null=True, verbose_name='Постер')
    trailer_url = models.URLField(
        max_length=300, blank=True,
        verbose_name='Ссылка на трейлер (YouTube)',
        help_text='Например: https://www.youtube.com/watch?v=…'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name='Статус проката')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Фильм'
        verbose_name_plural = 'Фильмы'
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                check=models.Q(duration__gte=1),
                name='movie_duration_positive',
            ),
            models.CheckConstraint(
                check=models.Q(age_rating__gte=0) & models.Q(age_rating__lte=21),
                name='movie_age_rating_range',
            ),
        ]
    
    def __str__(self):
        return self.title


class Hall(models.Model):
    TYPE_CHOICES = [
        ('2D', '2D'),
        ('3D', '3D'),
        ('VIP', 'VIP'),
        ('IMAX', 'IMAX'),
    ]
    
    number = models.PositiveIntegerField(unique=True, verbose_name='Номер зала')
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='2D', verbose_name='Тип зала')
    capacity = models.PositiveIntegerField(validators=[MinValueValidator(1)], verbose_name='Вместимость')
    description = models.TextField(blank=True, verbose_name='Описание')
    
    class Meta:
        verbose_name = 'Зал'
        verbose_name_plural = 'Залы'
        ordering = ['number']
        constraints = [
            models.CheckConstraint(
                check=models.Q(capacity__gte=1),
                name='hall_capacity_positive',
            ),
        ]
    
    def __str__(self):
        return f'Зал {self.number} ({self.get_type_display()})'
    
    def generate_seats(self):
        """Автогенерация мест для зала"""
        rows = 10
        seats_per_row = self.capacity // rows
        categories = ['standard'] * (rows * seats_per_row // 2) + ['comfort'] * (rows * seats_per_row // 3) + ['vip'] * (rows * seats_per_row // 6)
        
        Seat.objects.filter(hall=self).delete()
        
        seat_list = []
        cat_idx = 0
        for row in range(1, rows + 1):
            for seat_num in range(1, seats_per_row + 1):
                category = categories[cat_idx % len(categories)] if categories else 'standard'
                cat_idx += 1
                seat_list.append(Seat(
                    hall=self,
                    row=row,
                    number=seat_num,
                    category=category
                ))
        Seat.objects.bulk_create(seat_list)


class Seat(models.Model):
    CATEGORY_CHOICES = [
        ('standard', 'Стандарт'),
        ('comfort', 'Комфорт'),
        ('vip', 'VIP'),
    ]
    
    hall = models.ForeignKey(Hall, on_delete=models.CASCADE, related_name='seats', verbose_name='Зал')
    row = models.PositiveIntegerField(validators=[MinValueValidator(1)], verbose_name='Ряд')
    number = models.PositiveIntegerField(validators=[MinValueValidator(1)], verbose_name='Номер места')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='standard', verbose_name='Категория')
    
    class Meta:
        verbose_name = 'Место'
        verbose_name_plural = 'Места'
        ordering = ['row', 'number']
        constraints = [
            models.UniqueConstraint(fields=['hall', 'row', 'number'], name='unique_seat_in_hall')
        ]
    
    def __str__(self):
        return f'{self.hall} - Ряд {self.row}, Место {self.number} ({self.get_category_display()})'


class Session(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='sessions', verbose_name='Фильм')
    hall = models.ForeignKey(Hall, on_delete=models.CASCADE, related_name='sessions', verbose_name='Зал')
    date = models.DateField(verbose_name='Дата')
    time = models.TimeField(verbose_name='Время')
    duration_min = models.PositiveIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1)],
        verbose_name='Длительность сеанса (мин)',
        help_text='Снимок длительности фильма на момент создания сеанса'
    )
    price_standard = models.DecimalField(max_digits=8, decimal_places=2, default=300, verbose_name='Цена (Стандарт)')
    price_comfort = models.DecimalField(max_digits=8, decimal_places=2, default=450, verbose_name='Цена (Комфорт)')
    price_vip = models.DecimalField(max_digits=8, decimal_places=2, default=700, verbose_name='Цена (VIP)')
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Сеанс'
        verbose_name_plural = 'Сеансы'
        ordering = ['date', 'time']
        indexes = [
            models.Index(fields=['date', 'time'], name='idx_session_date_time'),
            models.Index(fields=['is_active', 'date'], name='idx_session_active_date'),
            models.Index(fields=['movie', 'date'], name='idx_session_movie_date'),
        ]
        constraints = [
            models.UniqueConstraint(fields=['hall', 'date', 'time'], name='unique_session_in_hall'),
            models.CheckConstraint(
                check=models.Q(price_standard__gte=0)
                & models.Q(price_comfort__gte=0)
                & models.Q(price_vip__gte=0),
                name='session_prices_nonnegative',
            ),
            models.CheckConstraint(
                check=models.Q(duration_min__gte=1),
                name='session_end_after_start',
            ),
        ]
    
    def __str__(self):
        return f'{self.movie} - {self.date} {self.time} ({self.hall})'
    
    def get_duration_min(self):
        return self.duration_min or (self.movie.duration if self.movie_id else 0)
    
    def clean(self):
        from django.conf import settings
        if self.date and self.time:
            from datetime import datetime, timedelta
            buffer = getattr(settings, 'SESSION_BUFFER_MINUTES', 20)
            duration = self.get_duration_min()
            session_start = datetime.combine(self.date, self.time)
            session_end = session_start + timedelta(minutes=duration + buffer)

            overlapping = Session.objects.filter(
                hall=self.hall,
                date=self.date,
                is_active=True
            ).exclude(pk=self.pk)

            for other in overlapping:
                other_start = datetime.combine(other.date, other.time)
                other_end = other_start + timedelta(minutes=other.get_duration_min() + buffer)

                # Конец одного сеанса может совпадать с началом следующего
                if session_start < other_end and session_end > other_start:
                    raise ValidationError('Сеансы в этом зале пересекаются по времени')
    
    def save(self, *args, **kwargs):
        if self.duration_min is None and self.movie_id:
            self.duration_min = self.movie.duration
        self.clean()
        super().save(*args, **kwargs)
    
    def get_price_for_category(self, category):
        prices = {
            'standard': self.price_standard,
            'comfort': self.price_comfort,
            'vip': self.price_vip,
        }
        return prices.get(category, self.price_standard)
    
    def get_available_seats(self):
        booked_seat_ids = Booking.objects.filter(
            session=self,
            status__in=[
                BookingStatus.CREATED, BookingStatus.PENDING_PAYMENT,
                BookingStatus.PAID, BookingStatus.USED,
            ]
        ).values_list('seat_id', flat=True)
        return self.hall.seats.exclude(id__in=booked_seat_ids)


class Booking(StatusTransitionMixin, models.Model):
    STATUS_CHOICES = BookingStatus.choices
    status_kind = 'booking'
    
    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookings', verbose_name='Клиент')
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='bookings', verbose_name='Сеанс')
    seat = models.ForeignKey(Seat, on_delete=models.CASCADE, related_name='bookings', verbose_name='Место')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=BookingStatus.CREATED, verbose_name='Статус')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name='Истекает')
    
    class Meta:
        verbose_name = 'Бронирование'
        verbose_name_plural = 'Бронирования'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at'], name='idx_booking_status_created'),
            models.Index(fields=['expires_at'], name='idx_booking_expires_at'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['session', 'seat'],
                condition=models.Q(status__in=['created', 'pending_payment', 'paid', 'used']),
                name='unique_active_booking_per_seat'
            )
        ]
    
    def __str__(self):
        return f'Бронь #{self.id} - {self.session} - {self.seat} ({self.get_status_display()})'
    
    def is_expired(self):
        if self.expires_at and timezone.now() > self.expires_at:
            return True
        return False
    
    def expire(self):
        if self.status in [BookingStatus.CREATED, BookingStatus.PENDING_PAYMENT]:
            self.set_status(BookingStatus.EXPIRED)


class Ticket(StatusTransitionMixin, models.Model):
    STATUS_CHOICES = TicketStatus.choices
    status_kind = 'ticket'
    
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='ticket', verbose_name='Бронирование')
    price = models.DecimalField(max_digits=8, decimal_places=2, verbose_name='Цена')
    barcode = models.CharField(max_length=64, unique=True, verbose_name='Штрихкод')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=TicketStatus.ACTIVE, verbose_name='Статус')
    issued_at = models.DateTimeField(auto_now_add=True, verbose_name='Выдан')
    used_at = models.DateTimeField(null=True, blank=True, verbose_name='Использован')
    
    class Meta:
        verbose_name = 'Билет'
        verbose_name_plural = 'Билеты'
        ordering = ['-issued_at']
        indexes = [
            models.Index(fields=['status', 'issued_at'], name='idx_ticket_status_issued'),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(price__gte=0),
                name='ticket_price_nonnegative',
            ),
        ]
    
    def __str__(self):
        return f'Билет #{self.barcode} ({self.get_status_display()})'
    
    def mark_used(self):
        self.used_at = timezone.now()
        self.set_status(TicketStatus.USED, update_fields=('status', 'used_at'))
        if self.booking.can_set_status(BookingStatus.USED):
            self.booking.set_status(BookingStatus.USED)


class Payment(StatusTransitionMixin, models.Model):
    METHOD_CHOICES = [
        ('cash', 'Наличные'),
        ('card', 'Карта'),
        ('online', 'Онлайн'),
    ]
    
    STATUS_CHOICES = PaymentStatus.choices
    status_kind = 'payment'
    
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='payments', verbose_name='Билет')
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Сумма')
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, verbose_name='Способ оплаты')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PaymentStatus.PENDING, verbose_name='Статус')
    transaction_id = models.CharField(max_length=100, blank=True, verbose_name='ID транзакции')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='Завершён')
    
    class Meta:
        verbose_name = 'Платёж'
        verbose_name_plural = 'Платежи'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at'], name='idx_payment_status_created'),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gte=0),
                name='payment_amount_nonnegative',
            ),
        ]
    
    def __str__(self):
        return f'Платёж #{self.id} - {self.amount} руб. ({self.get_status_display()})'


class AuditLog(models.Model):
    """Журнал аудита ключевых операций (ТЗ): кто, что, когда"""
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='audit_logs', verbose_name='Пользователь'
    )
    action = models.CharField(max_length=100, verbose_name='Действие')
    details = models.TextField(blank=True, verbose_name='Детали')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')

    class Meta:
        verbose_name = 'Запись аудита'
        verbose_name_plural = 'Журнал аудита'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at'], name='idx_audit_created_desc'),
            models.Index(fields=['action', '-created_at'], name='idx_audit_action_created'),
        ]

    def __str__(self):
        user = self.user.username if self.user else '—'
        return f'[{self.created_at:%d.%m.%Y %H:%M}] {user}: {self.action}'


def log_audit(user, action, details=''):
    """Пишет запись в журнал аудита. user — анонимный/неаутентифицированный → None"""
    if user is not None and not getattr(user, 'is_authenticated', False):
        user = None
    try:
        AuditLog.objects.create(user=user, action=action, details=details)
    except Exception:
        # Журнал аудита не должен ронять основную операцию
        pass


class Favorite(models.Model):
    """Избранные фильмы пользователя"""
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='favorites',
        verbose_name='Пользователь'
    )
    movie = models.ForeignKey(
        Movie, on_delete=models.CASCADE, related_name='favorited_by',
        verbose_name='Фильм'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Добавлено')

    class Meta:
        verbose_name = 'Избранное'
        verbose_name_plural = 'Избранное'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['user', 'movie'], name='unique_favorite'),
        ]

    def __str__(self):
        return f'{self.user} → {self.movie}'


class Review(models.Model):
    """Отзыв и оценка фильма (1–5), одна на пользователя"""
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='reviews',
        verbose_name='Пользователь'
    )
    movie = models.ForeignKey(
        Movie, on_delete=models.CASCADE, related_name='reviews',
        verbose_name='Фильм'
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name='Оценка'
    )
    comment = models.TextField(blank=True, verbose_name='Комментарий')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')

    class Meta:
        verbose_name = 'Отзыв'
        verbose_name_plural = 'Отзывы'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['user', 'movie'], name='unique_review_per_user'),
            models.CheckConstraint(
                check=models.Q(rating__gte=1) & models.Q(rating__lte=5),
                name='review_rating_range',
            ),
        ]

    def __str__(self):
        return f'{self.movie}: {self.user} — {self.rating}/5'