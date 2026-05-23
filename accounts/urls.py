from django.urls import path
from . import views
from .views import DashboardHomeView
urlpatterns = [
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('signup/', views.SignupRequestView.as_view(), name='signup'),
    path('signup/success/', views.signup_success_view, name='signup_success'),
    path('logout/', views.CustomLogoutView.as_view(), name='logout'),
    path('dashboard/', DashboardHomeView.as_view(), name='dashboard'),
    path('profile/', views.profile_view, name='profile'),
    path('password/change/', views.CustomPasswordChangeView.as_view(), name='password_change'),
]
