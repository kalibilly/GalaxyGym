from django.urls import path

from . import views


app_name = 'attendance'


urlpatterns = [
    path('', views.AttendanceListView.as_view(), name='attendance_list'),
    path('<int:pk>/', views.AttendanceDetailView.as_view(), name='attendance_detail'),
    path('create/', views.AttendanceCreateView.as_view(), name='attendance_create'),
    path('<int:pk>/update/', views.AttendanceUpdateView.as_view(), name='attendance_update'),

    path('member/<int:member_pk>/', views.MemberAttendanceHistoryView.as_view(), name='member_history'),
    path('staff/<int:staff_pk>/', views.StaffAttendanceHistoryView.as_view(), name='staff_history'),

    path('device/sync-status/', views.device_sync_status, name='device_sync_status'),
    path('device/enrollment/', views.device_enrollment, name='device_enrollment'),
    path('device/bridge-entry/', views.bridge_entry, name='bridge_entry'),
    path('device/access-sync/', views.access_sync, name='access_sync'),

    path('biometric/get-request/', views.biometric_get_request, name='biometric_get_request'),
    path('biometric/endpoint/', views.biometric_endpoint, name='biometric_endpoint'),
]
