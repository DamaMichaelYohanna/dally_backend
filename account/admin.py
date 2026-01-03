from django.contrib import admin
from account.models import User, PasswordResetOTP

admin.site.register(User)
admin.site.register(PasswordResetOTP)