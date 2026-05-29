from django.urls import path

from .views import access_sync, biometric_endpoint, bridge_entry

app_name = 'attendance_api'

urlpatterns = [
    path('', biometric_endpoint, name='biometric_root'),
    path('iclock/cdata', biometric_endpoint, name='iclock_cdata'),
    path('cdata', biometric_endpoint, name='cdata'),
    path('iWsService', biometric_endpoint, name='iwsservice'),
    path('bridge/', bridge_entry, name='bridge_entry'),
    path('access-sync/', access_sync, name='access_sync'),
]
