from apps.core.mixins import TenantMixin
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page

from utils.response import api_response, api_error
from .models import Branch, Warehouse
from .serializers import BranchSerializer, BranchDropdownSerializer, WarehouseSerializer


class BranchViewSet(TenantMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = BranchSerializer
    queryset = Branch.objects.filter(is_active=True)
    search_fields = ['name', 'code']

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            self.perform_create(serializer)
            return api_response(data=serializer.data, message='Branch created',
                                status_code=status.HTTP_201_CREATED)
        return api_error(errors=serializer.errors)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return api_response(data=serializer.data)

    @action(detail=False, methods=['get'], url_path='dropdown')
    def dropdown(self, request):
        branches = self.get_queryset().order_by('name')
        serializer = BranchDropdownSerializer(branches, many=True)
        return api_response(data=serializer.data)


class WarehouseViewSet(TenantMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = WarehouseSerializer
    search_fields = ['name', 'code']

    def get_queryset(self):
        qs = Warehouse.objects.filter(is_active=True)
        branch_id = self.request.query_params.get('branch')
        if branch_id:
            qs = qs.filter(branch_id=branch_id)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            self.perform_create(serializer)
            return api_response(data=serializer.data, message='Warehouse created',
                                status_code=status.HTTP_201_CREATED)
        return api_error(errors=serializer.errors)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return api_response(data=serializer.data)
