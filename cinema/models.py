from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


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
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name='Статус проката')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Фильм'
        verbose_name_plural = 'Фильмы'
        ordering = ['-created_at']
    
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
    price_standard = models.DecimalField(max_digits=8, decimal_places=2, default=300, verbose_name='Цена (Стандарт)')
    price_comfort = models.DecimalField(max_digits=8, decimal_places=2, default=450, verbose_name='Цена (Комфорт)')
    price_vip = models.DecimalField(max_digits=8, decimal_places=2, default=700, verbose_name='Цена (VIP)')
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Сеанс'
        verbose_name_plural = 'Сеансы'
        ordering = ['date', 'time']
        constraints = [
            models.UniqueConstraint(fields=['hall', 'date', 'time'], name='unique_session_in_hall')
        ]
    
    def __str__(self):
        return f'{self.movie} - {self.date} {self.time} ({self.hall})'
    
    def clean(self):
        from django.core.exceptions import ValidationError
        if self.date and self.time:
            from datetime import datetime, timedelta
            session_start = datetime.combine(self.date, self.time)
            session_end = session_start + timedelta(minutes=self.movie.duration + 20)
            
            overlapping = Session.objects.filter(
                hall=self.hall,
                date=self.date,
                is_active=True
            ).exclude(pk=self.pk)
            
            for other in overlapping:
                other_start = datetime.combine(other.date, other.time)
                other_end = other_start + timedelta(minutes=other.movie.duration + 20)
                
                if session_start < other_end and session_end > other_start:
                    raise ValidationError('Сеансы в этом зале пересекаются по времени')
    
    def save(self, *args, **kwargs):
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
            status__in=['created', 'pending_payment', 'paid', 'used']
        ).values_list('seat_id', flat=True)
        return self.hall.seats.exclude(id__in=booked_seat_ids)


class Booking(models.Model):
    STATUS_CHOICES = [
        ('created', 'Создано'),
        ('pending_payment', 'Ожидает оплаты'),
        ('paid', 'Оплачено'),
        ('used', 'Использовано'),
        ('cancelled', 'Отменено'),
        ('expired', 'Просрочено'),
    ]
    
    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookings', verbose_name='Клиент')
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='bookings', verbose_name='Сеанс')
    seat = models.ForeignKey(Seat, on_delete=models.CASCADE, related_name='bookings', verbose_name='Место')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='created', verbose_name='Статус')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name='Истекает')
    
    class Meta:
        verbose_name = 'Бронирование'
        verbose_name_plural = 'Бронирования'
        ordering = ['-created_at']
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
        if self.status in ['created', 'pending_payment']:
            self.status = 'expired'
            self.save(update_fields=['status'])


class Ticket(models.Model):
    STATUS_CHOICES = [
        ('active', 'Активен'),
        ('used', 'Использован'),
        ('refunded', 'Возвращён'),
        ('cancelled', 'Аннулирован'),
    ]
    
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='ticket', verbose_name='Бронирование')
    price = models.DecimalField(max_digits=8, decimal_places=2, verbose_name='Цена')
    barcode = models.CharField(max_length=64, unique=True, verbose_name='Штрихкод')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', verbose_name='Статус')
    issued_at = models.DateTimeField(auto_now_add=True, verbose_name='Выдан')
    used_at = models.DateTimeField(null=True, blank=True, verbose_name='Использован')
    
    class Meta:
        verbose_name = 'Билет'
        verbose_name_plural = 'Билеты'
        ordering = ['-issued_at']
    
    def __str__(self):
        return f'Билет #{self.barcode} ({self.get_status_display()})'
    
    def mark_used(self):
        self.status = 'used'
        self.used_at = timezone.now()
        self.save(update_fields=['status', 'used_at'])
        self.booking.status = 'used'
        self.booking.save(update_fields=['status'])


class Payment(models.Model):
    METHOD_CHOICES = [
        ('cash', 'Наличные'),
        ('card', 'Карта'),
        ('online', 'Онлайн'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Ожидает'),
        ('completed', 'Завершён'),
        ('failed', 'Неудача'),
        ('refunded', 'Возвращён'),
    ]
    
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='payments', verbose_name='Билет')
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Сумма')
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, verbose_name='Способ оплаты')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='Статус')
    transaction_id = models.CharField(max_length=100, blank=True, verbose_name='ID транзакции')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='Завершён')
    
    class Meta:
        verbose_name = 'Платёж'
        verbose_name_plural = 'Платежи'
        ordering = ['-created_at']
    
    def __str__(self):
        return f'Платёж #{self.id} - {self.amount} руб. ({self.get_status_display()})'
    
    def complete(self):
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at'])
        self.ticket.booking.status = 'paid'
        self.ticket.booking.save(update_fields=['status'])