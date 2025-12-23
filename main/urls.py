from django.urls import path
from . import views

app_name = 'main'

urlpatterns = [
    path('', views.home, name='home'),
    path('pricing/', views.pricing, name='pricing'),
    path('privacy/', views.privacy, name='privacy'),
    path('terms/', views.terms, name='terms'),
    path('waitlist/', views.waitlist_signup, name='waitlist_signup'),
]
