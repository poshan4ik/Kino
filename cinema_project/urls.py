from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve as media_serve
from django.contrib.auth import views as auth_views
from django.views import defaults as django_defaults
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.authtoken.views import ObtainAuthToken
from cinema import views as cinema_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('cinema.urls')),
    path('api/auth/', include('rest_framework.urls')),
    path('api/auth/token/', ObtainAuthToken.as_view(), name='api-token'),

    # OpenAPI / Swagger
    path('api/schema/', SpectacularAPIView.as_view(), name='api-schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='api-schema'), name='api-docs'),

    # Health
    path('health/', cinema_views.health, name='health'),

    # Auth
    path('login/', cinema_views.ThrottledLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='home'), name='logout'),
    path('register/', cinema_views.ThrottledRegisterView.as_view(), name='register'),

    # Frontend routes
    path('', cinema_views.HomeView.as_view(), name='home'),
    path('movie/<int:pk>/', cinema_views.MovieDetailView.as_view(), name='movie_detail'),
    path('film/<int:pk>/', cinema_views.MovieDetailView.as_view(), name='film'),
    path('booking/<int:session_id>/', cinema_views.BookingView.as_view(), name='booking'),
    path('pay/<int:booking_id>/', cinema_views.PaymentPageView.as_view(), name='pay_booking'),
    path('pay/gateway/<uuid:external_id>/', cinema_views.PaymentGatewayView.as_view(), name='payment_gateway'),
    path('pay/gateway/<uuid:external_id>/decide/', cinema_views.PaymentGatewayDecideView.as_view(), name='payment_gateway_decide'),
    path('api/webhooks/payment/<str:provider>/', cinema_views.payment_webhook, name='payment_webhook'),
    path('ticket/<int:pk>/', cinema_views.TicketDetailView.as_view(), name='ticket_detail'),
    path('profile/', cinema_views.ProfileView.as_view(), name='profile'),
    path('profile/password/', cinema_views.ProfilePasswordChangeView.as_view(), name='profile_password'),
    path('profile/edit/', cinema_views.ProfileEditView.as_view(), name='profile_edit'),
    path('profile/bookings/<int:booking_id>/cancel/', cinema_views.ProfileCancelBookingView.as_view(), name='profile_cancel_booking'),
    path('cashier/', cinema_views.CashierView.as_view(), name='cashier'),
    path('controller/', cinema_views.ControllerView.as_view(), name='controller'),
    path('manager/', cinema_views.ManagerView.as_view(), name='manager'),
    path('manager/movies/', cinema_views.ManagerMoviesView.as_view(), name='staff_movies'),
    path('manager/sessions/', cinema_views.ManagerSessionsView.as_view(), name='staff_sessions'),
    path('manager/halls/', cinema_views.ManagerHallsView.as_view(), name='staff_halls'),
    path('manager/bookings/', cinema_views.ManagerBookingsView.as_view(), name='staff_bookings'),
    path('manager/tickets/', cinema_views.ManagerTicketsView.as_view(), name='staff_tickets'),
    path('manager/clients/', cinema_views.ManagerClientsView.as_view(), name='staff_clients'),
    path('manager/sales/', cinema_views.ManagerSalesView.as_view(), name='staff_sales'),
    path('manager/reports/', cinema_views.ManagerReportsView.as_view(), name='staff_reports'),
    path('manager/reports/export/', cinema_views.ManagerSalesExportView.as_view(), name='staff_reports_export'),
    path('manager/users/', cinema_views.ManagerUsersView.as_view(), name='staff_users'),

    # SEO
    path('robots.txt', cinema_views.robots_txt, name='robots_txt'),
    path('sitemap.xml', cinema_views.sitemap_xml, name='sitemap_xml'),
]

handler404 = django_defaults.page_not_found
handler500 = django_defaults.server_error

# MEDIA_URL должен отдаваться и при DEBUG=False (static() в prod возвращает []).
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', media_serve, {'document_root': settings.MEDIA_ROOT}),
]
if settings.DEBUG:
    urlpatterns += [re_path(r'^static/(?P<path>.*)$', media_serve, {'document_root': settings.STATIC_ROOT})]