from django.urls import path

from . import views

app_name = 'members'

urlpatterns = [
    path('', views.MemberListView.as_view(), name='list'),
    path('create/', views.MemberCreateView.as_view(), name='create'),
    path('<int:pk>/request-delete/', views.MemberDeleteRequestCreateView.as_view(), name='request_delete'),
    path('delete-requests/', views.MemberDeleteRequestListView.as_view(), name='delete_request_list'),
    path('delete-requests/<int:pk>/', views.MemberDeleteRequestReviewView.as_view(), name='delete_request_review'),
    path('<int:pk>/', views.MemberDetailView.as_view(), name='detail'),
    path('<int:pk>/update/', views.MemberUpdateView.as_view(), name='update'),
]
