from django.urls import path

from . import views

app_name = 'attendance'

urlpatterns = [
    path('', views.AttendanceListView.as_view(), name='attendance_list'),
    path('<int:pk>/', views.AttendanceDetailView.as_view(), name='attendance_detail'),
    path('member/<int:member_pk>/', views.MemberAttendanceHistoryView.as_view(), name='member_history'),
    path('staff/<int:staff_pk>/', views.StaffAttendanceHistoryView.as_view(), name='staff_history'),
]
