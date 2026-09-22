from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
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
    path('booking/<int:session_id>/', cinema_views.BookingView.as_view(), name='booking'),
    path('profile/', cinema_views.ProfileView.as_view(), name='profile'),
    path('cashier/', cinema_views.CashierView.as_view(), name='cashier'),
    path('controller/', cinema_views.ControllerView.as_view(), name='controller'),
    path('manager/', cinema_views.ManagerView.as_view(), name='manager'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)