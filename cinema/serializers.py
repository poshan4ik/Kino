from rest_framework import serializers
from .models import User, Genre, Movie, Hall, Seat, Session, Booking, Ticket, Payment
import uuid


class UserSerializer(serializers.ModelSerializer):
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
    
    def get_movies_count(self, obj):
        return obj.movies.count()


class MovieSerializer(serializers.ModelSerializer):
    genre_name = serializers.CharField(source='genre.name', read_only=True)
    sessions_count = serializers.SerializerMethodField()
    poster_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Movie
        fields = ['id', 'title', 'genre', 'genre_name', 'duration', 'age_rating', 'description', 'poster', 'poster_url', 'status', 'sessions_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_sessions_count(self, obj):
        return obj.sessions.filter(is_active=True).count()
    
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
    
    class Meta:
        model = Movie
        fields = ['id', 'title', 'genre_name', 'duration', 'age_rating', 'poster_url', 'status', 'next_sessions']
    
    def get_poster_url(self, obj):
        if obj.poster:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.poster.url)
        return None
    
    def get_next_sessions(self, obj):
        from django.utils import timezone
        now = timezone.now()
        sessions = obj.sessions.filter(date__gte=now.date(), is_active=True).order_by('date', 'time')[:5]
        return SessionListSerializer(sessions, many=True, context=self.context).data


class HallSerializer(serializers.ModelSerializer):
    seats_count = serializers.SerializerMethodField()
    sessions_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Hall
        fields = ['id', 'number', 'type', 'capacity', 'description', 'seats_count', 'sessions_count']
        read_only_fields = ['id']
    
    def get_seats_count(self, obj):
        return obj.seats.count()
    
    def get_sessions_count(self, obj):
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
    
    def get_available_seats_count(self, obj):
        return obj.get_available_seats().count()
    
    def get_seats_layout(self, obj):
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
    ticket = serializers.SerializerMethodField()
    
    class Meta:
        model = Booking
        fields = ['id', 'client', 'client_name', 'client_username', 'session', 'session_info', 'seat', 'seat_info', 'status', 'created_at', 'expires_at', 'ticket']
        read_only_fields = ['id', 'client', 'created_at', 'expires_at']
    
    def get_ticket(self, obj):
        if hasattr(obj, 'ticket'):
            return TicketSerializer(obj.ticket, context=self.context).data
        return None


class BookingCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = ['session', 'seat']
    
    def validate(self, attrs):
        session = attrs['session']
        seat = attrs['seat']
        
        if seat.hall != session.hall:
            raise serializers.ValidationError('Место не принадлежит залу этого сеанса')
        
        if not session.is_active:
            raise serializers.ValidationError('Сеанс неактивен')
        
        existing = Booking.objects.filter(
            session=session,
            seat=seat,
            status__in=['created', 'pending_payment', 'paid', 'used']
        ).exists()
        
        if existing:
            raise serializers.ValidationError('Это место уже забронировано')
        
        return attrs
    
    def create(self, validated_data):
        validated_data['client'] = self.context['request'].user
        validated_data['status'] = 'pending_payment'
        from django.utils import timezone
        from datetime import timedelta
        validated_data['expires_at'] = timezone.now() + timedelta(minutes=15)
        return super().create(validated_data)


class TicketSerializer(serializers.ModelSerializer):
    booking_info = BookingSerializer(source='booking', read_only=True)
    
    class Meta:
        model = Ticket
        fields = ['id', 'booking', 'booking_info', 'price', 'barcode', 'status', 'issued_at', 'used_at']
        read_only_fields = ['id', 'barcode', 'issued_at', 'used_at']


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ['id', 'ticket', 'amount', 'method', 'status', 'transaction_id', 'created_at', 'completed_at']
        read_only_fields = ['id', 'created_at', 'completed_at']


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
        payment = super().create(validated_data)
        payment.complete()
        return payment


class DashboardStatsSerializer(serializers.Serializer):
    sessions_today = serializers.IntegerField()
    tickets_sold = serializers.IntegerField()
    revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    occupancy_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    movies_active = serializers.IntegerField()
    halls_total = serializers.IntegerField()