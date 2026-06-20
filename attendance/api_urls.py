from django.urls import path

from .views import (
    access_sync,
    biometric_device_cdata,
    biometric_endpoint,
    biometric_get_request,
    bridge_entry,
    device_enrollment,
    device_sync_status,
    ebioserver_webhook,
)

urlpatterns = [
    path("", biometric_endpoint, name="biometric_root"),

    path("getrequest", biometric_get_request, name="getrequest"),
    path("getrequest/", biometric_get_request, name="getrequest_slash"),

    path("cdata", biometric_device_cdata, name="cdata"),
    path("cdata/", biometric_device_cdata, name="cdata_slash"),

    path("cdata.aspx", biometric_device_cdata, name="cdata_aspx"),
    path("getrequest.aspx", biometric_get_request, name="getrequest_aspx"),

    path("iclock/getrequest", biometric_get_request, name="iclock_getrequest"),
    path("iclock/getrequest/", biometric_get_request, name="iclock_getrequest_slash"),

    path("iclock/cdata", biometric_device_cdata, name="iclock_cdata"),
    path("iclock/cdata/", biometric_device_cdata, name="iclock_cdata_slash"),

    path("iclock/cdata.aspx", biometric_device_cdata, name="iclock_cdata_aspx"),
    path("iclock/getrequest.aspx", biometric_get_request, name="iclock_getrequest_aspx"),

    path(
        "iclock/cdata/iclock/cdata.aspx",
        biometric_device_cdata,
        name="nested_iclock_cdata_aspx",
    ),
    path(
        "iclock/getrequest/iclock/getrequest.aspx",
        biometric_get_request,
        name="nested_iclock_getrequest_aspx",
    ),

    path("iWsService", biometric_endpoint, name="iwsservice"),
    path("iWsService/", biometric_endpoint, name="iwsservice_slash"),

    path("bridge/", bridge_entry, name="bridge_entry"),
    path("access-sync/", access_sync, name="access_sync"),
    path("device-sync/status/", device_sync_status, name="device_sync_status"),
    path("device-sync/enroll/", device_enrollment, name="device_enrollment"),

    path("ebioserver/", ebioserver_webhook, name="ebioserver_webhook"),
    path("ebioserver", ebioserver_webhook, name="ebioserver_webhook_noslash"),
]
