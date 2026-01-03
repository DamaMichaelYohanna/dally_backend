from logging import error
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.hashers import check_password

import jwt
from rest_framework import serializers

from account.models import PasswordResetOTP, User


class UserRegistrationSerializer(serializers.Serializer):
    """
    Serializer for user registration with business creation
    Email will be used as the username
    """
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    
    # Business fields
    business_name = serializers.CharField(max_length=255)
    business_description = serializers.CharField(required=False, allow_blank=True)

    def validate_email(self, value):
        """Validate that email is unique (will be used as username)"""
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already registered.")
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Email already registered.")
        return value

    def validate(self, data):
        """Validate that passwords match"""
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({"password": "Passwords do not match."})
        return data


class PasswordResetRequestSerializer(serializers.Serializer):
    """
    Serializer for requesting a password reset
    """
    email = serializers.EmailField()

    def validate_email(self, value):
        """
        Validate that the email exists in the system
        """
        if not User.objects.filter(email=value).exists():
            # Don't reveal that the email doesn't exist for security
            # Just silently accept it
            pass
        return value


class PasswordOTPSendSerializer(serializers.Serializer):
    """
    Serializer for confirming a password reset
    """
    otp = serializers.CharField()
    email = serializers.EmailField(write_only=True, min_length=8)

    def validate(self, data):
        """
        Validate that pin is correct and active
        """
        try:
           email = data['email']
           otp = PasswordResetOTP.objects.filter(user__email=email).first()
           if otp.is_valid():
               return data
           else: raise ValueError
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError("Invalid reset pin.")


class PasswordOTPVerifySerializer(serializers.Serializer):
    """
    Serializer for verifying OTP during password reset
    """
    otp = serializers.CharField()
    email = serializers.EmailField(write_only=True)

    def validate(self, data):
        email = data["email"]
        otp = data["otp"]

        try:
            user = User.objects.get(email=email)
            record = PasswordResetOTP.objects.get(user=user)
        except (User.DoesNotExist, PasswordResetOTP.DoesNotExist):
            raise serializers.ValidationError("Invalid reset pin.")

        if not record.is_valid():
            raise serializers.ValidationError("OTP expired or already used.")

        if not check_password(str(otp), record.otp_hash):
            record.attempts += 1
            record.save(update_fields=["attempts"])
            raise serializers.ValidationError("Invalid reset pin.")

        # Mark OTP as used
        record.used = True
        record.save(update_fields=["used"])

        return {
            "user": user
        }

class ChangePasswordSerializer(serializers.Serializer):
    """
    Serializer for changing password while authenticated
    """
    jwt = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    new_password_confirm = serializers.CharField(write_only=True, min_length=8)

    def validate(self, data):
        """
        Validate that passwords match
        """

        token = data.get('jwt')
        try:
            payload = jwt.decode(
                token,
                settings.INTERNAL_JWT_SECRET,
                algorithms=["HS256"]
            )
        except:
            raise serializers.ValidationError("Something went wrong. Please try again.")
        
        if payload.get("purpose") != "password_reset":
            raise serializers.ValidationError("Something went wrong. Please try again.")
        
        if data['new_password'] != data['new_password_confirm']:
            raise serializers.ValidationError("New passwords do not match.")
        
        try:
            user = User.objects.get(email=payload.get("email"))
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid reset token.")
          # Django password validators
        validate_password(data["new_password"], user=user)

        self.user = user
        self.payload = payload
        return data

    def save(self):
        self.user.set_password(self.validated_data["new_password"])
        self.user.save(update_fields=["password"])
        return self.user

