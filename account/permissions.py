from rest_framework import BasePermission


class IsAdmin(BasePermission):

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_staff)


class IsProUser(BasePermission):
    """
    Allows access only to pro users.
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_pro)
       