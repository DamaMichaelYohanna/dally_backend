import uuid
from django.utils import timezone
from django.db import models
from django.contrib.auth.models import AbstractUser

from django.contrib.auth.base_user import BaseUserManager

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)



class User(AbstractUser):
    email = models.EmailField(unique=True)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    objects = UserManager()

    def __str__(self):
        return self.email


class PasswordResetOTP(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    otp = models.CharField(max_length=255)
    attempts = models.PositiveIntegerField(default=0)
    reset_jti = models.CharField(max_length=500, blank=True, null=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
    jti_used = models.BooleanField(default=False)

    MAX_ATTEMPTS = 5

    def otp_valid(self):
        return (
            not self.used and
            not self.attempts > self.MAX_ATTEMPTS
            and timezone.now() < self.expires_at
        )
    
    def jwt_valid(self):
        return (
            not self.jti_used and
            not self.attempts > self.MAX_ATTEMPTS
            and timezone.now() < self.expires_at
        )
    
    def __str__(self):
        return f" - OTP for {self.user.id}"
