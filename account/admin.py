from django.contrib import admin
from account.models import User, PasswordResetOTP
from account.models import Subscription, SubscriptionPlan

admin.site.register(User)
admin.site.register(PasswordResetOTP)
admin.site.register(Subscription)
admin.site.register(SubscriptionPlan)