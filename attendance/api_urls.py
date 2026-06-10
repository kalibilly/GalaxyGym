from django.urls import path

from .views import (
    access_sync,
    biometric_endpoint,
    biometric_get_request,
    bridge_entry,
    device_enrollment,
    device_sync_status,
)

urlpatterns = [
    # Root endpoint
    path('', biometric_endpoint, name='biometric_root'),

    # Standard ADMS routes
    path('getrequest', biometric_get_request, name='getrequest'),
    path('getrequest/', biometric_get_request, name='getrequest_slash'),

    path('cdata', biometric_endpoint, name='cdata'),
    path('cdata/', biometric_endpoint, name='cdata_slash'),

    # ASPX compatibility routes
    path('cdata.aspx', biometric_endpoint, name='cdata_aspx'),
    path('getrequest.aspx', biometric_get_request, name='getrequest_aspx'),

    # Existing iclock routes
    path('iclock/getrequest', biometric_get_request, name='iclock_getrequest'),
    path('iclock/getrequest/', biometric_get_request, name='iclock_getrequest_slash'),

    path('iclock/cdata', biometric_endpoint, name='iclock_cdata'),
    path('iclock/cdata/', biometric_endpoint, name='iclock_cdata_slash'),

    # Additional legacy eSSL/ZKTeco routes
    path('iclock/cdata.aspx', biometric_endpoint, name='iclock_cdata_aspx'),
    path('iclock/getrequest.aspx', biometric_get_request, name='iclock_getrequest_aspx'),

    # Some firmware versions generate:
    # /iclock/cdata/iclock/cdata.aspx
    path(
        'iclock/cdata/iclock/cdata.aspx',
        biometric_endpoint,
        name='nested_iclock_cdata_aspx'
    ),

    path(
        'iclock/getrequest/iclock/getrequest.aspx',
        biometric_get_request,
        name='nested_iclock_getrequest_aspx'
    ),

    # SOAP / SDK compatibility
    path('iWsService', biometric_endpoint, name='iwsservice'),
    path('iWsService/', biometric_endpoint, name='iwsservice_slash'),

    # Internal bridge endpoints
    path('bridge/', bridge_entry, name='bridge_entry'),
    path('access-sync/', access_sync, name='access_sync'),
    path('device-sync/status/', device_sync_status, name='device_sync_status'),
    path('device-sync/enroll/', device_enrollment, name='device_enrollment'),
]
