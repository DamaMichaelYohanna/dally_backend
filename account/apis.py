import logging
from datetime import timedelta
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_decode
from django.utils.timezone import now
from django.utils.encoding import force_str
from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction

import jwt
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiExample

from account.utils import OTPVerifyThrottle, create_or_replace_otp

from .serializers import ChangePasswordSerializer, PasswordOTPVerifySerializer, UserRegistrationSerializer, PasswordResetRequestSerializer, PasswordResetSerializer
from bookkeeping.models import Business
from account.models import PasswordResetOTP, User

# prepare logging handler for this file
logger = logging.getLogger(__name__)

@extend_schema(
    summary="Register new user",
    description="Register a new user account and automatically create their business. Returns user details and JWT tokens.",
    tags=["auth"],
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
                
                # Create business for the user
                business = Business.objects.create(
                    user=user,
                    name=serializer.validated_data['business_name'],
                    description=serializer.validated_data.get('business_description', '')
                )
                
                # Generate JWT tokens
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
                    logger.info(f"Email send to {user.email} successfully!")
                except Exception as e:
                    logger.warning(f"Sending email failed for {user.email}")
                
                logger.info(f"Account for {user.email} has been created successfully")
                return Response({
                    'status': 'success',
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
            logger.error(f"Failed to create user account. error {e}")
            return Response({
                'status': 'error',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    summary="Request password reset",
    description="Request a password reset pin. In development mode, returns the reset URL. In production, sends an email.",
    tags=["auth"],
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
                'status': {'type': 'string'},
                'otp': {'type': 'string', 'description': 'Resent pin'},
            }
        }
    }
)
@api_view(['POST'])
@permission_classes([AllowAny])
def password_reset_request(request):
    """
    Request a password reset email. OTP will be sent
    
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
            otp = create_or_replace_otp(user)
            # Send password reset email
            try:
                send_mail(
                    subject='Password Reset Request - Dally Bookkeeping',
                    message=f'''Hello {user.username},
                    
You have requested to reset your password for your Dally Bookkeeping account.

Here is your six (6) digit pin

{otp}

This pin will expire in 10 mins.

If you did not request this password reset, please ignore this email.

Best regards,
Dally Bookkeeping Team
                    ''',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=False,
                )
                email_sent = True
                logger.info(f"Reset password pin sent to {email}")
            except Exception as e:
                logger.error(f"Could not send email: {e}")
                email_sent = False
            
            # For development/testing, also return the reset link
            if settings.DEBUG:
                return Response({
                    'status': 'Success!',
                    'otp': otp,
                    'email_sent': email_sent,
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    "status": "success",
                    'message': 'If an account exists with this email, a password reset pin has been sent.'
                }, status=status.HTTP_200_OK)
                
        except User.DoesNotExist:
            # Don't reveal that the user doesn't exist
            pass
        
        # Always return success to prevent email enumeration
        return Response({
            "status": "success",
            'message': 'If an account exists with this email, a password reset pin has been sent.'
        }, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



# verify otp
# ---------------------------------
@extend_schema(
    summary="Confirm password reset pin",
    description="Confirm password reset pin sent via email.",
    tags=["auth"],
    request=PasswordOTPVerifySerializer,
    examples=[
        OpenApiExample(
            'Confirm OTP',
            value={
                'otp': '1234',
                'email': "codewithdama@gmail.com"
            },
            request_only=True
        )
    ],
    responses={
        200: {'description': 'Pin verified successful proceed to reset password'},
        400: {'description': 'Invalid reset pin'}
    }
)
@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([OTPVerifyThrottle])
def password_otp_verify(request):
    """
    Confirm password reset pin
    
    POST /api/auth/confirm-otp/
    {
        "otp": "1234",
    }
    """
    serializer = PasswordOTPVerifySerializer(data=request.data)
    
    if serializer.is_valid():
        user_and_token = serializer.save()
        reset_token = jwt.encode(
        {
            "email": user_and_token['user'].email,
            "purpose": "password_reset",
            "jti": user_and_token['jti'],
            "exp": now() + timedelta(minutes=10)
        },
        settings.INTERNAL_JWT_SECRET,
        algorithm="HS256"
    )
        return Response({
            'message': 'success',
            'reset_token': reset_token
        }, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)




@extend_schema(
    summary="Reset password using pin",
    description="Reset password using using jwt token obtained after verifying pin.",
    tags=["auth"],
    request=PasswordResetSerializer,
    examples=[
        OpenApiExample(
            'Password Reset Confirm',
            value={
                'jwt': 'your_jwt_token_here',
                'new_password': "newpassword123",
                'new_password_confirm': "newpassword123"
            },
            request_only=True
        )
    ],
    responses={
        200: {'description': 'Pin verified successful proceed to reset password'},
        400: {'description': 'Invalid token or passwords do not match'}
    }
)
@api_view(['POST'])
@permission_classes([AllowAny])
def password_reset_confirm(request):
    """
    Verify reset paasword pin
    
    POST /api/auth/password-reset-confirm/
    {
        "jwt": "your_jwt_token_here",
        "new_password": "newpassword123",
        "new_password_confirm": "newpassword123"
    }
    """
    serializer = PasswordResetSerializer(data=request.data)
    
    if serializer.is_valid():
        serializer.save()
        return Response({
            'message': 'Password has been reset successfully.'
        }, status=status.HTTP_200_OK)
    
    error_message = None
    if 'non_field_errors' in serializer.errors:
        error_message = ' '.join(serializer.errors['non_field_errors'])
    elif serializer.errors:
        first_key = next(iter(serializer.errors))
        error_message = ' '.join(serializer.errors[first_key])
    else:
        error_message = 'Invalid input.'
    return Response({"status": "error", "message": error_message}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    summary="Change password",
    description="Change password for the authenticated user. Requires old password verification.",
    tags=["auth"],
    request=PasswordResetSerializer,
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
@permission_classes([IsAuthenticated])
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
        serializer.save()
        return Response({
            'message': 'Password changed successfully.'
        }, status=status.HTTP_200_OK)
    
    error_message = None
    if 'non_field_errors' in serializer.errors:
        error_message = ' '.join(serializer.errors['non_field_errors'])
    elif serializer.errors:
        first_key = next(iter(serializer.errors))
        error_message = ' '.join(serializer.errors[first_key])
    else:
        error_message = 'Invalid input.'
    return Response({"status": "error", "message": error_message}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    summary="Verify password reset token",
    description="Check if a password reset token is valid without consuming it.",
    tags=["auth"],
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

