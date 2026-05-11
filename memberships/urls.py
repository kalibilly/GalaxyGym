from django.urls import path

from . import views

app_name = 'memberships'

urlpatterns = [
    path('plans/', views.MembershipPlanListView.as_view(), name='plan_list'),
    path('plans/create/', views.MembershipPlanCreateView.as_view(), name='plan_create'),
    path('plans/<int:pk>/', views.MembershipPlanDetailView.as_view(), name='plan_detail'),
    path('plans/<int:pk>/update/', views.MembershipPlanUpdateView.as_view(), name='plan_update'),

    path('', views.MembershipListView.as_view(), name='list'),
    path('create/', views.MembershipCreateView.as_view(), name='create'),
    path('<int:pk>/', views.MembershipDetailView.as_view(), name='detail'),
    path('<int:pk>/update/', views.MembershipUpdateView.as_view(), name='update'),
]
