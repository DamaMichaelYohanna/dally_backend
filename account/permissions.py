from rest_framework import BasePermission


class IsAdmin(BasePermission):

    def has_permission(self, request, ):
        return bool(request.user and request.user.is_staff)
       