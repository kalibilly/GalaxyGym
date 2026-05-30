from django.urls import path

from .views import access_sync, biometric_endpoint, biometric_get_request, bridge_entry

app_name = 'attendance_api'

urlpatterns = [
    path('', biometric_endpoint, name='biometric_root'),
    path('getrequest', biometric_get_request, name='getrequest'),
    path('getrequest/', biometric_get_request, name='getrequest_slash'),
    path('iclock/getrequest', biometric_get_request, name='iclock_getrequest'),
    path('iclock/getrequest/', biometric_get_request, name='iclock_getrequest_slash'),
    path('iclock/cdata', biometric_endpoint, name='iclock_cdata'),
    path('iclock/cdata/', biometric_endpoint, name='iclock_cdata_slash'),
    path('cdata', biometric_endpoint, name='cdata'),
    path('cdata/', biometric_endpoint, name='cdata_slash'),
    path('iWsService', biometric_endpoint, name='iwsservice'),
    path('iWsService/', biometric_endpoint, name='iwsservice_slash'),
    path('bridge/', bridge_entry, name='bridge_entry'),
    path('access-sync/', access_sync, name='access_sync'),
]
