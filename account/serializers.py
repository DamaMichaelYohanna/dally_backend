from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
import uuid
import jwt
from rest_framework import serializers

from account.models import PasswordResetOTP, User


# model serializers for users
class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for User model
    """
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']
        read_only_fields = ['id']


# user registration serializer
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


# password reset request serializer
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


# password reset OTP verification serializer
class PasswordOTPVerifySerializer(serializers.Serializer):
    otp = serializers.CharField()
    email = serializers.EmailField(write_only=True)

    def validate(self, data):
        email = data["email"]
        otp = data["otp"]

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid reset pin.")

        try:
            record = PasswordResetOTP.objects.get(user=user)
        except PasswordResetOTP.DoesNotExist:
            raise serializers.ValidationError("Invalid reset pin.")

        # Pure validation only
        if not record.otp_valid():
            raise serializers.ValidationError("OTP expired or already used.")

        if not str(otp) == record.otp:
            record.attempts += 1
            record.save(update_fields=["attempts"])
            raise serializers.ValidationError("Invalid reset pin.")

        # Store for save()
        self.user = user
        self.record_id = record.id

        return data

    def save(self):
        """
        Burn OTP and mint exactly one JTI (atomic & race-safe)
        """
        with transaction.atomic():
            record = (
                PasswordResetOTP.objects
                .select_for_update()
                .get(pk=self.record_id)
            )

            if record.used:
                raise serializers.ValidationError("OTP already used.")

            jti = uuid.uuid4().hex

            record.used = True
            record.reset_jti = jti
            record.save(update_fields=["used", "reset_jti"])

        return {
            "user": self.user,
            "jti": jti,
        }


# password reset serializer
class PasswordResetSerializer(serializers.Serializer):
    jwt = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    new_password_confirm = serializers.CharField(write_only=True, min_length=8)

    def validate(self, data):
        token = data["jwt"]

        try:
            payload = jwt.decode(
                token,
                settings.INTERNAL_JWT_SECRET,
                algorithms=["HS256"],
            )
        except jwt.ExpiredSignatureError:
            raise serializers.ValidationError("Reset token expired.")
        except jwt.InvalidTokenError:
            raise serializers.ValidationError("Invalid reset token.")

        if payload.get("purpose") != "password_reset":
            raise serializers.ValidationError("Invalid reset token.")

        if data["new_password"] != data["new_password_confirm"]:
            raise serializers.ValidationError("New passwords do not match.")

        try:
            otp_record = PasswordResetOTP.objects.get(
                reset_jti=payload.get("jti")
            )
        except PasswordResetOTP.DoesNotExist:
            raise serializers.ValidationError("Invalid or expired reset token.")

        validate_password(data["new_password"], user=otp_record.user)

        self.otp_record = otp_record
        self.user = otp_record.user
        return data

    def save(self):
        with transaction.atomic():
            otp_record = (
                PasswordResetOTP.objects
                .select_for_update()
                .get(pk=self.otp_record.pk)
            )

            # 🔐 burn the token
            otp_record.reset_jti = None
            otp_record.jti_used = True
            otp_record.save(update_fields=["reset_jti", "jti_used"])

            self.user.set_password(self.validated_data["new_password"])
            self.user.save(update_fields=["password"])

        return self.user
    

# change password serializer
class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    new_password_confirm = serializers.CharField(write_only=True, min_length=8)

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value

    def validate(self, data):
        if data["new_password"] != data["new_password_confirm"]:
            raise serializers.ValidationError("New passwords do not match.")
        validate_password(data["new_password"], user=self.context['request'].user)
        return data

    def save(self):
        user = self.context['request'].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user