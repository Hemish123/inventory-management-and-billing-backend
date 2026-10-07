from apps.core.mixins import TenantMixin
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from utils.response import api_response, api_error
from .models import Customer
from .serializers import CustomerSerializer, CustomerListSerializer, CustomerDropdownSerializer
from .filters import CustomerFilter


class CustomerViewSet(TenantMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Customer.objects.all()
    filterset_class = CustomerFilter
    search_fields = ['name', 'company_name', 'email', 'gstin', 'phone']
    ordering_fields = ['name', 'created_at', 'updated_at']

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.role_name == 'EMPLOYEE':
            qs = qs.filter(created_by=self.request.user)
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return CustomerListSerializer
        return CustomerSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            self.perform_create(serializer)
            return api_response(
                data=serializer.data,
                message='Customer created successfully',
                status_code=status.HTTP_201_CREATED
            )
        return api_error(errors=serializer.errors)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return api_response(data=serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = CustomerSerializer(instance)
        return api_response(data=serializer.data)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = CustomerSerializer(instance, data=request.data, partial=True)
        if serializer.is_valid():
            self.perform_update(serializer)
            return api_response(data=serializer.data, message='Customer updated')
        return api_error(errors=serializer.errors)



    @action(detail=False, methods=['get'], url_path='dropdown')
    def dropdown(self, request):
        """Lightweight list for billing customer dropdowns — no pagination."""
        qs = Customer.objects.filter(company=request.user.company, is_active=True)
        if request.user.role_name == 'EMPLOYEE':
            qs = qs.filter(created_by=request.user)
            
        customers = qs.order_by('name')
        serializer = CustomerDropdownSerializer(customers, many=True)
        return api_response(data=serializer.data)

    @action(detail=True, methods=['get'], url_path='profile')
    def profile(self, request, pk=None):
        """Customer profile: details + purchase history + stats."""
        from apps.billing.models import Bill
        from django.db.models import Sum, Count, Max

        customer = self.get_object()
        bills = Bill.objects.filter(
            customer=customer, status='COMPLETED'
        ).order_by('-billing_date')

        stats = bills.aggregate(
            total_purchases=Count('id'),
            total_amount=Sum('grand_total'),
            last_purchase=Max('billing_date'),
        )

        recent_bills = bills[:20].values(
            'id', 'bill_number', 'billing_date', 'grand_total',
            'payment_method', 'status'
        )

        data = {
            'customer': CustomerSerializer(customer).data,
            'stats': {
                'total_purchases': stats['total_purchases'] or 0,
                'total_amount': float(stats['total_amount'] or 0),
                'last_purchase': stats['last_purchase'],
            },
            'recent_bills': list(recent_bills),
        }
        return api_response(data=data)

