from django.urls import path

from . import views

app_name = 'memberships'

urlpatterns = [
    path('plans/', views.MembershipPlanListView.as_view(), name='plan_list'),
    path('plans/create/', views.MembershipPlanCreateView.as_view(), name='plan_create'),
    path('plans/<int:pk>/', views.MembershipPlanDetailView.as_view(), name='plan_detail'),
    path('plans/catalog/', views.MembershipPlanCatalogView.as_view(), name='plan_catalog'),
    path('plans/<int:pk>/purchase/', views.MembershipPurchaseView.as_view(), name='plan_purchase'),
    path('plans/purchase-success/<int:invoice_pk>/', views.MembershipPurchaseSuccessView.as_view(), name='purchase_success'),
    path('plans/<int:pk>/update/', views.MembershipPlanUpdateView.as_view(), name='plan_update'),

    path('', views.MembershipListView.as_view(), name='list'),
    path('create/', views.MembershipCreateView.as_view(), name='create'),
    path('<int:pk>/', views.MembershipDetailView.as_view(), name='detail'),
    path('<int:pk>/update/', views.MembershipUpdateView.as_view(), name='update'),
]
