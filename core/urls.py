from django.urls import path
from .views import DashboardHomeView

app_name = 'core'

urlpatterns = [
    path('', DashboardHomeView.as_view(), name='dashboard'),
]
