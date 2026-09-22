from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    UserViewSet, GenreViewSet, MovieViewSet, HallViewSet, SeatViewSet,
    SessionViewSet, BookingViewSet, TicketViewSet, PaymentViewSet, DashboardViewSet
)

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'genres', GenreViewSet, basename='genre')
router.register(r'movies', MovieViewSet, basename='movie')
router.register(r'halls', HallViewSet, basename='hall')
router.register(r'seats', SeatViewSet, basename='seat')
router.register(r'sessions', SessionViewSet, basename='session')
router.register(r'bookings', BookingViewSet, basename='booking')
router.register(r'tickets', TicketViewSet, basename='ticket')
router.register(r'payments', PaymentViewSet, basename='payment')
router.register(r'dashboard', DashboardViewSet, basename='dashboard')

urlpatterns = [
    path('api/', include(router.urls)),
]