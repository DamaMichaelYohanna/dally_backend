from django.urls import path
from . import views

app_name = 'admin_dashboard'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    path('metrics/', views.metrics_json, name='metrics_json'),
    
    # Users management
    path('users/', views.users_list, name='users_list'),
    path('users/<uuid:pk>/', views.user_detail, name='user_detail'),
    path('users/<uuid:pk>/toggle-active/', views.user_toggle_active, name='user_toggle_active'),
    
    # Businesses management
    path('businesses/', views.businesses_list, name='businesses_list'),
    
    # Transactions management
    path('transactions/', views.transactions_list, name='transactions_list'),
    
    # Subscriptions management
    path('subscriptions/', views.subscriptions_list, name='subscriptions_list'),
]
