from django.urls import path

from . import views

app_name = 'members'

urlpatterns = [
    path('', views.MemberListView.as_view(), name='list'),
    path('create/', views.MemberCreateView.as_view(), name='create'),
    path('<int:pk>/', views.MemberDetailView.as_view(), name='detail'),
    path('<int:pk>/update/', views.MemberUpdateView.as_view(), name='update'),
]
