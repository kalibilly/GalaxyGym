from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('dashboard/', include('core.urls')),
    path('departments/', include('departments.urls')),
    path('staffs/', include('staffs.urls')),
    path('members/', include('members.urls')),
    path('memberships/', include('memberships.urls')),
    path('payments/', include('payments.urls')),
    path('attendance/', include('attendance.urls')),
    path('notifications/', include('notifications.urls')),
    path('', lambda request: __import__('django.shortcuts', fromlist=['redirect']).redirect('dashboard')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
