from django.conf import settings
from django.db.models import Avg
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from .models import User, Genre, Movie, Hall, Seat, Session, Booking, Ticket, Payment, Favorite, Review, TicketType
import uuid


class UserSerializer(serializers.ModelSerializer):
    """Публичный/личный профиль: роль — только чтение (защита от эскалирования)."""

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'role', 'phone', 'is_active', 'date_joined']
        read_only_fields = ['id', 'date_joined', 'role', 'is_active']


class UserAdminSerializer(serializers.ModelSerializer):
    """CRUD пользователей менеджером/админом (роль редактируема)."""

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'role', 'phone', 'is_active', 'date_joined']
        read_only_fields = ['id', 'date_joined']


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password', 'first_name', 'last_name', 'role', 'phone']
    
    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User.objects.create_user(**validated_data)
        user.set_password(password)
        user.save()
        return user


class GenreSerializer(serializers.ModelSerializer):
    movies_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Genre
        fields = ['id', 'name', 'description', 'movies_count']
    
    @extend_schema_field(OpenApiTypes.INT)
    def get_movies_count(self, obj) -> int:
        return obj.movies.count()


class MovieSerializer(serializers.ModelSerializer):
    genre_name = serializers.CharField(source='genre.name', read_only=True)
    sessions_count = serializers.SerializerMethodField()
    poster_url = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    reviews_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Movie
        fields = ['id', 'title', 'genre', 'genre_name', 'duration', 'age_rating', 'description', 'poster', 'poster_url', 'trailer_url', 'status', 'sessions_count', 'rating', 'reviews_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    @extend_schema_field(OpenApiTypes.INT)
    def get_sessions_count(self, obj) -> int:
        return obj.sessions.filter(is_active=True).count()

    @extend_schema_field(OpenApiTypes.DOUBLE)
    def get_rating(self, obj):
        from .models import Review
        rating = getattr(obj, 'average_rating', None)
        if rating is None:
            rating = Review.objects.filter(movie=obj).aggregate(
                avg=Avg('rating')
            )['avg']
        return round(float(rating), 1) if rating is not None else None

    @extend_schema_field(OpenApiTypes.INT)
    def get_reviews_count(self, obj) -> int:
        from .models import Review
        count = getattr(obj, 'reviews_count', None)
        if count is None:
            count = Review.objects.filter(movie=obj).count()
        return count

    @extend_schema_field(OpenApiTypes.URI)
    def get_poster_url(self, obj):
        if obj.poster:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.poster.url)
        return None


class MovieListSerializer(serializers.ModelSerializer):
    genre_name = serializers.CharField(source='genre.name', read_only=True)
    poster_url = serializers.SerializerMethodField()
    next_sessions = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    reviews_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Movie
        fields = ['id', 'title', 'genre_name', 'duration', 'age_rating', 'poster_url', 'trailer_url', 'status', 'rating', 'reviews_count', 'next_sessions']
    
    @extend_schema_field(OpenApiTypes.URI)
    def get_poster_url(self, obj):
        if obj.poster:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.poster.url)
        return None

    @extend_schema_field(OpenApiTypes.DOUBLE)
    def get_rating(self, obj):
        from .models import Review
        rating = getattr(obj, 'average_rating', None)
        if rating is None:
            rating = Review.objects.filter(movie=obj).aggregate(
                avg=Avg('rating')
            )['avg']
        return round(float(rating), 1) if rating is not None else None

    @extend_schema_field(OpenApiTypes.INT)
    def get_reviews_count(self, obj) -> int:
        from .models import Review
        count = getattr(obj, 'reviews_count', None)
        if count is None:
            count = Review.objects.filter(movie=obj).count()
        return count
    
    @extend_schema_field({'type': 'array', 'items': {'type': 'object'}})
    def get_next_sessions(self, obj) -> list:
        # На list сеансы уже prefetch'нуты (select_related hall/movie) — без N+1
        sessions = obj.sessions.all()[:5]
        return SessionListSerializer(sessions, many=True, context=self.context).data


class HallSerializer(serializers.ModelSerializer):
    seats_count = serializers.SerializerMethodField()
    sessions_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Hall
        fields = ['id', 'number', 'type', 'capacity', 'description', 'seats_count', 'sessions_count']
        read_only_fields = ['id']
    
    @extend_schema_field(OpenApiTypes.INT)
    def get_seats_count(self, obj) -> int:
        return obj.seats.count()
    
    @extend_schema_field(OpenApiTypes.INT)
    def get_sessions_count(self, obj) -> int:
        return obj.sessions.filter(is_active=True).count()


