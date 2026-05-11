from django.urls import path

from . import views

app_name = 'staffs'

urlpatterns = [
    path('', views.StaffListView.as_view(), name='list'),
    path('create/', views.StaffCreateView.as_view(), name='create'),
    path('<int:pk>/', views.StaffDetailView.as_view(), name='detail'),
    path('<int:pk>/update/', views.StaffUpdateView.as_view(), name='update'),
]
