from rest_framework.permissions import BasePermission


class IsOwner(BasePermission):
    """Only allow owners of an object to access it."""

    def has_object_permission(self, request, view, obj):
        if hasattr(obj, 'msme_owner'):
            return obj.msme_owner == request.user
        if hasattr(obj, 'uploaded_by'):
            return obj.uploaded_by == request.user
        if hasattr(obj, 'assigned_by'):
            return obj.assigned_by == request.user
        return False


class IsOwnerOrReadOnly(BasePermission):
    """Allow owners to edit, others to read only."""

    def has_object_permission(self, request, view, obj):
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return True
        if hasattr(obj, 'msme_owner'):
            return obj.msme_owner == request.user
        return False
