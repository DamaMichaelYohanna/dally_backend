from django.urls import path
from .apis import (
    register,
    password_reset_request,
    password_reset_confirm,
    password_reset_verify,
    password_otp_verify,
    change_password,
)

urlpatterns = [
    path('register/', register, name='register'),
    path('password-reset/', password_reset_request, name='password_reset_request'),
    path('password-otp-verify/', password_otp_verify, name='password_otp_verify'),
    path('password-reset-confirm/', password_reset_confirm, name='password_reset_confirm'),
    path('change-password/', change_password, name='change_password'),
]
