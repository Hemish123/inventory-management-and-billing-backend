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
