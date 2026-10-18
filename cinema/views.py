from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema
from drf_spectacular.types import OpenApiTypes
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Sum, Q, F, Avg
from django.db.models.functions import TruncDate
from django.db import transaction, connection
from django.db.utils import IntegrityError
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json
import uuid
from datetime import timedelta, date
from pathlib import Path

from .models import User, Genre, Movie, Hall, Seat, Session, Booking, Ticket, Payment, PaymentIntent, AuditLog, Favorite, Review, TicketType, log_audit
from . import services
from . import payments
from .serializers import (
    UserSerializer, UserAdminSerializer, UserCreateSerializer, GenreSerializer, MovieSerializer,
    MovieListSerializer, HallSerializer, SeatSerializer, SessionSerializer,
    SessionListSerializer, BookingSerializer, BookingCreateSerializer,
    TicketSerializer, PaymentSerializer, PaymentCreateSerializer,
    DashboardStatsSerializer, FavoriteSerializer, ReviewSerializer,
    ReviewCreateSerializer, MovieReviewsSummarySerializer,
    HoldRequestSerializer, PayRequestSerializer
)
from .permissions import (
    IsAdminOrManager, IsCashierOrAbove, IsCashierRole, IsControllerOrAbove,
    IsOwnerOrStaff
)


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['role', 'is_active']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering_fields = ['username', 'date_joined']

    def get_queryset(self):
        return User.objects.order_by('username')

    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        if self.action in ['me', 'update_me', 'list', 'retrieve']:
            return UserSerializer
        return UserAdminSerializer

    def get_permissions(self):
        # create — только персонал (публичная регистрация через HTML-форму),
        # list/retrieve — только менеджер/админ (защита персональных данных)
        if self.action in ['me', 'update_me']:
            return [IsAuthenticated()]
        return [IsAdminOrManager()]

    def get_throttles(self):
        if self.action == 'create':
            self.throttle_scope = 'auth'
            return [ScopedRateThrottle()]
        return super().get_throttles()

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    @action(detail=False, methods=['patch'], permission_classes=[IsAuthenticated])
    def update_me(self, request):
        serializer = self.get_serializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class GenreViewSet(viewsets.ModelViewSet):
    queryset = Genre.objects.all()
    serializer_class = GenreSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name']
    ordering_fields = ['name']
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAdminOrManager()]


class MovieViewSet(viewsets.ModelViewSet):
    queryset = Movie.objects.select_related('genre').all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['genre', 'status', 'age_rating']
    search_fields = ['title', 'description']
    ordering_fields = ['title', 'created_at', 'duration']

    def get_queryset(self):
        qs = Movie.objects.select_related('genre').annotate(
            average_rating=Avg('reviews__rating'),
            reviews_count=Count('reviews', distinct=True),
        ).order_by('-created_at')
        if self.action == 'list':
            from django.db.models import Prefetch
            qs = qs.prefetch_related(Prefetch(
                'sessions',
                queryset=Session.objects.select_related('hall', 'movie')
                .filter(date__gte=timezone.localdate(), is_active=True)
                .order_by('date', 'time'),
            ))
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return MovieListSerializer
        return MovieSerializer
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'sessions']:
            return [AllowAny()]
        return [IsAdminOrManager()]

    @action(detail=True, methods=['get'], permission_classes=[AllowAny])
    def sessions(self, request, pk=None):
        movie = self.get_object()
        sessions = movie.sessions.filter(
            date__gte=timezone.localdate(), is_active=True
        ).order_by('date', 'time')
        serializer = SessionListSerializer(sessions, many=True, context={'request': request})
        return Response(serializer.data)


class HallViewSet(viewsets.ModelViewSet):
    queryset = Hall.objects.prefetch_related('seats').all()
    serializer_class = HallSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['type']
    search_fields = ['number']
    ordering_fields = ['number', 'capacity']
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAdminOrManager()]
    
    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager])
    def generate_seats(self, request, pk=None):
        hall = self.get_object()
        hall.generate_seats()
        return Response({'detail': f'Места сгенерированы для зала {hall.number}'})


class SeatViewSet(viewsets.ModelViewSet):
    queryset = Seat.objects.select_related('hall').all()
    serializer_class = SeatSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['hall', 'category']
    ordering_fields = ['row', 'number']
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAdminOrManager()]


