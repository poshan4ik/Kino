from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Genre, Movie, Hall, Seat, Session, Booking, Ticket, Payment


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'first_name', 'last_name', 'role', 'is_staff', 'is_active']
    list_filter = ['role', 'is_staff', 'is_active', 'is_superuser']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering = ['username']
    
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Дополнительно', {'fields': ('role', 'phone')}),
    )
    
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Дополнительно', {'fields': ('role', 'phone')}),
    )


@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ['name', 'description']
    search_fields = ['name']
    ordering = ['name']


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ['title', 'genre', 'duration', 'age_rating', 'status', 'created_at']
    list_filter = ['genre', 'status', 'age_rating']
    search_fields = ['title', 'description']
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'updated_at']
    list_editable = ['status']


class SeatInline(admin.TabularInline):
    model = Seat
    extra = 0
    readonly_fields = ['hall', 'row', 'number', 'category']
    can_delete = False
    max_num = 0


@admin.register(Hall)
class HallAdmin(admin.ModelAdmin):
    list_display = ['number', 'type', 'capacity']
    list_filter = ['type']
    search_fields = ['number']
    ordering = ['number']
    inlines = [SeatInline]
    
    actions = ['generate_seats_action']
    
    @admin.action(description='Сгенерировать места для выбранных залов')
    def generate_seats_action(self, request, queryset):
        for hall in queryset:
            hall.generate_seats()
        self.message_user(request, f'Места сгенерированы для {queryset.count()} залов')


@admin.register(Seat)
class SeatAdmin(admin.ModelAdmin):
    list_display = ['hall', 'row', 'number', 'category']
    list_filter = ['hall', 'category']
    search_fields = ['hall__number', 'row', 'number']
    ordering = ['hall', 'row', 'number']


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ['movie', 'hall', 'date', 'time', 'is_active']
    list_filter = ['hall', 'date', 'is_active', 'movie__genre']
    search_fields = ['movie__title', 'hall__number']
    ordering = ['-date', 'time']
    list_editable = ['is_active']
    date_hierarchy = 'date'


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ['id', 'client', 'session', 'seat', 'status', 'created_at', 'expires_at']
    list_filter = ['status', 'session__date', 'session__hall']
    search_fields = ['client__username', 'session__movie__title', 'seat__row', 'seat__number']
    ordering = ['-created_at']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'
    list_editable = ['status']


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ['barcode', 'booking', 'price', 'status', 'issued_at', 'used_at']
    list_filter = ['status']
    search_fields = ['barcode', 'booking__client__username', 'booking__session__movie__title']
    ordering = ['-issued_at']
    readonly_fields = ['issued_at', 'barcode']
    date_hierarchy = 'issued_at'


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['id', 'ticket', 'amount', 'method', 'status', 'created_at']
    list_filter = ['method', 'status']
    search_fields = ['ticket__barcode', 'transaction_id']
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'completed_at']
    date_hierarchy = 'created_at'