from rest_framework import permissions


class IsOwner(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to access it.
    Ensures users can only access their own data.
    """
    
    def has_object_permission(self, request, view, obj):
        """
        Check if the object belongs to the requesting user
        """
        # Check if object has a user field
        if hasattr(obj, 'user'):
            return obj.user == request.user
        
        # For TransactionItem, check through transaction
        if hasattr(obj, 'transaction'):
            return obj.transaction.user == request.user
        
        return False


class IsBusinessOwner(permissions.BasePermission):
    """
    Permission to ensure user can only access their own business
    """
    
    def has_object_permission(self, request, view, obj):
        """
        Business must belong to the requesting user
        """
        return obj.user == request.user
