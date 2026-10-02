import django_filters
from django.db.models import Q
from .models import Customer


class CustomerFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method='filter_search')
    date_from = django_filters.DateFilter(field_name='created_at', lookup_expr='gte')
    date_to = django_filters.DateFilter(field_name='created_at', lookup_expr='lte')
    phone = django_filters.CharFilter(field_name='phone', lookup_expr='icontains')

    class Meta:
        model = Customer
        fields = ['search', 'date_from', 'date_to', 'phone']

    def filter_search(self, queryset, name, value):
        """Search by name, email, GSTIN, or phone number."""
        return queryset.filter(
            Q(name__icontains=value) |
            Q(email__icontains=value) |
            Q(gstin__icontains=value) |
            Q(phone__icontains=value)
        )
