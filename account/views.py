from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiExample


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


class PasswordResetConfirmSerializer(serializers.Serializer):
    """
    Serializer for confirming a password reset
    """
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)
    new_password_confirm = serializers.CharField(write_only=True)

    def validate(self, data):
        """
        Validate that passwords match and token is valid
        """
        if data['new_password'] != data['new_password_confirm']:
            raise serializers.ValidationError("Passwords do not match.")
        
        # Validate token
        try:
            uid = force_str(urlsafe_base64_decode(data['uid']))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError("Invalid reset link.")
        
        if not default_token_generator.check_token(user, data['token']):
            raise serializers.ValidationError("Invalid or expired reset link.")
        
        data['user'] = user
        return data


class ChangePasswordSerializer(serializers.Serializer):
    """
    Serializer for changing password while authenticated
    """
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    new_password_confirm = serializers.CharField(write_only=True)

    def validate(self, data):
        """
        Validate that passwords match
        """
        if data['new_password'] != data['new_password_confirm']:
            raise serializers.ValidationError("New passwords do not match.")
        return data

    def validate_old_password(self, value):
        """
        Validate that the old password is correct
        """
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value


@extend_schema(
    summary="Register new user",
    description="Register a new user account and automatically create their business. Returns user details and JWT tokens.",
    tags=["Authentication"],
    request=UserRegistrationSerializer,
    examples=[
        OpenApiExample(
            'User Registration',
            value={
                'email': 'john@example.com',
                'password': 'SecurePass123',
                'password_confirm': 'SecurePass123',
                'first_name': 'John',
                'last_name': 'Doe',
                'business_name': 'John\'s Trading',
                'business_description': 'Import and export business'
            },
            request_only=True
        )
    ],
    responses={
        201: {
            'type': 'object',
            'properties': {
                'message': {'type': 'string'},
                'user': {
                    'type': 'object',
                    'properties': {
                        'id': {'type': 'integer'},
                        'username': {'type': 'string'},
                        'email': {'type': 'string'},
                        'first_name': {'type': 'string'},
                        'last_name': {'type': 'string'}
                    }
                },
                'business': {
                    'type': 'object',
                    'properties': {
                        'id': {'type': 'string'},
                        'name': {'type': 'string'},
                        'description': {'type': 'string'}
                    }
                },
                'tokens': {
                    'type': 'object',
                    'properties': {
                        'access': {'type': 'string'},
                        'refresh': {'type': 'string'}
                    }
                }
            }
        },
        400: {'description': 'Validation error'}
    }
)
@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    """
    Register a new user and create their business
    
    POST /api/auth/register/
    {
        "email": "john@example.com",
        "password": "SecurePass123",
        "password_confirm": "SecurePass123",
        "first_name": "John",
        "last_name": "Doe",
        "business_name": "John's Trading",
        "business_description": "Import and export business"
    }
    """
    serializer = UserRegistrationSerializer(data=request.data)
    
    if serializer.is_valid():
        try:
            # Use transaction to ensure both user and business are created together
            with transaction.atomic():
                # Create user (use email as username)
                user = User.objects.create_user(
                    username=serializer.validated_data['email'],
                    email=serializer.validated_data['email'],
                    password=serializer.validated_data['password'],
                    first_name=serializer.validated_data.get('first_name', ''),
                    last_name=serializer.validated_data.get('last_name', '')
                )
                
                # Import Business model
                from bookkeeping.models import Business
                
                # Create business for the user
                business = Business.objects.create(
                    user=user,
                    name=serializer.validated_data['business_name'],
                    description=serializer.validated_data.get('business_description', '')
                )
                
                # Generate JWT tokens
                from rest_framework_simplejwt.tokens import RefreshToken
                refresh = RefreshToken.for_user(user)
                
                # Send welcome email (optional)
                try:
                    send_mail(
                        subject='Welcome to Dally Bookkeeping!',
                        message=f'''Hello {user.first_name or 'there'},

Welcome to Dally Bookkeeping! Your account has been successfully created.

Business: {business.name}
Email: {user.email}

You can now log in using your email address and start managing your bookkeeping records.

Best regards,
Dally Bookkeeping Team
''',
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[user.email],
                        fail_silently=True,
                    )
                except Exception as e:
                    # Don't fail registration if email fails
                    print(f"Failed to send welcome email: {e}")
                
                return Response({
                    'message': 'User registered successfully.',
                    'user': {
                        'id': user.id,
                        'username': user.username,
                        'email': user.email,
                        'first_name': user.first_name,
                        'last_name': user.last_name
                    },
                    'business': {
                        'id': str(business.id),
                        'name': business.name,
                        'description': business.description
                    },
                    'tokens': {
                        'access': str(refresh.access_token),
                        'refresh': str(refresh)
                    }
                }, status=status.HTTP_201_CREATED)
                
        except Exception as e:
            return Response({
                'error': 'Registration failed. Please try again.',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    summary="Request password reset",
    description="Request a password reset link. In development mode, returns the reset URL. In production, sends an email.",
    tags=["Authentication"],
    request=PasswordResetRequestSerializer,
    examples=[
        OpenApiExample(
            'Password Reset Request',
            value={'email': 'user@example.com'},
            request_only=True
        )
    ],
    responses={
        200: {
            'type': 'object',
            'properties': {
                'message': {'type': 'string'},
                'reset_url': {'type': 'string', 'description': 'Only in DEBUG mode'},
                'uid': {'type': 'string', 'description': 'Only in DEBUG mode'},
                'token': {'type': 'string', 'description': 'Only in DEBUG mode'}
            }
        }
    }
)
@api_view(['POST'])
@permission_classes([AllowAny])
def password_reset_request(request):
    """
    Request a password reset email
    
    POST /api/auth/password-reset/
    {
        "email": "user@example.com"
    }
    """
    serializer = PasswordResetRequestSerializer(data=request.data)
    
    if serializer.is_valid():
        email = serializer.validated_data['email']
        
        # Get user by email
        try:
            user = User.objects.get(email=email)
            
            # Generate password reset token
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            
            # Build reset URL (frontend URL in production)
            reset_url = f"{request.scheme}://{request.get_host()}/api/auth/password-reset-verify/{uid}/{token}/"
            
            # Send password reset email
            try:
                send_mail(
                    subject='Password Reset Request - Dally Bookkeeping',
                    message=f'''Hello {user.username},

You have requested to reset your password for your Dally Bookkeeping account.

Click the link below to reset your password:
{reset_url}

This link will expire in 24 hours.

If you did not request this password reset, please ignore this email.

Best regards,
Dally Bookkeeping Team
''',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=False,
                )
                email_sent = True
            except Exception as e:
                # Log the error but don't reveal it to the user
                print(f"Failed to send email: {e}")
                email_sent = False
            
            # For development/testing, also return the reset link
            if settings.DEBUG:
                return Response({
                    'message': 'Password reset link generated.',
                    'reset_url': reset_url,
                    'uid': uid,
                    'token': token,
                    'email_sent': email_sent,
                    'note': 'Check your email for the reset link.' if email_sent else 'Email sending failed. Use the reset_url above.'
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'message': 'If an account exists with this email, a password reset link has been sent.'
                }, status=status.HTTP_200_OK)
                
        except User.DoesNotExist:
            # Don't reveal that the user doesn't exist
            pass
        
        # Always return success to prevent email enumeration
        return Response({
            'message': 'If an account exists with this email, a password reset link has been sent.'
        }, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    summary="Confirm password reset",
    description="Reset password using the token received via email.",
    tags=["Authentication"],
    request=PasswordResetConfirmSerializer,
    examples=[
        OpenApiExample(
            'Password Reset Confirm',
            value={
                'uid': 'MQ',
                'token': 'abc123-token',
                'new_password': 'newSecurePassword123',
                'new_password_confirm': 'newSecurePassword123'
            },
            request_only=True
        )
    ],
    responses={
        200: {'description': 'Password reset successful'},
        400: {'description': 'Invalid token or passwords do not match'}
    }
)
@api_view(['POST'])
@permission_classes([AllowAny])
def password_reset_confirm(request):
    """
    Confirm password reset with token
    
    POST /api/auth/password-reset-confirm/
    {
        "uid": "MQ",
        "token": "abcdef-123456",
        "new_password": "newpassword123",
        "new_password_confirm": "newpassword123"
    }
    """
    serializer = PasswordResetConfirmSerializer(data=request.data)
    
    if serializer.is_valid():
        user = serializer.validated_data['user']
        new_password = serializer.validated_data['new_password']
        
        # Set new password
        user.set_password(new_password)
        user.save()
        
        return Response({
            'message': 'Password has been reset successfully.'
        }, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    summary="Change password",
    description="Change password for the authenticated user. Requires old password verification.",
    tags=["Authentication"],
    request=ChangePasswordSerializer,
    examples=[
        OpenApiExample(
            'Change Password',
            value={
                'old_password': 'currentPassword',
                'new_password': 'newSecurePassword123',
                'new_password_confirm': 'newSecurePassword123'
            },
            request_only=True
        )
    ],
    responses={
        200: {'description': 'Password changed successfully'},
        400: {'description': 'Invalid old password or passwords do not match'},
        401: {'description': 'Authentication required'}
    }
)
@api_view(['POST'])
def change_password(request):
    """
    Change password for authenticated user
    
    POST /api/auth/change-password/
    {
        "old_password": "oldpassword",
        "new_password": "newpassword123",
        "new_password_confirm": "newpassword123"
    }
    
    Requires authentication.
    """
    serializer = ChangePasswordSerializer(
        data=request.data,
        context={'request': request}
    )
    
    if serializer.is_valid():
        # Set new password
        user = request.user
        new_password = serializer.validated_data['new_password']
        user.set_password(new_password)
        user.save()
        
        return Response({
            'message': 'Password changed successfully.'
        }, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    summary="Verify password reset token",
    description="Check if a password reset token is valid without consuming it.",
    tags=["Authentication"],
    responses={
        200: {
            'type': 'object',
            'properties': {
                'valid': {'type': 'boolean'},
                'message': {'type': 'string'}
            }
        },
        400: {
            'type': 'object',
            'properties': {
                'valid': {'type': 'boolean'},
                'message': {'type': 'string'}
            }
        }
    }
)
@api_view(['GET'])
@permission_classes([AllowAny])
def password_reset_verify(request, uid, token):
    """
    Verify if a password reset token is valid
    
    GET /api/auth/password-reset-verify/{uid}/{token}/
    
    Returns whether the token is valid without consuming it
    """
    try:
        uid_decoded = force_str(urlsafe_base64_decode(uid))
        user = User.objects.get(pk=uid_decoded)
        
        if default_token_generator.check_token(user, token):
            return Response({
                'valid': True,
                'message': 'Token is valid.'
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'valid': False,
                'message': 'Token is invalid or expired.'
            }, status=status.HTTP_400_BAD_REQUEST)
            
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return Response({
            'valid': False,
            'message': 'Invalid reset link.'
        }, status=status.HTTP_400_BAD_REQUEST)

