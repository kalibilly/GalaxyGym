from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from core.views import HomeView

urlpatterns = [
    path('admin/', admin.site.urls),

    # Existing attendance API
    path('api/attendance/', include(('attendance.api_urls', 'attendance_api'), namespace='attendance_api')),

    # Additional routes for eSSL/ZKTeco ADMS compatibility
    path('iclock/', include('attendance.api_urls')),

    path('accounts/', include('accounts.urls')),
    path('dashboard/', include('core.urls')),
    path('departments/', include('departments.urls')),
    path('staffs/', include('staffs.urls')),
    path('members/', include('members.urls')),
    path('memberships/', include('memberships.urls')),
    path('payments/', include('payments.urls')),
    path('attendance/', include('attendance.urls')),
    path('notifications/', include('notifications.urls')),

    path('', HomeView.as_view(), name='home'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
