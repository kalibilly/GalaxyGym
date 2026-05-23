from django.urls import path
from .views import (
    DashboardHomeView,
    MemberDashboardView,
    StaffDashboardView,
    OwnerDashboardView,
)

urlpatterns = [
    path('', DashboardHomeView.as_view(), name='dashboard'),
    path('member/', MemberDashboardView.as_view(), name='dashboard_member'),
    path('staff/', StaffDashboardView.as_view(), name='dashboard_staff'),
    path('owner/', OwnerDashboardView.as_view(), name='dashboard_owner'),
]
