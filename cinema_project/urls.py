from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.views import defaults as django_defaults
from django.views.generic import TemplateView
from cinema import views as cinema_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('cinema.urls')),
    path('api/auth/', include('rest_framework.urls')),
    
    # Auth
    path('login/', auth_views.LoginView.as_view(
        template_name='login.html',
        redirect_authenticated_user=True
    ), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='home'), name='logout'),
    path('register/', cinema_views.RegisterView.as_view(), name='register'),
    
    # Frontend routes
    path('', cinema_views.HomeView.as_view(), name='home'),
    path('movie/<int:pk>/', cinema_views.MovieDetailView.as_view(), name='movie_detail'),
    path('film/<int:pk>/', cinema_views.MovieDetailView.as_view(), name='film'),
    path('booking/<int:session_id>/', cinema_views.BookingView.as_view(), name='booking'),
    path('profile/', cinema_views.ProfileView.as_view(), name='profile'),
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
    path('manager/users/', cinema_views.ManagerUsersView.as_view(), name='staff_users'),

    # SEO
    path('robots.txt', cinema_views.robots_txt, name='robots_txt'),
    path('sitemap.xml', cinema_views.sitemap_xml, name='sitemap_xml'),
]

handler404 = django_defaults.page_not_found
handler500 = django_defaults.server_error

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)