class SeatSerializer(serializers.ModelSerializer):
    class Meta:
        model = Seat
        fields = ['id', 'hall', 'row', 'number', 'category']
        read_only_fields = ['id']


class SessionSerializer(serializers.ModelSerializer):
    movie_title = serializers.CharField(source='movie.title', read_only=True)
    movie_duration = serializers.IntegerField(source='movie.duration', read_only=True)
    movie_age_rating = serializers.IntegerField(source='movie.age_rating', read_only=True)
    hall_number = serializers.IntegerField(source='hall.number', read_only=True)
    hall_type = serializers.CharField(source='hall.type', read_only=True)
    available_seats_count = serializers.SerializerMethodField()
    seats_layout = serializers.SerializerMethodField()
    
    class Meta:
        model = Session
        fields = ['id', 'movie', 'movie_title', 'movie_duration', 'movie_age_rating', 'hall', 'hall_number', 'hall_type', 'date', 'time', 'price_standard', 'price_comfort', 'price_vip', 'is_active', 'available_seats_count', 'seats_layout', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    @extend_schema_field(OpenApiTypes.INT)
    def get_available_seats_count(self, obj) -> int:
        return obj.get_available_seats().count()
    
    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_seats_layout(self, obj) -> dict:
        seats = obj.hall.seats.all().order_by('row', 'number')
        booked_seat_ids = set(obj.bookings.filter(
            status__in=['created', 'pending_payment', 'paid', 'used']
        ).values_list('seat_id', flat=True))
        
        layout = {}
        for seat in seats:
            row_key = f'row_{seat.row}'
            if row_key not in layout:
                layout[row_key] = []
            layout[row_key].append({
                'id': seat.id,
                'number': seat.number,
                'category': seat.category,
                'is_booked': seat.id in booked_seat_ids,
            })
        return layout


class SessionListSerializer(serializers.ModelSerializer):
    movie_title = serializers.CharField(source='movie.title', read_only=True)
    hall_number = serializers.IntegerField(source='hall.number', read_only=True)
    hall_type = serializers.CharField(source='hall.type', read_only=True)
    
    class Meta:
        model = Session
        fields = ['id', 'movie_title', 'hall_number', 'hall_type', 'date', 'time', 'price_standard', 'price_comfort', 'price_vip']


class BookingSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.get_full_name', read_only=True)
    client_username = serializers.CharField(source='client.username', read_only=True)
    session_info = SessionListSerializer(source='session', read_only=True)
    seat_info = SeatSerializer(source='seat', read_only=True)
    ticket_type_name = serializers.CharField(
        source='ticket_type.name', read_only=True, default=None
    )
    ticket = serializers.SerializerMethodField()
    
    class Meta:
        model = Booking
        fields = ['id', 'client', 'client_name', 'client_username', 'session', 'session_info', 'seat', 'seat_info', 'ticket_type', 'ticket_type_name', 'status', 'created_at', 'expires_at', 'ticket']
        read_only_fields = ['id', 'client', 'session', 'seat', 'status', 'created_at', 'expires_at']
    
    @extend_schema_field({'type': 'object', 'nullable': True})
    def get_ticket(self, obj):
        if hasattr(obj, 'ticket'):
            return TicketSerializer(obj.ticket, context=self.context).data
        return None


class BookingCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = ['session', 'seat']
        validators = []

    def validate(self, attrs):
        from . import services
        session = attrs['session']
        seat = attrs['seat']

        if seat.hall != session.hall:
            raise serializers.ValidationError('Место не принадлежит залу этого сеанса')

        try:
            services.validate_session_bookable(session)
        except services.BookingError as exc:
            raise serializers.ValidationError(exc.message)

        existing = Booking.objects.filter(
            session=session,
            seat=seat,
            status__in=services.ACTIVE_BOOKING_STATUSES
        ).exists()

        if existing:
            raise serializers.ValidationError('Это место уже забронировано')

        return attrs

    def create(self, validated_data):
        # «Всё или ничего» через общий сервис (лимит/блокировки/истечение)
        from . import services
        user = self.context['request'].user
        session = validated_data['session']
        seat = validated_data['seat']
        try:
            bookings, _ = services.create_booking(user, session, [seat.id])
        except services.BookingError as exc:
            raise serializers.ValidationError(exc.message)
        return bookings[0]


class TicketSerializer(serializers.ModelSerializer):
    booking_info = serializers.SerializerMethodField()

    class Meta:
        model = Ticket
        fields = ['id', 'booking', 'booking_info', 'price', 'barcode', 'status', 'issued_at', 'used_at']
        read_only_fields = ['id', 'booking', 'price', 'barcode', 'status', 'issued_at', 'used_at']

    @extend_schema_field({'type': 'object', 'nullable': True})
    def get_booking_info(self, obj):
        if self.context.get('nested'):
            return None
        return BookingSerializer(obj.booking, context={**self.context, 'nested': True}).data


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ['id', 'ticket', 'amount', 'method', 'status', 'transaction_id', 'created_at', 'completed_at']
        read_only_fields = ['id', 'ticket', 'amount', 'status', 'created_at', 'completed_at']


class PaymentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ['ticket', 'amount', 'method', 'transaction_id']
    
    def validate(self, attrs):
        ticket = attrs['ticket']
        if ticket.status != 'active':
            raise serializers.ValidationError('Билет неактивен')
        if ticket.booking.status not in ['pending_payment', 'created']:
            raise serializers.ValidationError('Бронирование не ожидает оплаты')
        if attrs['amount'] != ticket.price:
            raise serializers.ValidationError('Сумма не соответствует цене билета')
        return attrs
    
    def create(self, validated_data):
        validated_data['status'] = 'completed'
        from django.utils import timezone
        validated_data['completed_at'] = timezone.now()
        # Статусы Booking/Ticket обновляет сигнал payment_post_save (signals.py) —
        # это единственный источник правды по завершению платежа
        payment = super().create(validated_data)

        from .models import log_audit
        request = self.context.get('request')
        if request is not None:
            log_audit(
                request.user, 'confirm_payment',
                f'Платёж #{payment.id}, билет {payment.ticket.barcode}, '
                f'{payment.amount} руб. ({payment.get_method_display()})'
            )
        return payment


class DashboardStatsSerializer(serializers.Serializer):
    sessions_today = serializers.IntegerField()
    tickets_sold = serializers.IntegerField()
    revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    occupancy_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    movies_active = serializers.IntegerField()
    halls_total = serializers.IntegerField()


class FavoriteSerializer(serializers.ModelSerializer):
    movie_title = serializers.CharField(source='movie.title', read_only=True)

    class Meta:
        model = Favorite
        fields = ['id', 'movie', 'movie_title', 'created_at']
        read_only_fields = ['id', 'created_at']


class ReviewSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = Review
        fields = ['id', 'user', 'username', 'movie', 'rating', 'comment', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']


class MovieReviewsSummarySerializer(serializers.Serializer):
    """Сводка отзывов фильма: рейтинг, количество, список."""
    rating = serializers.FloatField(allow_null=True)
    count = serializers.IntegerField()
    reviews = ReviewSerializer(many=True)


class HoldRequestSerializer(serializers.Serializer):
    """Тело POST /api/bookings/hold/."""
    session = serializers.IntegerField()
    seats = serializers.ListField(
        child=serializers.IntegerField(), min_length=1, max_length=10,
        help_text='ID мест (не больше BOOKING_MAX_SEATS)',
    )
    ticket_type = serializers.IntegerField(
        required=False, allow_null=True,
        help_text='ID типа билета (скидка); без него — взрослый',
    )


class PayRequestSerializer(serializers.Serializer):
    """Тело POST /api/bookings/pay/."""
    booking_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        max_length=getattr(settings, 'BOOKING_MAX_SEATS', 10),
    )
    method = serializers.ChoiceField(
        choices=Payment.METHOD_CHOICES, default='online',
    )


class ReviewCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ['movie', 'rating', 'comment']

    def validate(self, attrs):
        # Оставить оценку может только клиент с оплаченным и
        # использованным билетом на этот фильм
        from .models import BookingStatus, TicketStatus
        user = self.context['request'].user
        movie = attrs['movie']
        can_review = Ticket.objects.filter(
            booking__client=user,
            booking__session__movie=movie,
            status=TicketStatus.USED,
        ).exists() or Booking.objects.filter(
            client=user,
            session__movie=movie,
            status=BookingStatus.USED,
        ).exists()
        if not can_review:
            raise serializers.ValidationError(
                'Оценку можно оставить после посещения сеанса '
                '(оплаченный и использованный билет на этот фильм)'
            )
        return attrs

    def create(self, validated_data):
        # Одна оценка на пользователя: повторный отзыв обновляет существующий
        user = self.context['request'].user
        review, _ = Review.objects.update_or_create(
            user=user,
            movie=validated_data['movie'],
            defaults={
                'rating': validated_data['rating'],
                'comment': validated_data.get('comment', ''),
            },
        )
        return review