class SessionViewSet(viewsets.ModelViewSet):
    queryset = Session.objects.select_related('movie', 'hall', 'movie__genre').prefetch_related('hall__seats').all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['movie', 'hall', 'date', 'is_active']
    search_fields = ['movie__title']
    ordering_fields = ['date', 'time', 'created_at']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return SessionListSerializer
        return SessionSerializer
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'by_date', 'seats']:
            return [AllowAny()]
        return [IsAdminOrManager()]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action == 'list':
            date_from = self.request.query_params.get('date_from')
            date_to = self.request.query_params.get('date_to')
            if date_from:
                queryset = queryset.filter(date__gte=date_from)
            if date_to:
                queryset = queryset.filter(date__lte=date_to)
        return queryset
    
    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def by_date(self, request):
        target_date = request.query_params.get('date', timezone.localdate().isoformat())
        sessions = self.get_queryset().filter(date=target_date, is_active=True).order_by('time')
        serializer = self.get_serializer(sessions, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'], permission_classes=[AllowAny])
    def seats(self, request, pk=None):
        session = self.get_object()
        seats = session.hall.seats.all().order_by('row', 'number')
        booked_seat_ids = set(session.bookings.filter(
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
                'price': float(session.get_price_for_category(seat.category)),
                'is_booked': seat.id in booked_seat_ids,
            })
        return Response(layout)


class BookingViewSet(viewsets.ModelViewSet):
    queryset = Booking.objects.select_related('client', 'session', 'session__movie', 'session__hall', 'seat', 'ticket').all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'session', 'client']
    search_fields = ['session__movie__title', 'client__username', 'seat__row']
    ordering_fields = ['created_at', 'status']
    
    def get_serializer_class(self):
        if self.action == 'create':
            return BookingCreateSerializer
        return BookingSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'hold', 'pay', 'cancel_own']:
            return [IsAuthenticated()]
        if self.action in ['list', 'retrieve']:
            return [IsOwnerOrStaff()]
        if self.action in ['confirm_payment', 'cancel', 'refund', 'expire_old']:
            return [IsCashierRole()]
        return [IsCashierOrAbove()]

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and user.role in ['cashier', 'controller', 'manager', 'admin']:
            return super().get_queryset()
        return super().get_queryset().filter(client=user)
    
    def perform_create(self, serializer):
        serializer.save(client=self.request.user)
    
    @action(detail=True, methods=['post'], permission_classes=[IsCashierRole])
    def confirm_payment(self, request, pk=None):
        booking = self.get_object()
        try:
            ticket = services.confirm_payment(
                booking, request.data.get('method', 'cash'), request.user
            )
        except services.BookingError as exc:
            return Response({'error': exc.message}, status=exc.status)
        return Response(TicketSerializer(ticket, context={'request': request}).data)

    @extend_schema(request=HoldRequestSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def hold(self, request):
        """Атомарно удерживает места сеанса («всё или ничего») через services."""
        raw_seats = request.data.get('seats')
        if not isinstance(raw_seats, list) or not raw_seats:
            return Response({'error': 'Не выбрано ни одного места'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            session_obj = Session.objects.get(pk=request.data.get('session'), is_active=True)
        except (Session.DoesNotExist, TypeError, ValueError):
            return Response({'error': 'Сеанс не найден'}, status=status.HTTP_404_NOT_FOUND)

        seat_ids = []
        for value in raw_seats:
            try:
                seat_ids.append(int(value))
            except (TypeError, ValueError):
                return Response({'error': 'Некорректный выбор мест'},
                                status=status.HTTP_400_BAD_REQUEST)

        ticket_type = None
        raw_type = request.data.get('ticket_type')
        if raw_type is not None:
            try:
                ticket_type = TicketType.objects.get(pk=int(raw_type), is_active=True)
            except (TicketType.DoesNotExist, TypeError, ValueError):
                return Response({'error': 'Тип билета не найден'},
                                status=status.HTTP_400_BAD_REQUEST)

        try:
            bookings, expires_at = services.create_booking(
                request.user, session_obj, seat_ids, ticket_type=ticket_type
            )
        except services.BookingError as exc:
            return Response({'error': exc.message}, status=exc.status)

        return Response({
            'session': session_obj.id,
            'expires_at': expires_at.isoformat(),
            'bookings': BookingSerializer(
                bookings, many=True, context={'request': request}
            ).data,
        }, status=status.HTTP_201_CREATED)

    @extend_schema(request=PayRequestSerializer, responses=TicketSerializer(many=True))
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def pay(self, request):
        """Оплата нескольких броней одним запросом.

        Клиент оплачивает только свои брони (card/online),
        персонал — любые брони любым способом.
        """
        raw_ids = request.data.get('booking_ids')
        if not isinstance(raw_ids, list) or not raw_ids:
            return Response({'error': 'Нет броней для оплаты'},
                            status=status.HTTP_400_BAD_REQUEST)
        if len(raw_ids) > 6:
            return Response({'error': 'Слишком много броней'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            booking_ids = [int(i) for i in raw_ids]
        except (TypeError, ValueError):
            return Response({'error': 'Некорректный идентификатор брони'},
                            status=status.HTTP_400_BAD_REQUEST)

        method = request.data.get('method', 'online')
        if method not in dict(Payment.METHOD_CHOICES):
            return Response({'error': 'Недопустимый способ оплаты'},
                            status=status.HTTP_400_BAD_REQUEST)
        user = request.user
        is_staff = user.role in ['cashier', 'controller', 'manager', 'admin']
        if not is_staff and method not in ['card', 'online']:
            return Response({'error': 'Наличными оплачивает только кассир'},
                            status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            bookings_qs = Booking.objects.select_related(
                'session', 'seat'
            ).filter(id__in=booking_ids)
            if connection.features.has_select_for_update:
                bookings_qs = bookings_qs.select_for_update()
            bookings = list(bookings_qs)

            if len(bookings) != len(set(booking_ids)):
                return Response({'error': 'Бронирование не найдено'},
                                status=status.HTTP_404_NOT_FOUND)

            for booking in bookings:
                if booking.client_id != user.id and not is_staff:
                    return Response({'error': 'Нет доступа к бронированию'},
                                    status=status.HTTP_403_FORBIDDEN)

            try:
                tickets = [
                    services.confirm_payment(booking, method, user)
                    for booking in bookings
                ]
            except services.BookingError as exc:
                return Response({'error': exc.message}, status=exc.status)

        return Response(
            TicketSerializer(tickets, many=True, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )
    
    @action(detail=True, methods=['post'], permission_classes=[IsCashierRole])
    def cancel(self, request, pk=None):
        booking = self.get_object()
        try:
            booking = services.cancel_booking(booking, request.user, force=True)
        except services.BookingError as exc:
            return Response({'error': exc.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(BookingSerializer(booking, context={'request': request}).data)

    @action(detail=True, methods=['post'], permission_classes=[IsCashierRole])
    def refund(self, request, pk=None):
        """Возврат: билет → refunded, платежи → refunded, бронь → cancelled."""
        booking = self.get_object()
        try:
            booking = services.refund_ticket(booking, request.user)
        except services.BookingError as exc:
            return Response({'error': exc.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(BookingSerializer(booking, context={'request': request}).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def cancel_own(self, request, pk=None):
        """Клиент отменяет свою непогашенную бронь до начала сеанса."""
        booking = self.get_object()
        if booking.client_id != request.user.id:
            return Response({'error': 'Нет доступа к бронированию'},
                            status=status.HTTP_403_FORBIDDEN)
        try:
            booking = services.cancel_booking(booking, request.user, force=False)
        except services.BookingError as exc:
            return Response({'error': exc.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(BookingSerializer(booking, context={'request': request}).data)
    
    @action(detail=False, methods=['post'], permission_classes=[IsCashierRole])
    def expire_old(self, request):
        return Response({'expired_count': services.expire_old_bookings()})


class TicketViewSet(viewsets.ModelViewSet):
    queryset = Ticket.objects.select_related('booking', 'booking__client', 'booking__session', 'booking__session__movie', 'booking__session__hall', 'booking__seat').all()
    serializer_class = TicketSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status']
    search_fields = ['barcode', 'booking__client__username']
    ordering_fields = ['issued_at', 'status']
    lookup_field = 'barcode'
    
    def get_permissions(self):
        if self.action in ['validate_ticket']:
            return [IsControllerOrAbove()]
        if self.action in ['list', 'retrieve']:
            return [IsOwnerOrStaff()]
        return [IsCashierOrAbove()]
    
    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and user.role in ['cashier', 'controller', 'manager', 'admin']:
            return super().get_queryset()
        return super().get_queryset().filter(booking__client=user)
    
    @action(detail=True, methods=['post'], permission_classes=[IsControllerOrAbove])
    def validate_ticket(self, request, barcode=None):
        ticket = self.get_object()
        try:
            ticket, message = services.check_ticket(ticket, actor=request.user)
        except services.BookingError as exc:
            return Response({
                'valid': False,
                'message': exc.message,
                'ticket': TicketSerializer(ticket, context={'request': request}).data
            }, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'valid': True,
            'message': message,
            'ticket': TicketSerializer(ticket, context={'request': request}).data
        })
    
    @action(detail=False, methods=['post'], permission_classes=[IsControllerOrAbove])
    def check_by_barcode(self, request):
        barcode = request.data.get('barcode')
        if not barcode:
            return Response({'error': 'Штрихкод не указан'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            ticket = Ticket.objects.select_related(
                'booking', 'booking__client', 'booking__session', 'booking__session__movie',
                'booking__session__hall', 'booking__seat'
            ).get(barcode=barcode)
        except Ticket.DoesNotExist:
            return Response({
                'valid': False,
                'message': 'Билет не найден'
            }, status=status.HTTP_404_NOT_FOUND)
        
        try:
            ticket, message = services.check_ticket(ticket, actor=request.user)
        except services.BookingError as exc:
            return Response({
                'valid': False,
                'message': exc.message,
                'ticket': TicketSerializer(ticket, context={'request': request}).data
            }, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'valid': True,
            'message': message,
            'ticket': TicketSerializer(ticket, context={'request': request}).data
        })


class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.select_related('ticket', 'ticket__booking', 'ticket__booking__client').all()
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['method', 'status', 'ticket']
    ordering_fields = ['created_at', 'amount']
    
    def get_serializer_class(self):
        if self.action == 'create':
            return PaymentCreateSerializer
        return PaymentSerializer
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsOwnerOrStaff()]
        return [IsCashierOrAbove()]
    
    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and user.role in ['cashier', 'controller', 'manager', 'admin']:
            return super().get_queryset()
        return super().get_queryset().filter(ticket__booking__client=user)


class DashboardViewSet(viewsets.ViewSet):
    permission_classes = [IsAdminOrManager]
    
    @extend_schema(responses=DashboardStatsSerializer)
    @action(detail=False, methods=['get'])
    def stats(self, request):
        today = timezone.localdate()
        week_start = today - timedelta(days=6)

        sessions_today = Session.objects.filter(date=today, is_active=True).count()

        tickets_sold = Ticket.objects.filter(
            status__in=['active', 'used'],
            issued_at__date=today
        ).count()

        revenue = Payment.objects.filter(
            status='completed',
            completed_at__date=today
        ).aggregate(total=Sum('amount'))['total'] or 0

        total_seats_today = Session.objects.filter(date=today, is_active=True).aggregate(
            total=Sum('hall__capacity')
        )['total'] or 1

        occupied_seats = Booking.objects.filter(
            session__date=today,
            status__in=['paid', 'used']
        ).count()

        occupancy_rate = (occupied_seats / total_seats_today * 100) if total_seats_today > 0 else 0

        movies_active = Movie.objects.filter(status='active').count()
        halls_total = Hall.objects.count()

        # График продаж за последние 7 дней — двумя агрегатами вместо цикла
        revenue_by_day = {
            row['day']: row['total']
            for row in Payment.objects.filter(
                status='completed',
                completed_at__date__gte=week_start,
                completed_at__date__lte=today,
            ).annotate(day=TruncDate('completed_at')).values('day').annotate(
                total=Sum('amount')
            )
        }
        tickets_by_day = {
            row['day']: row['cnt']
            for row in Ticket.objects.filter(
                status__in=['active', 'used'],
                issued_at__date__gte=week_start,
                issued_at__date__lte=today,
            ).annotate(day=TruncDate('issued_at')).values('day').annotate(
                cnt=Count('id')
            )
        }
        sales_chart = []
        for i in range(7):
            day = week_start + timedelta(days=i)
            sales_chart.append({
                'date': day.isoformat(),
                'revenue': float(revenue_by_day.get(day, 0)),
                'tickets': tickets_by_day.get(day, 0),
            })

        # Загрузка залов (места одним запросом)
        seats_by_hall = dict(
            Hall.objects.annotate(seats_total=Count('seats')).values_list('id', 'seats_total')
        )
        hall_load = []
        for hall in Hall.objects.all():
            hall_sessions = Session.objects.filter(hall=hall, date=today, is_active=True)
            session_count = hall_sessions.count()
            total_capacity = session_count * (seats_by_hall.get(hall.id) or hall.capacity)
            booked = Booking.objects.filter(
                session__in=hall_sessions,
                status__in=['paid', 'used']
            ).count()
            load_pct = (booked / total_capacity * 100) if total_capacity > 0 else 0
            hall_load.append({
                'hall': f'Зал {hall.number} ({hall.get_type_display()})',
                'capacity': seats_by_hall.get(hall.id) or hall.capacity,
                'sessions': session_count,
                'booked': booked,
                'load_percent': round(load_pct, 1)
            })

        data = {
            'sessions_today': sessions_today,
            'tickets_sold': tickets_sold,
            'revenue': revenue,
            'occupancy_rate': round(occupancy_rate, 1),
            'movies_active': movies_active,
            'halls_total': halls_total,
            'sales_chart': sales_chart,
            'hall_load': hall_load,
        }

        serializer = DashboardStatsSerializer(data)
        return Response(serializer.data)
    
    @extend_schema(parameters=None, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=['get'])
    def sales_report(self, request):
        today = timezone.localdate()
        date_from = request.query_params.get('date_from', (today - timedelta(days=30)).isoformat())
        date_to = request.query_params.get('date_to', today.isoformat())
        
        payments = Payment.objects.filter(
            status='completed',
            completed_at__date__gte=date_from,
            completed_at__date__lte=date_to
        ).select_related('ticket__booking__session__movie', 'ticket__booking__session__hall')
        
        by_movie = payments.values('ticket__booking__session__movie__title').annotate(
            tickets=Count('id'),
            revenue=Sum('amount')
        ).order_by('-revenue')
        
        by_hall = payments.values('ticket__booking__session__hall__number', 'ticket__booking__session__hall__type').annotate(
            tickets=Count('id'),
            revenue=Sum('amount')
        ).order_by('-revenue')
        
        by_method = payments.values('method').annotate(
            count=Count('id'),
            total=Sum('amount')
        ).order_by('-total')
        
        daily = payments.annotate(day=TruncDate('completed_at')).values('day').annotate(
            tickets=Count('id'),
            revenue=Sum('amount')
        ).order_by('day')
        
        return Response({
            'date_from': date_from,
            'date_to': date_to,
            'by_movie': list(by_movie),
            'by_hall': list(by_hall),
            'by_method': list(by_method),
            'daily': list(daily),
        })


# Frontend Views
from django.views.generic import TemplateView, FormView, View
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.conf import settings
from django.db.models import Prefetch
from .forms import RegisterForm


class FavoriteListAPIView(APIView):
    """GET /api/favorites/ — избранные фильмы текущего пользователя"""
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=FavoriteSerializer(many=True))
    def get(self, request):
        favorites = request.user.favorites.select_related('movie').all()
        return Response(FavoriteSerializer(favorites, many=True).data)


class FavoriteToggleAPIView(APIView):
    """POST /api/favorites/{movie_id}/ — добавить, DELETE — убрать"""
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses=FavoriteSerializer)
    def post(self, request, movie_id):
        movie = get_object_or_404(Movie, pk=movie_id)
        favorite, created = Favorite.objects.get_or_create(
            user=request.user, movie=movie
        )
        return Response(
            FavoriteSerializer(favorite).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @extend_schema(request=None, responses=None)
    def delete(self, request, movie_id):
        Favorite.objects.filter(user=request.user, movie_id=movie_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MovieReviewsAPIView(APIView):
    """GET /api/movies/{movie_id}/reviews/ — отзывы и рейтинг фильма"""
    permission_classes = [AllowAny]

    @extend_schema(responses=MovieReviewsSummarySerializer)
    def get(self, request, movie_id):
        movie = get_object_or_404(Movie, pk=movie_id)
        reviews = movie.reviews.select_related('user').all()
        summary = movie.reviews.aggregate(
            average=Avg('rating'), count=Count('id')
        )
        return Response({
            'movie': movie.id,
            'rating': round(float(summary['average']), 1)
            if summary['average'] is not None else None,
            'count': summary['count'],
            'results': ReviewSerializer(reviews, many=True).data,
        })


class ReviewListCreateAPIView(APIView):
    """GET /api/reviews/ — список отзывов, POST — создать/обновить свой отзыв"""
    permission_classes = [AllowAny]

    @extend_schema(responses=ReviewSerializer(many=True))
    def get(self, request):
        reviews = Review.objects.select_related('user', 'movie').all()
        return Response(ReviewSerializer(reviews, many=True).data)

    @extend_schema(request=ReviewCreateSerializer, responses=ReviewSerializer)
    def post(self, request):
        if not request.user.is_authenticated:
            return Response({'detail': 'Аутентификация требуется'},
                            status=status.HTTP_401_UNAUTHORIZED)
        serializer = ReviewCreateSerializer(
            data=request.data, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        review = serializer.save()
        return Response(ReviewSerializer(review).data, status=status.HTTP_201_CREATED)


def movie_badges(first_date, last_date):
    """Бейджи карточки фильма: «Премьера» и «Последние сеансы» (п.12)"""
    badges = []
    today = timezone.localdate()
    if first_date is not None and (first_date - today).days <= 7:
        badges.append(('Премьера', 'badge-gold'))
    if last_date is not None and (last_date - today).days <= 3:
        badges.append(('Последние сеансы', 'badge-red'))
    return badges


class HomeView(TemplateView):
    template_name = 'home.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        movies = list(Movie.objects.filter(
            status='active'
        ).select_related('genre').annotate(
            average_rating=Avg('reviews__rating'),
            reviews_count=Count('reviews', distinct=True),
        ).prefetch_related(
            Prefetch('sessions', queryset=Session.objects.filter(
                date__gte=today, is_active=True
            ).select_related('hall').order_by('date', 'time'))
        )[:12])

        for movie in movies:
            sessions = list(movie.sessions.all())
            session_dates = [s.date for s in sessions]
            movie.badges = movie_badges(
                session_dates[0], session_dates[-1]
            ) if session_dates else []
            movie.filter_dates = sorted({s.date.isoformat() for s in sessions})
            movie.filter_formats = sorted({s.hall.type for s in sessions})

            days = {}
            for session in sessions:
                days.setdefault(session.date, []).append(session)
            movie.session_days = []
            for day, day_sessions in sorted(days.items()):
                if day == today:
                    label = 'Сегодня'
                elif day == today + timedelta(days=1):
                    label = 'Завтра'
                else:
                    label = day.strftime('%d.%m')
                movie.session_days.append({
                    'date': day, 'label': label, 'sessions': day_sessions,
                })
        context['movies'] = movies

        hero = None
        for movie in sorted(
            movies, key=lambda m: (m.average_rating or 0, m.reviews_count or 0),
            reverse=True,
        ):
            if movie.session_days:
                hero = movie
                break
        if hero is None and movies:
            hero = movies[0]
        context['hero'] = hero

        filter_dates = []
        for i in range(5):
            day = today + timedelta(days=i)
            if i == 0:
                label = 'Сегодня'
            elif i == 1:
                label = 'Завтра'
            else:
                label = day.strftime('%d.%m')
            filter_dates.append({'iso': day.isoformat(), 'label': label})
        context['filter_dates'] = filter_dates

        context['genres'] = Genre.objects.filter(
            movies__status='active'
        ).distinct().order_by('name')

        context['upcoming'] = list(Movie.objects.filter(
            status='upcoming'
        ).select_related('genre').annotate(
            average_rating=Avg('reviews__rating'),
            reviews_count=Count('reviews', distinct=True),
        ).order_by('created_at')[:6])

        context['reviews'] = list(
            Review.objects.select_related('user', 'movie')
            .exclude(comment__isnull=True)
            .exclude(comment='')
            .order_by('-created_at')[:6]
        )

        if self.request.user.is_authenticated:
            context['favorite_ids'] = set(
                self.request.user.favorites.values_list('movie_id', flat=True)
            )
        else:
            context['favorite_ids'] = set()
        return context


class MovieDetailView(TemplateView):
    template_name = 'movie_detail.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        movie = get_object_or_404(
            Movie.objects.select_related('genre').annotate(
                average_rating=Avg('reviews__rating'),
                reviews_count=Count('reviews', distinct=True),
            ),
            pk=kwargs['pk'],
        )
        context['movie'] = movie
        
        sessions = list(movie.sessions.filter(
            date__gte=timezone.localdate(), is_active=True
        ).select_related('hall').order_by('date', 'time'))
        
        sessions_by_date = {}
        for session in sessions:
            date_key = session.date.isoformat()
            if date_key not in sessions_by_date:
                sessions_by_date[date_key] = []
            sessions_by_date[date_key].append(session)
        
        context['sessions_by_date'] = sessions_by_date
        context['reviews'] = movie.reviews.select_related('user').all()
        context['badges'] = movie_badges(
            sessions[0].date, sessions[-1].date
        ) if sessions else []

        user = self.request.user
        if user.is_authenticated:
            context['is_favorite'] = user.favorites.filter(movie=movie).exists()
            context['user_review'] = Review.objects.filter(user=user, movie=movie).first()
            from .models import BookingStatus, TicketStatus
            context['can_review'] = (
                context['user_review'] is not None
                or Ticket.objects.filter(
                    booking__client=user, booking__session__movie=movie,
                    status=TicketStatus.USED,
                ).exists()
                or Booking.objects.filter(
                    client=user, session__movie=movie,
                    status=BookingStatus.USED,
                ).exists()
            )
        else:
            context['is_favorite'] = False
            context['user_review'] = None
            context['can_review'] = False
        return context


def _ticket_qr_data_uri(barcode):
    """QR-код штрихкода билета как data URI (библиотека qrcode + Pillow)."""
    import base64
    import io

    import qrcode

    qr = qrcode.QRCode(version=None, box_size=10, border=2)
    qr.add_data(barcode)
    qr.make(fit=True)
    img = qr.make_image(fill_color='#0d0e12', back_color='white')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


class TicketDetailView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Страница билета с QR-кодом: только владелец или персонал.

    QR генерируется на сервере из штрихкода билета (qrcode + Pillow).
    Печатная версия — @media print в шаблоне ticket.html.
    """
    template_name = 'ticket.html'
    login_url = 'login'

    def test_func(self):
        ticket = get_object_or_404(
            Ticket.objects.select_related(
                'booking__client', 'booking__session__movie',
                'booking__session__hall', 'booking__seat',
            ),
            pk=self.kwargs['pk'],
        )
        self.ticket = ticket
        user = self.request.user
        return (
            ticket.booking.client_id == user.id
            or user.role in ['cashier', 'controller', 'manager', 'admin']
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ticket = get_object_or_404(
            Ticket.objects.select_related(
                'booking__client', 'booking__session__movie',
                'booking__session__hall', 'booking__seat',
                'booking__ticket_type',
            ),
            pk=kwargs['pk'],
        )
        context['ticket'] = ticket
        context['booking'] = ticket.booking
        context['session'] = ticket.booking.session
        context['movie'] = ticket.booking.session.movie
        context['qr_data_uri'] = _ticket_qr_data_uri(ticket.barcode)
        return context


class PaymentPageView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Страница оплаты брони с таймером удержания мест.

    «Место удерживается MM:SS» — до expires_at; по истечении JS показывает
    сообщение и возвращает на выбор мест. Оплата — через services.confirm_payment.
    """
    template_name = 'pay.html'
    login_url = 'login'

    def test_func(self):
        booking = get_object_or_404(
            Booking.objects.select_related('session__movie', 'session__hall'),
            pk=self.kwargs['booking_id'],
        )
        self.booking_obj = booking
        user = self.request.user
        return (
            booking.client_id == user.id
            or user.role in ['cashier', 'manager', 'admin']
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        booking = get_object_or_404(
            Booking.objects.select_related(
                'session__movie', 'session__hall', 'seat', 'ticket_type',
            ),
            pk=kwargs['booking_id'],
        )
        context['booking'] = booking
        context['session'] = booking.session
        base_price = booking.session.get_price_for_category(booking.seat.category)
        context['base_price'] = base_price
        context['final_price'] = services.calculate_ticket_price(
            base_price, booking.ticket_type
        )
        context['is_expired'] = booking.is_expired()
        context['can_pay'] = (
            booking.status == 'pending_payment' and not context['is_expired']
        )
        return context

    def post(self, request, *args, **kwargs):
        booking = get_object_or_404(
            Booking.objects.select_related('session__movie', 'session__hall', 'seat'),
            pk=kwargs['booking_id'],
            client=request.user,
        )
        if booking.status != 'pending_payment':
            messages.error(request, 'Это бронирование не ожидает оплаты')
            return redirect('profile')

        method = request.POST.get('method', 'online')
        if method in payments.PROVIDERS:
            # Онлайн-оплата Kaspi/Халык: создаём intent и уходим в демо-шлюз
            try:
                intent = payments.create_intent(booking, method)
            except payments.PaymentGatewayError as exc:
                messages.error(request, exc.message)
                return redirect('booking', session_id=booking.session_id)
            return redirect('payment_gateway', external_id=intent.external_id)

        try:
            ticket = services.confirm_payment(booking, 'online', request.user)
        except services.BookingError as exc:
            messages.error(request, exc.message)
            return redirect('booking', session_id=booking.session_id)
        return redirect('ticket_detail', pk=ticket.pk)


class PaymentGatewayView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Демо-шлюз Kaspi/Халык: страница «оплаты у провайдера».

    Показывает брендинг провайдера и кнопки успеха/отказа. В боевой
    интеграции вместо кнопок пользователь был бы редиректнут на сайт
    банка; здесь решение шлёт подписанный webhook в payment_webhook.
    """
    template_name = 'pay/gateway.html'
    login_url = 'login'

    def test_func(self):
        intent = get_object_or_404(
            PaymentIntent.objects.select_related('booking__client'),
            external_id=self.kwargs['external_id'],
        )
        self.intent_obj = intent
        user = self.request.user
        return (
            intent.booking.client_id == user.id
            or user.role in ['cashier', 'manager', 'admin']
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        intent = self.intent_obj
        context['intent'] = intent
        context['booking'] = intent.booking
        context['session'] = intent.booking.session
        context['provider_label'] = intent.get_provider_display()
        context['is_kaspi'] = intent.provider == PaymentIntent.PROVIDER_KASPI
        return context


class PaymentGatewayDecideView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Демо-кнопки шлюза: успех/отказ → подписанный webhook в payment_webhook."""
    login_url = 'login'

    def test_func(self):
        intent = get_object_or_404(
            PaymentIntent.objects.select_related('booking__client'),
            external_id=self.kwargs['external_id'],
        )
        self.intent_obj = intent
        user = self.request.user
        return (
            intent.booking.client_id == user.id
            or user.role in ['cashier', 'manager', 'admin']
        )

    def post(self, request, *args, **kwargs):
        intent = self.intent_obj
        decision = request.POST.get('decision')
        if decision not in ('success', 'declined'):
            messages.error(request, 'Некорректное решение платежа')
            return redirect('payment_gateway', external_id=intent.external_id)

        payload = {
            'provider': intent.provider,
            'external_id': str(intent.external_id),
            'status': decision,
            'amount': str(intent.amount),
            'transaction_id': f'{intent.provider}-{uuid.uuid4().hex[:16].upper()}',
            'timestamp': timezone.now().isoformat(),
        }
        signature = payments.sign_payload(payload)
        try:
            result = payments.process_webhook(intent.provider, payload, signature)
        except payments.PaymentGatewayError as exc:
            messages.error(request, exc.message)
            if exc.code == 409:
                return redirect('booking', session_id=intent.booking.session_id)
            return redirect('payment_gateway', external_id=intent.external_id)

        if result['status'] == PaymentIntent.STATUS_SUCCESS:
            messages.success(request, 'Оплата прошла успешно — билет готов')
            ticket_id = result.get('ticket_id')
            if not ticket_id:
                # Идемпотентный повтор: intent уже закрыт, берём билет брони
                booking = intent.booking
                ticket_id = booking.ticket.id if hasattr(booking, 'ticket') else None
            if ticket_id:
                return redirect('ticket_detail', pk=ticket_id)
            return redirect('profile')
        messages.error(request, 'Платёж отклонён провайдером. Место ещё удерживается.')
        return redirect('pay_booking', booking_id=intent.booking_id)


@csrf_exempt
def payment_webhook(request, provider):
    """HTTP-эндпоинт webhook'а провайдера (Kaspi/Халык).

    Ожидает JSON {provider, external_id, status, amount, transaction_id,
    timestamp} и заголовок X-Signature = HMAC-SHA256 канонического payload.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Метод не поддерживается'}, status=405)
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': 'Некорректный JSON'}, status=400)
    signature = request.META.get('HTTP_X_SIGNATURE', '')
    try:
        result = payments.process_webhook(provider, payload, signature)
    except payments.PaymentGatewayError as exc:
        return JsonResponse({'error': exc.message}, status=exc.code)
    return JsonResponse(result, status=200)


class BookingView(LoginRequiredMixin, TemplateView):
    template_name = 'booking.html'
    login_url = 'login'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = get_object_or_404(
            Session.objects.select_related('movie', 'hall', 'movie__genre').prefetch_related('hall__seats'),
            pk=kwargs['session_id'],
            is_active=True
        )
        context['session'] = session
        
        seats = session.hall.seats.all().order_by('row', 'number')
        booked_seat_ids = set(session.bookings.filter(
            status__in=['created', 'pending_payment', 'paid', 'used']
        ).values_list('seat_id', flat=True))
        
        seats_by_row = {}
        for seat in seats:
            row_key = seat.row
            if row_key not in seats_by_row:
                seats_by_row[row_key] = []
            seats_by_row[row_key].append({
                'id': seat.id,
                'number': seat.number,
                'category': seat.category,
                'price': float(session.get_price_for_category(seat.category)),
                'is_booked': seat.id in booked_seat_ids,
                'row': seat.row,
            })
        
        context['seats_by_row'] = dict(sorted(seats_by_row.items()))
        context['ticket_types'] = TicketType.objects.filter(is_active=True)
        return context
    
    def post(self, request, *args, **kwargs):
        session = get_object_or_404(Session, pk=kwargs['session_id'], is_active=True)
        raw = request.POST.get('seats', '').split(',')
        seat_ids = [int(s) for s in raw if s.isdigit()]

        ticket_type = None
        raw_type = request.POST.get('ticket_type', '')
        if raw_type.isdigit():
            ticket_type = TicketType.objects.filter(
                pk=int(raw_type), is_active=True
            ).first()

        try:
            bookings, _ = services.create_booking(
                request.user, session, seat_ids, ticket_type=ticket_type
            )
        except services.BookingError as exc:
            messages.error(request, exc.message)
            return redirect('booking', session_id=session.id)

        messages.success(
            request,
            f'Забронировано {len(bookings)} мест. Осталось оплатить — '
            f'{settings.BOOKING_HOLD_MINUTES} минут на решение.'
        )
        return redirect('pay_booking', booking_id=bookings[0].id)


class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = 'profile.html'
    login_url = 'login'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        context['bookings'] = Booking.objects.filter(
            client=user
        ).select_related(
            'session', 'session__movie', 'session__hall', 'seat', 'ticket'
        ).order_by('-created_at')
        
        context['tickets'] = Ticket.objects.filter(
            booking__client=user
        ).select_related(
            'booking', 'booking__session', 'booking__session__movie',
            'booking__session__hall', 'booking__seat'
        ).order_by('-issued_at')
        
        context['payments'] = Payment.objects.filter(
            ticket__booking__client=user
        ).select_related(
            'ticket', 'ticket__booking', 'ticket__booking__session', 'ticket__booking__session__movie'
        ).order_by('-created_at')

        context['favorites'] = user.favorites.select_related(
            'movie', 'movie__genre'
        ).annotate(
            average_rating=Avg('movie__reviews__rating'),
            reviews_count=Count('movie__reviews', distinct=True),
        )

        return context


class CashierView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = 'cashier.html'
    login_url = 'login'
    
    def test_func(self):
        return self.request.user.role in ['cashier', 'manager', 'admin']
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        
        context['staff_shell'] = True
        context['staff_section'] = 'cashier'
        context['staff_role'] = self.request.user.role
        context['today'] = today
        context['movies'] = Movie.objects.filter(status='active').order_by('title')
        
        sessions = Session.objects.filter(
            date=today, is_active=True
        ).select_related('movie', 'hall').order_by('time')
        
        context['sessions'] = sessions
        return context


class ControllerView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = 'controller.html'
    login_url = 'login'
    
    def test_func(self):
        return self.request.user.role in ['controller', 'manager', 'admin']
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context['staff_shell'] = True
        context['staff_section'] = 'controller'
        context['staff_role'] = self.request.user.role
        
        barcode = self.request.GET.get('barcode')
        if barcode:
            try:
                ticket = Ticket.objects.select_related(
                    'booking', 'booking__client', 'booking__session', 'booking__session__movie',
                    'booking__session__hall', 'booking__seat'
                ).get(barcode=barcode.upper())
                try:
                    ticket, message = services.check_ticket(ticket, actor=self.request.user)
                    valid, already_used, result_message = True, False, message
                except services.BookingError as exc:
                    valid = False
                    already_used = ticket.status == 'used'
                    result_message = exc.message

                context['ticket_result'] = {
                    'valid': valid,
                    'already_used': already_used,
                    'message': result_message,
                    'ticket': {
                        'barcode': ticket.barcode,
                        'movie_title': ticket.booking.session.movie.title,
                        'session_date': ticket.booking.session.date.strftime('%d.%m.%Y'),
                        'session_time': ticket.booking.session.time.strftime('%H:%M'),
                        'hall_number': ticket.booking.session.hall.number,
                        'hall_type': ticket.booking.session.hall.get_type_display(),
                        'seat_row': ticket.booking.seat.row,
                        'seat_number': ticket.booking.seat.number,
                        'seat_category': ticket.booking.seat.get_category_display(),
                        'client_name': ticket.booking.client.get_full_name() or ticket.booking.client.username,
                        'status': ticket.get_status_display(),
                    }
                }
            except Ticket.DoesNotExist:
                context['ticket_result'] = {
                    'valid': False,
                    'message': 'Билет не найден'
                }
        
        # История проверок за сессию (фиксируем только что проверенный код)
        if barcode and 'ticket_result' in context:
            history = list(self.request.session.get('check_history', []))
            if not history or history[0].get('barcode') != barcode:
                history.insert(0, {
                    'barcode': barcode,
                    'valid': bool(context['ticket_result'].get('valid')),
                    'time': timezone.now().strftime('%H:%M:%S'),
                })
                self.request.session['check_history'] = history[:50]
        context['check_history'] = self.request.session.get('check_history', [])
        
        return context
    
    def post(self, request, *args, **kwargs):
        barcode = request.POST.get('barcode', '').strip().upper()
        if barcode:
            return redirect(f'{request.path}?barcode={barcode}')
        return redirect(request.path)


class ManagerView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = 'manager.html'
    login_url = 'login'
    
    def test_func(self):
        return self.request.user.role in ['manager', 'admin']
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        import json
        from django.utils import timezone
        from django.db.models import Sum, Count, Q
        from datetime import timedelta
        
        context['staff_shell'] = True
        context['staff_section'] = 'dashboard'
        context['staff_role'] = self.request.user.role
        
        today = timezone.localdate()

        def parse_date(value, fallback):
            try:
                return date.fromisoformat(value)
            except (TypeError, ValueError):
                return fallback

        date_to = parse_date(self.request.GET.get('date_to'), today)
        date_from = parse_date(
            self.request.GET.get('date_from'), date_to - timedelta(days=6)
        )
        if date_from > date_to:
            date_from, date_to = date_to, date_from
        context['date_from'] = date_from
        context['date_to'] = date_to

        context['today'] = today
        context['now'] = timezone.now()
        context['movies'] = Movie.objects.select_related('genre').order_by('-created_at')[:20]
        context['halls'] = Hall.objects.order_by('number')
        
        sessions = Session.objects.select_related('movie', 'hall').filter(
            date=today, is_active=True
        ).order_by('time').annotate(
            sold_count=Count('bookings', filter=Q(bookings__status__in=['paid', 'used'])),
            revenue_sum=Sum('bookings__ticket__price', filter=Q(bookings__status__in=['paid', 'used'])),
        )
        seats_by_hall = dict(
            Hall.objects.annotate(seats_total=Count('seats')).values_list('id', 'seats_total')
        )
        session_rows = []
        for s in sessions:
            total = seats_by_hall.get(s.hall_id) or 0
            sold = s.sold_count or 0
            session_rows.append({
                'time': s.time,
                'movie': s.movie,
                'hall': s.hall,
                'sold': sold,
                'total': total,
                'percent': round(sold / total * 100) if total else 0,
                'revenue': int(float(s.revenue_sum or 0)),
            })
        context['sessions'] = session_rows
        
        revenue = Payment.objects.filter(
            status='completed',
            completed_at__date=today
        ).aggregate(total=Sum('amount'))['total'] or 0
        tickets_sold = Ticket.objects.filter(
            status__in=['active', 'used'],
            issued_at__date=today
        ).count()
        total_seats = sum(r['total'] for r in session_rows)
        sold_seats = sum(r['sold'] for r in session_rows)
        context['stats'] = {
            'revenue': int(float(revenue)),
            'tickets': tickets_sold,
            'occupancy': round(sold_seats / total_seats * 100) if total_seats else 0,
            'sessions': len(session_rows),
        }
        context['revenue'] = int(float(revenue))
        context['tickets_sold'] = tickets_sold
        context['occupancy'] = context['stats']['occupancy']
        
        # Продажи по дням за выбранный период (для Chart.js)
        payments = Payment.objects.filter(
            status='completed',
            completed_at__date__gte=date_from,
            completed_at__date__lte=date_to,
        )
        rev_by_day = {
            row['day']: row['total']
            for row in payments.annotate(day=TruncDate('completed_at')).values('day').annotate(
                total=Sum('amount')
            )
        }
        chart = []
        span_days = (date_to - date_from).days
        for i in range(span_days + 1):
            d = date_from + timedelta(days=i)
            chart.append({
                'day': d.strftime('%d.%m'),
                'revenue': int(float(rev_by_day.get(d, 0))),
            })
        context['chart'] = chart
        context['chart_labels'] = json.dumps([c['day'] for c in chart])
        context['chart_data'] = json.dumps([c['revenue'] for c in chart])

        # Топ-5 фильмов за период
        top = Ticket.objects.filter(
            status__in=['active', 'used'],
            issued_at__date__gte=date_from,
            issued_at__date__lte=date_to,
        ).values(
            'booking__session__movie__title'
        ).annotate(tickets=Count('id'), revenue=Sum('price')).order_by('-tickets')[:5]
        context['top_films'] = [
            {'title': t['booking__session__movie__title'], 'tickets': t['tickets'],
             'revenue': int(float(t['revenue'] or 0))}
            for t in top
        ]
        context['top_labels'] = json.dumps([t['title'] for t in context['top_films']])
        context['top_data'] = json.dumps([t['tickets'] for t in context['top_films']])

        # Загрузка залов в % (средняя по сеансам периода)
        hall_rows = Session.objects.filter(
            date__gte=date_from, date__lte=date_to, is_active=True
        ).values('hall_id', 'hall__number').annotate(
            sold=Count('bookings', filter=Q(bookings__status__in=['paid', 'used'])),
        )
        hall_stats = {}
        for row in hall_rows:
            entry = hall_stats.setdefault(
                row['hall_id'],
                {'hall': row['hall__number'], 'sold': 0, 'capacity_sessions': 0},
            )
            entry['sold'] += row['sold']
            entry['capacity_sessions'] += seats_by_hall.get(row['hall_id'], 0)
        occupancy_rows = [
            {
                'hall': h['hall'],
                'percent': round(h['sold'] / h['capacity_sessions'] * 100)
                if h['capacity_sessions'] else 0,
            }
            for h in sorted(hall_stats.values(), key=lambda x: x['hall'])
        ]
        context['hall_occupancy'] = occupancy_rows
        context['hall_labels'] = json.dumps(
            [f"Зал {h['hall']}" for h in occupancy_rows]
        )
        context['hall_data'] = json.dumps([h['percent'] for h in occupancy_rows])
        
        return context


class StaffSectionMixin(LoginRequiredMixin, UserPassesTestMixin):
    """База staff-страниц: shell с sidebar + проверка роли."""
    login_url = 'login'
    staff_section = ''
    allowed_roles = ['manager', 'admin']

    def test_func(self):
        return self.request.user.role in self.allowed_roles

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['staff_shell'] = True
        context['staff_section'] = self.staff_section
        context['staff_role'] = self.request.user.role
        return context


class ManagerMoviesView(StaffSectionMixin, TemplateView):
    template_name = 'staff/movies.html'
    staff_section = 'movies'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['movies'] = Movie.objects.select_related('genre').annotate(
            average_rating=Avg('reviews__rating'),
            reviews_count=Count('reviews', distinct=True),
        ).order_by('-created_at')[:200]
        context['genres'] = Genre.objects.order_by('name')
        return context


class ManagerSessionsView(StaffSectionMixin, TemplateView):
    template_name = 'staff/sessions.html'
    staff_section = 'sessions'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sessions'] = Session.objects.select_related(
            'movie', 'hall'
        ).filter(date__gte=timezone.localdate()).order_by('date', 'time')[:200]
        context['movies'] = Movie.objects.filter(
            status__in=['active', 'upcoming']
        ).order_by('title')
        context['halls'] = Hall.objects.order_by('number')
        return context


class ManagerHallsView(StaffSectionMixin, TemplateView):
    template_name = 'staff/halls.html'
    staff_section = 'halls'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['halls'] = Hall.objects.annotate(
            seats_total=Count('seats'),
            sessions_count=Count('sessions', filter=Q(sessions__is_active=True)),
        ).order_by('number')
        return context


class ManagerBookingsView(StaffSectionMixin, TemplateView):
    template_name = 'staff/bookings.html'
    staff_section = 'bookings'
    allowed_roles = ['cashier', 'controller', 'manager', 'admin']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        bookings = Booking.objects.select_related(
            'client', 'session', 'session__movie', 'session__hall',
            'seat', 'ticket',
        ).order_by('-created_at')
        status_filter = self.request.GET.get('status')
        if status_filter in dict(Booking.STATUS_CHOICES):
            bookings = bookings.filter(status=status_filter)
        context['bookings'] = bookings[:200]
        context['status_filter'] = status_filter if status_filter in dict(Booking.STATUS_CHOICES) else ''
        context['status_choices'] = Booking.STATUS_CHOICES
        return context


class ManagerTicketsView(StaffSectionMixin, TemplateView):
    template_name = 'staff/tickets.html'
    staff_section = 'tickets'
    allowed_roles = ['cashier', 'controller', 'manager', 'admin']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tickets = Ticket.objects.select_related(
            'booking', 'booking__client', 'booking__session',
            'booking__session__movie', 'booking__session__hall', 'booking__seat',
        ).order_by('-issued_at')
        status_filter = self.request.GET.get('status')
        if status_filter in dict(Ticket.STATUS_CHOICES):
            tickets = tickets.filter(status=status_filter)
        context['tickets'] = tickets[:200]
        context['status_filter'] = status_filter if status_filter in dict(Ticket.STATUS_CHOICES) else ''
        context['status_choices'] = Ticket.STATUS_CHOICES
        return context


class ManagerClientsView(StaffSectionMixin, TemplateView):
    template_name = 'staff/clients.html'
    staff_section = 'clients'
    allowed_roles = ['cashier', 'manager', 'admin']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['clients'] = User.objects.filter(role='client').annotate(
            bookings_total=Count('bookings'),
            tickets_total=Count('bookings__ticket'),
        ).order_by('-date_joined')[:200]
        return context


class ManagerSalesView(StaffSectionMixin, TemplateView):
    template_name = 'staff/sales.html'
    staff_section = 'sales'
    allowed_roles = ['cashier', 'manager', 'admin']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        payments = Payment.objects.select_related(
            'ticket', 'ticket__booking', 'ticket__booking__client',
            'ticket__booking__session', 'ticket__booking__session__movie',
        ).filter(status='completed').order_by('-completed_at')
        context['payments'] = payments[:200]
        context['sales_today'] = int(float(
            payments.filter(completed_at__date=today).aggregate(
                total=Sum('amount'))['total'] or 0
        ))
        context['tickets_today'] = Ticket.objects.filter(
            status__in=['active', 'used'], issued_at__date=today
        ).count()
        context['method_choices'] = Payment.METHOD_CHOICES
        return context


class ManagerReportsView(StaffSectionMixin, TemplateView):
    template_name = 'staff/reports.html'
    staff_section = 'reports'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()

        def parse_date(value, fallback):
            try:
                return date.fromisoformat(value)
            except (TypeError, ValueError):
                return fallback

        date_to = parse_date(self.request.GET.get('date_to'), today)
        date_from = parse_date(
            self.request.GET.get('date_from'), date_to - timedelta(days=30)
        )
        if date_from > date_to:
            date_from, date_to = date_to, date_from

        context['today'] = today
        context['date_from'] = date_from
        context['date_to'] = date_to

        payments = Payment.objects.filter(
            status='completed',
            completed_at__date__gte=date_from,
            completed_at__date__lte=date_to,
        )
        daily_rows = (
            payments
            .annotate(day=TruncDate('completed_at'))
            .values('day')
            .annotate(revenue=Sum('amount'), tickets=Count('id'))
            .order_by('day')
        )
        daily = {r['day']: r for r in daily_rows}

        chart = []
        total_revenue = 0
        total_tickets = 0
        span_days = (date_to - date_from).days
        for i in range(span_days + 1):
            d = date_from + timedelta(days=i)
            row = daily.get(d)
            rev = int(float(row['revenue'])) if row else 0
            cnt = row['tickets'] if row else 0
            total_revenue += rev
            total_tickets += cnt
            chart.append({'day': d.strftime('%d.%m'), 'revenue': rev, 'tickets': cnt})
        max_rev = max((c['revenue'] for c in chart), default=0) or 1
        for c in chart:
            c['percent'] = max(3, round(c['revenue'] / max_rev * 100))
        context['chart'] = chart
        context['totals'] = {
            'revenue': total_revenue,
            'tickets': total_tickets,
            'avg': round(total_revenue / total_tickets) if total_tickets else 0,
        }

        by_movie_rows = (
            payments
            .values('ticket__booking__session__movie__title')
            .annotate(revenue=Sum('amount'), tickets=Count('id'))
            .order_by('-revenue')[:10]
        )
        context['by_movie'] = [
            {
                'title': r['ticket__booking__session__movie__title'] or '—',
                'revenue': int(float(r['revenue'])),
                'tickets': r['tickets'],
            }
            for r in by_movie_rows
        ]

        by_method_rows = (
            payments
            .values('method')
            .annotate(revenue=Sum('amount'), tickets=Count('id'))
            .order_by('-revenue')
        )
        context['by_method'] = [
            {
                'method': r['method'],
                'label': dict(Payment.METHOD_CHOICES).get(r['method'], r['method']),
                'revenue': int(float(r['revenue'])),
                'tickets': r['tickets'],
            }
            for r in by_method_rows
        ]
        return context


class ManagerSalesExportView(StaffSectionMixin, TemplateView):
    """Экспорт отчёта по продажам в CSV за выбранный период."""

    def get(self, request, *args, **kwargs):
        import csv
        from django.http import HttpResponse

        today = timezone.localdate()

        def parse_date(value, fallback):
            try:
                return date.fromisoformat(value)
            except (TypeError, ValueError):
                return fallback

        date_to = parse_date(request.GET.get('date_to'), today)
        date_from = parse_date(
            request.GET.get('date_from'), date_to - timedelta(days=30)
        )

        payments = Payment.objects.filter(
            status='completed',
            completed_at__date__gte=date_from,
            completed_at__date__lte=date_to,
        ).select_related(
            'ticket__booking__session__movie',
            'ticket__booking__session__hall',
            'ticket__booking__client',
        ).order_by('completed_at')

        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = (
            f'attachment; filename="sales_{date_from}_{date_to}.csv"'
        )
        response.write('﻿')  # BOM для Excel
        writer = csv.writer(response, delimiter=';')
        writer.writerow([
            'Дата', 'Время', 'Фильм', 'Зал', 'Клиент',
            'Штрихкод', 'Способ оплаты', 'Сумма',
        ])
        for p in payments:
            booking = p.ticket.booking
            writer.writerow([
                p.completed_at.strftime('%d.%m.%Y') if p.completed_at else '',
                p.completed_at.strftime('%H:%M') if p.completed_at else '',
                booking.session.movie.title,
                f'{booking.session.hall.number} ({booking.session.hall.get_type_display()})',
                booking.client.username,
                p.ticket.barcode,
                p.get_method_display(),
                f'{p.amount:.2f}',
            ])
        return response


class ManagerUsersView(StaffSectionMixin, TemplateView):
    template_name = 'staff/users.html'
    staff_section = 'users'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['staff_users'] = User.objects.order_by('-date_joined')[:200]
        context['role_choices'] = User.ROLE_CHOICES
        return context


class RegisterView(FormView):
    template_name = 'register.html'
    form_class = RegisterForm
    success_url = '/profile/'
    
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('profile')
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        user = form.save()
        from django.contrib.auth import login
        login(self.request, user)
        messages.success(self.request, 'Регистрация прошла успешно! Добро пожаловать в АИС «Аврора».')
        return super().form_valid(form)

# -- SEO: robots.txt � sitemap.xml --------------------------
from django.http import HttpResponse  # noqa: E402


def robots_txt(request):
    lines = [
        'User-agent: *',
        'Allow: /',
        'Disallow: /admin/',
        'Disallow: /manager/',
        'Disallow: /cashier/',
        'Disallow: /controller/',
        'Disallow: /profile/',
        'Disallow: /api/',
        'Disallow: /login/',
        'Disallow: /register/',
        'Disallow: /logout/',
        f'Sitemap: {request.build_absolute_uri("/sitemap.xml")}',
        '',
    ]
    return HttpResponse('\n'.join(lines), content_type='text/plain; charset=utf-8')


def sitemap_xml(request):
    from cinema.models import Movie

    urls = [
        (request.build_absolute_uri('/'), None, 'daily', '1.0'),
    ]
    for m in Movie.objects.filter(status='active').order_by('id'):
        urls.append((
            request.build_absolute_uri(f'/film/{m.id}/'),
            m.updated_at.date().isoformat(),
            'weekly',
            '0.8',
        ))
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, lastmod, freq, priority in urls:
        parts.append('  <url>')
        parts.append(f'    <loc>{loc}</loc>')
        if lastmod:
            parts.append(f'    <lastmod>{lastmod}</lastmod>')
        parts.append(f'    <changefreq>{freq}</changefreq>')
        parts.append(f'    <priority>{priority}</priority>')
        parts.append('  </url>')
    parts.append('</urlset>')
    return HttpResponse('\n'.join(parts), content_type='application/xml; charset=utf-8')


# ── Health check (для мониторинга/хостинга) ──────────────
from django.http import JsonResponse  # noqa: E402
from django.core.cache import cache  # noqa: E402
from django.contrib.auth import login as auth_login  # noqa: E402
from django.contrib.auth import views as auth_views  # noqa: E402


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


def _rate_limited(request, key, limit=10, window=300):
    """Простой счётчик попыток в кэше: limit за window секунд."""
    cache_key = f'rate:{key}:{_client_ip(request)}'
    used = cache.get(cache_key, 0)
    if used >= limit:
        return True
    cache.set(cache_key, used + 1, window)
    return False


class ThrottledLoginView(auth_views.LoginView):
    """Вход с ограничением 10 попыток за 5 минут с одного IP."""
    template_name = 'login.html'
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        if _rate_limited(request, 'login', limit=10, window=300):
            messages.error(request, 'Слишком много попыток входа. Попробуйте через 5 минут.')
            return self.get(request)
        return super().post(request, *args, **kwargs)


class ThrottledRegisterView(RegisterView):
    """Регистрация с ограничением 5 попыток за 10 минут с одного IP."""

    def post(self, request, *args, **kwargs):
        if _rate_limited(request, 'register', limit=5, window=600):
            messages.error(request, 'Слишком много попыток регистрации. Попробуйте позже.')
            return self.get(request)
        return super().post(request, *args, **kwargs)


def health(request):
    from django.db import connection
    from django.db.utils import Error as DatabaseError

    db_status = 'ok'
    try:
        connection.ensure_connection()
    except DatabaseError as exc:
        db_status = f'error: {exc.__class__.__name__}'

    from django.conf import settings as dj_settings
    from cinema.models import Movie

    posters_dir = Path(dj_settings.MEDIA_ROOT) / 'posters'
    posters_on_disk = sorted(p.name for p in posters_dir.glob('*.jpg')) if posters_dir.is_dir() else []

    payload = {
        'status': 'ok' if db_status == 'ok' else 'degraded',
        'database': db_status,
        'debug': dj_settings.DEBUG,
        'media_root': str(dj_settings.MEDIA_ROOT),
        'posters_dir_exists': posters_dir.is_dir(),
        'posters_on_disk': posters_on_disk,
        'movies_with_poster': int(Movie.objects.exclude(poster='').count()),
        'movies_total': int(Movie.objects.count()),
    }
    return JsonResponse(payload, status=200 if db_status == 'ok' else 503)


# ── Кабинет: отмена брони, смена пароля, редактирование ──
from django.contrib.auth.forms import PasswordChangeForm  # noqa: E402


class ProfilePasswordChangeView(LoginRequiredMixin, FormView):
    """Смена пароля через личный кабинет."""
    template_name = 'profile.html'
    login_url = 'login'
    form_class = PasswordChangeForm
    success_url = '/profile/'

    def get(self, request, *args, **kwargs):
        return redirect('profile')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.save()
        from django.contrib.auth import update_session_auth_hash
        update_session_auth_hash(self.request, form.user)
        messages.success(self.request, 'Пароль успешно изменён.')
        log_audit(self.request.user, 'change_password', 'Смена пароля через кабинет')
        return super().form_valid(form)

    def form_invalid(self, form):
        for error in form.errors.values():
            messages.error(self.request, error.as_text().strip())
        return redirect('profile')


class ProfileEditView(LoginRequiredMixin, TemplateView):
    """Редактирование профиля (имя, телефон, email)."""
    template_name = 'profile.html'
    login_url = 'login'

    def get(self, request, *args, **kwargs):
        return redirect('profile')

    def post(self, request, *args, **kwargs):
        user = request.user
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()

        if email and User.objects.filter(email=email).exclude(pk=user.pk).exists():
            messages.error(request, 'Этот email уже используется.')
            return redirect('profile')

        user.first_name = first_name
        user.last_name = last_name
        if email:
            user.email = email
        user.phone = phone
        user.save()
        messages.success(request, 'Профиль обновлён.')
        log_audit(user, 'update_profile', 'Редактирование профиля через кабинет')
        return redirect('profile')


class ProfileCancelBookingView(LoginRequiredMixin, TemplateView):
    """Клиент отменяет свою непогашенную бронь до начала сеанса."""
    template_name = 'profile.html'
    login_url = 'login'

    def post(self, request, booking_id, *args, **kwargs):
        booking = get_object_or_404(Booking, pk=booking_id, client=request.user)
        try:
            services.cancel_booking(booking, request.user, force=False)
        except services.BookingError as exc:
            messages.error(request, exc.message)
        else:
            messages.success(request, f'Бронь #{booking.id} отменена.')
        return redirect('profile')

