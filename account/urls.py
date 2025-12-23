from django.urls import path
from .views import (
    register,
    password_reset_request,
    password_reset_confirm,
    password_reset_verify,
    change_password,
)

urlpatterns = [
    path('register/', register, name='register'),
    path('password-reset/', password_reset_request, name='password_reset_request'),
    path('password-reset-confirm/', password_reset_confirm, name='password_reset_confirm'),
    path('password-reset-verify/<str:uid>/<str:token>/', password_reset_verify, name='password_reset_verify'),
    path('change-password/', change_password, name='change_password'),
]
