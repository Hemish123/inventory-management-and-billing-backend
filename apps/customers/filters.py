import django_filters
from .models import Customer


class CustomerFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(field_name='name', lookup_expr='icontains')
    date_from = django_filters.DateFilter(field_name='created_at', lookup_expr='gte')
    date_to = django_filters.DateFilter(field_name='created_at', lookup_expr='lte')

    class Meta:
        model = Customer
        fields = ['search', 'date_from', 'date_to']
