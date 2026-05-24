from django.urls import path
from .views import (
    DashboardHomeView,
    StaffDashboardView,
    OwnerDashboardView,
)

urlpatterns = [
    path('', DashboardHomeView.as_view(), name='dashboard'),
    path('staff/', StaffDashboardView.as_view(), name='dashboard_staff'),
    path('owner/', OwnerDashboardView.as_view(), name='dashboard_owner'),
]
