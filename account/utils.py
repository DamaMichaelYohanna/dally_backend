import random 
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth.hashers import make_password
from rest_framework.throttling import AnonRateThrottle


from account.models import PasswordResetOTP

def create_or_replace_otp(user):
    otp = random.randint(100000, 999999)
    expires_at = timezone.now() + timedelta(minutes=10)

    PasswordResetOTP.objects.update_or_create(
        user=user,
        defaults={
            "otp": str(otp),
            "attempts": 0,
            "used": False,
            "expires_at": expires_at,
        }
    )
    return otp


class OTPVerifyThrottle(AnonRateThrottle):
    rate = "3/min"
