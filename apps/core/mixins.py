from django.db.models import ProtectedError
from utils.response import api_response


class TenantMixin:
    """
    Mixin for DRF ViewSets to automatically filter querysets by the user's company
    and inject the user's company on creation.
    """
    def get_queryset(self):
        """Filter the queryset by the logged-in user's company."""
        qs = super().get_queryset()
        user = self.request.user
        
        if hasattr(user, 'company') and user.company:
            return qs.filter(company=user.company)
            
        # If the user has no company, return nothing.
        return qs.none()

    def perform_create(self, serializer):
        """Automatically set the company on creation."""
        user = self.request.user
        if hasattr(user, 'company') and user.company:
            serializer.save(company=user.company)
        else:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'detail': 'User is not associated with any company.'})

    def perform_destroy(self, instance):
        """
        Try hard delete first. If it fails due to protected foreign keys,
        fall back to soft delete (is_active = False) if the model supports it.
        """
        try:
            instance.delete()
        except ProtectedError:
            if hasattr(instance, 'is_active'):
                instance.is_active = False
                instance.save(update_fields=['is_active'])
            else:
                raise

    def destroy(self, request, *args, **kwargs):
        """Override destroy to return a consistent API response."""
        instance = self.get_object()
        self.perform_destroy(instance)
        return api_response(message='Deleted successfully')

