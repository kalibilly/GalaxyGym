from django.urls import path

from .views import biometric_endpoint

app_name = 'attendance_api'

urlpatterns = [
    path('', biometric_endpoint, name='biometric_root'),
    path('iclock/cdata', biometric_endpoint, name='iclock_cdata'),
    path('cdata', biometric_endpoint, name='cdata'),
    path('iWsService', biometric_endpoint, name='iwsservice'),
]
