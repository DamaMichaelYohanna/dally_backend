from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from .apis import (
    register,
    password_reset_request,
    password_reset_confirm,
    password_otp_verify,
    change_password,
    subscription_status,
    initialize_subscription,
    paystack_webhook,
    profile_view,
    list_plans,
)

urlpatterns = [
    path('register/', register, name='register'),
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('password-reset/', password_reset_request, name='password_reset_request'),
    path('password-otp-verify/', password_otp_verify, name='password_otp_verify'),
    path('password-reset-confirm/', password_reset_confirm, name='password_reset_confirm'),
    path('change-password/', change_password, name='change_password'),
    path('plans/', list_plans, name='list_plans'),
    path('subscription/status/', subscription_status, name='subscription_status'),
    path('subscription/initialize/', initialize_subscription, name='initialize_subscription'),
    path('paystack/webhook/', paystack_webhook, name='paystack_webhook'),
    path('profile/', profile_view, name='profile'),
]
