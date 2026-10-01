from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Sum, Q, F
from django.utils import timezone
from datetime import timedelta, date
import uuid

from .models import User, Genre, Movie, Hall, Seat, Session, Booking, Ticket, Payment
from .serializers import (
    UserSerializer, UserCreateSerializer, GenreSerializer, MovieSerializer,
    MovieListSerializer, HallSerializer, SeatSerializer, SessionSerializer,
    SessionListSerializer, BookingSerializer, BookingCreateSerializer,
    TicketSerializer, PaymentSerializer, PaymentCreateSerializer,
    DashboardStatsSerializer
)
from .permissions import (
    IsAdminOrManager, IsAdmin, IsCashierOrAbove, IsControllerOrAbove,
    IsOwnerOrStaff, IsClientOrReadOnly, PublicReadOnly
)


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['role', 'is_active']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering_fields = ['username', 'date_joined']
    
    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        return UserSerializer
    
    def get_permissions(self):
        if self.action in ['create']:
            return [AllowAny()]
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        return [IsAdminOrManager()]
    
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
            return [PublicReadOnly()]
        return [IsAdminOrManager()]


class MovieViewSet(viewsets.ModelViewSet):
    queryset = Movie.objects.select_related('genre').all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['genre', 'status', 'age_rating']
    search_fields = ['title', 'description']
    ordering_fields = ['title', 'created_at', 'duration']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return MovieListSerializer
        return MovieSerializer
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [PublicReadOnly()]
        return [IsAdminOrManager()]
    
    @action(detail=True, methods=['get'], permission_classes=[PublicReadOnly])
    def sessions(self, request, pk=None):
        movie = self.get_object()
        sessions = movie.sessions.filter(date__gte=date.today(), is_active=True).order_by('date', 'time')
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
            return [PublicReadOnly()]
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
            return [PublicReadOnly()]
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
        if self.action in ['list', 'retrieve', 'by_date']:
            return [PublicReadOnly()]
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
    
    @action(detail=False, methods=['get'], permission_classes=[PublicReadOnly])
    def by_date(self, request):
        target_date = request.query_params.get('date', date.today().isoformat())
        sessions = self.get_queryset().filter(date=target_date, is_active=True).order_by('time')
        serializer = self.get_serializer(sessions, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'], permission_classes=[PublicReadOnly])
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
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status', 'session', 'client']
    ordering_fields = ['created_at', 'status']
    
    def get_serializer_class(self):
        if self.action == 'create':
            return BookingCreateSerializer
        return BookingSerializer
    
    def get_permissions(self):
        if self.action == 'create':
            return [IsAuthenticated()]
        if self.action in ['list', 'retrieve']:
            return [IsOwnerOrStaff()]
        return [IsCashierOrAbove()]
    
    def get_queryset(self):
        user = self.request.user
        if user.role in ['cashier', 'controller', 'manager', 'admin']:
            return super().get_queryset()
        return super().get_queryset().filter(client=user)
    
    def perform_create(self, serializer):
        serializer.save(client=self.request.user)
    
    @action(detail=True, methods=['post'], permission_classes=[IsCashierOrAbove])
    def confirm_payment(self, request, pk=None):
        booking = self.get_object()
        if booking.status != 'pending_payment':
            return Response({'error': 'Бронирование не ожидает оплаты'}, status=status.HTTP_400_BAD_REQUEST)
        
        ticket = Ticket.objects.create(
            booking=booking,
            price=booking.session.get_price_for_category(booking.seat.category),
            barcode=str(uuid.uuid4()).replace('-', '').upper()[:20],
            status='active'
        )
        
        Payment.objects.create(
            ticket=ticket,
            amount=ticket.price,
            method=request.data.get('method', 'cash'),
            status='completed',
            completed_at=timezone.now()
        )
        
        booking.status = 'paid'
        booking.save()
        
        return Response(TicketSerializer(ticket, context={'request': request}).data)
    
    @action(detail=True, methods=['post'], permission_classes=[IsCashierOrAbove])
    def cancel(self, request, pk=None):
        booking = self.get_object()
        if booking.status in ['used', 'cancelled', 'expired']:
            return Response({'error': 'Нельзя отменить это бронирование'}, status=status.HTTP_400_BAD_REQUEST)
        
        booking.status = 'cancelled'
        booking.save()
        if hasattr(booking, 'ticket'):
            booking.ticket.status = 'cancelled'
            booking.ticket.save()
        
        return Response(BookingSerializer(booking, context={'request': request}).data)
    
    @action(detail=False, methods=['post'], permission_classes=[IsCashierOrAbove])
    def expire_old(self, request):
        expired_bookings = Booking.objects.filter(
            status__in=['created', 'pending_payment'],
            expires_at__lt=timezone.now()
        )
        count = expired_bookings.count()
        expired_bookings.update(status='expired')
        return Response({'expired_count': count})


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
        if user.role in ['cashier', 'controller', 'manager', 'admin']:
            return super().get_queryset()
        return super().get_queryset().filter(booking__client=user)
    
    @action(detail=True, methods=['post'], permission_classes=[IsControllerOrAbove])
    def validate_ticket(self, request, barcode=None):
        ticket = self.get_object()
        
        if ticket.status == 'used':
            return Response({
                'valid': False,
                'message': 'Билет уже использован',
                'ticket': TicketSerializer(ticket, context={'request': request}).data
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if ticket.status in ['refunded', 'cancelled']:
            return Response({
                'valid': False,
                'message': 'Билет аннулирован или возвращён',
                'ticket': TicketSerializer(ticket, context={'request': request}).data
            }, status=status.HTTP_400_BAD_REQUEST)
        
        ticket.mark_used()
        return Response({
            'valid': True,
            'message': 'Билет действителен, вход разрешён',
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
        
        if ticket.status == 'used':
            return Response({
                'valid': False,
                'message': 'Билет уже использован',
                'ticket': TicketSerializer(ticket, context={'request': request}).data
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if ticket.status in ['refunded', 'cancelled']:
            return Response({
                'valid': False,
                'message': 'Билет аннулирован или возвращён',
                'ticket': TicketSerializer(ticket, context={'request': request}).data
            }, status=status.HTTP_400_BAD_REQUEST)
        
        ticket.mark_used()
        return Response({
            'valid': True,
            'message': 'Билет действителен, вход разрешён',
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
        if user.role in ['cashier', 'controller', 'manager', 'admin']:
            return super().get_queryset()
        return super().get_queryset().filter(ticket__booking__client=user)


class DashboardViewSet(viewsets.ViewSet):
    permission_classes = [IsAdminOrManager]
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        today = date.today()
        now = timezone.now()
        
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
        
        # График продаж за последние 7 дней
        sales_chart = []
        for i in range(7):
            day = today - timedelta(days=i)
            day_revenue = Payment.objects.filter(
                status='completed',
                completed_at__date=day
            ).aggregate(total=Sum('amount'))['total'] or 0
            day_tickets = Ticket.objects.filter(
                status__in=['active', 'used'],
                issued_at__date=day
            ).count()
            sales_chart.append({
                'date': day.isoformat(),
                'revenue': float(day_revenue),
                'tickets': day_tickets
            })
        sales_chart.reverse()
        
        # Загрузка залов
        hall_load = []
        for hall in Hall.objects.all():
            hall_sessions = Session.objects.filter(hall=hall, date=today, is_active=True)
            total_capacity = hall_sessions.count() * hall.capacity
            booked = Booking.objects.filter(
                session__in=hall_sessions,
                status__in=['paid', 'used']
            ).count()
            load_pct = (booked / total_capacity * 100) if total_capacity > 0 else 0
            hall_load.append({
                'hall': f'Зал {hall.number} ({hall.get_type_display()})',
                'capacity': hall.capacity,
                'sessions': hall_sessions.count(),
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
        serializer.is_valid()
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def sales_report(self, request):
        date_from = request.query_params.get('date_from', (date.today() - timedelta(days=30)).isoformat())
        date_to = request.query_params.get('date_to', date.today().isoformat())
        
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
        
        daily = payments.extra(select={'day': 'date(completed_at)'}).values('day').annotate(
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
from django.views.generic import TemplateView, FormView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Prefetch
from .forms import RegisterForm


class HomeView(TemplateView):
    template_name = 'home.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['movies'] = Movie.objects.filter(
            status='active'
        ).select_related('genre').prefetch_related(
            Prefetch('sessions', queryset=Session.objects.filter(
                date__gte=date.today(), is_active=True
            ).order_by('date', 'time'))
        )[:12]
        return context


class MovieDetailView(TemplateView):
    template_name = 'movie_detail.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        movie = get_object_or_404(Movie.objects.select_related('genre'), pk=kwargs['pk'])
        context['movie'] = movie
        
        sessions = movie.sessions.filter(
            date__gte=date.today(), is_active=True
        ).select_related('hall').order_by('date', 'time')
        
        sessions_by_date = {}
        for session in sessions:
            date_key = session.date.isoformat()
            if date_key not in sessions_by_date:
                sessions_by_date[date_key] = []
            sessions_by_date[date_key].append(session)
        
        context['sessions_by_date'] = sessions_by_date
        return context


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
        return context
    
    def post(self, request, *args, **kwargs):
        session = get_object_or_404(Session, pk=kwargs['session_id'], is_active=True)
        seat_ids = request.POST.get('seats', '').split(',')
        seat_ids = [int(s) for s in seat_ids if s.isdigit()]
        
        if not seat_ids:
            messages.error(request, 'Не выбрано ни одного места')
            return redirect('booking', session_id=session.id)
        
        if len(seat_ids) > 8:
            messages.error(request, 'Максимум 8 мест за раз')
            return redirect('booking', session_id=session.id)
        
        seats = Seat.objects.filter(id__in=seat_ids, hall=session.hall)
        if seats.count() != len(seat_ids):
            messages.error(request, 'Некорректные места')
            return redirect('booking', session_id=session.id)
        
        # Проверка доступности
        booked = Booking.objects.filter(
            session=session,
            seat__in=seats,
            status__in=['created', 'pending_payment', 'paid', 'used']
        ).exists()
        
        if booked:
            messages.error(request, 'Одно или несколько мест уже заняты')
            return redirect('booking', session_id=session.id)
        
        # Создание броней
        from django.utils import timezone
        from datetime import timedelta
        expires_at = timezone.now() + timedelta(minutes=15)
        
        for seat in seats:
            Booking.objects.create(
                client=request.user,
                session=session,
                seat=seat,
                status='pending_payment',
                expires_at=expires_at
            )
        
        messages.success(request, f'Забронировано {len(seat_ids)} мест. Ожидает оплаты.')
        return redirect('profile')


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
        
        return context


class CashierView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = 'cashier.html'
    login_url = 'login'
    
    def test_func(self):
        return self.request.user.role in ['cashier', 'manager', 'admin']
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        
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
        
        barcode = self.request.GET.get('barcode')
        if barcode:
            try:
                ticket = Ticket.objects.select_related(
                    'booking', 'booking__client', 'booking__session', 'booking__session__movie',
                    'booking__session__hall', 'booking__seat'
                ).get(barcode=barcode.upper())
                
                if ticket.status == 'used':
                    context['ticket_result'] = {
                        'valid': False,
                        'already_used': True,
                        'message': 'Билет уже использован',
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
                elif ticket.status in ['refunded', 'cancelled']:
                    context['ticket_result'] = {
                        'valid': False,
                        'message': 'Билет аннулирован или возвращён',
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
                else:
                    ticket.mark_used()
                    context['ticket_result'] = {
                        'valid': True,
                        'message': 'Билет действителен, вход разрешён',
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
        
        # История проверок за сессию
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
        from django.utils import timezone
        from django.db.models import Sum, Count, Q
        from datetime import timedelta
        
        today = date.today()
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
        session_rows = []
        for s in sessions:
            total = s.hall.seats.count()
            session_rows.append({
                'time': s.time,
                'movie': s.movie,
                'hall': s.hall,
                'sold': s.sold_count or 0,
                'total': total,
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
        
        chart = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            day_rev = Payment.objects.filter(
                status='completed',
                completed_at__date=d
            ).aggregate(total=Sum('amount'))['total'] or 0
            chart.append({
                'day': d.strftime('%d.%m'),
                'revenue': int(float(day_rev)),
            })
        max_rev = max(c['revenue'] for c in chart) or 1
        for c in chart:
            c['percent'] = max(6, round(c['revenue'] / max_rev * 100))
        context['chart'] = chart
        
        top = Ticket.objects.filter(
            status__in=['active', 'used'],
            issued_at__date__gte=today - timedelta(days=7)
        ).values(
            'booking__session__movie__title'
        ).annotate(tickets=Count('id')).order_by('-tickets')[:5]
        max_top = top[0]['tickets'] if top else 1
        context['top_films'] = [
            {'title': t['booking__session__movie__title'], 'tickets': t['tickets'],
             'percent': round(t['tickets'] / max_top * 100)}
            for t in top
        ]
        context['top_movies'] = context['top_films']
        
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