from django.urls import path

from . import views

app_name = 'members'

urlpatterns = [
    path('', views.MemberListView.as_view(), name='list'),
    path('create/', views.MemberCreateView.as_view(), name='create'),

    path('delete-requests/', views.MemberDeleteRequestListView.as_view(), name='delete_request_list'),
    path('delete-requests/<int:pk>/', views.MemberDeleteRequestReviewView.as_view(), name='delete_request_review'),

    path('<int:pk>/', views.MemberDetailView.as_view(), name='detail'),
    path('<int:pk>/update/', views.MemberUpdateView.as_view(), name='update'),
    path('<int:pk>/request-delete/', views.MemberDeleteRequestCreateView.as_view(), name='request_delete'),

    path(
        '<int:pk>/biometric/send-to-device/<int:device_pk>/',
        views.MemberSendToDeviceView.as_view(),
        name='send_to_device',
    ),
    path(
        '<int:pk>/biometric/send-to-both-devices/',
        views.MemberSendToBothDevicesView.as_view(),
        name='send_to_both_devices',
    ),
    path(
        '<int:pk>/biometric/check-device-status/<int:device_pk>/',
        views.MemberCheckDeviceStatusView.as_view(),
        name='check_device_status',
    ),
]
