from rest_framework import serializers
from .models import Branch, Warehouse


class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = ['id', 'branch', 'name', 'code', 'location_description', 'is_active']
        read_only_fields = ['id']


class BranchSerializer(serializers.ModelSerializer):
    warehouses = WarehouseSerializer(many=True, read_only=True)
    staff_count = serializers.SerializerMethodField()

    class Meta:
        model = Branch
        fields = ['id', 'name', 'code', 'address', 'phone', 'email',
                  'manager_name', 'is_active', 'created_at', 'updated_at',
                  'warehouses', 'staff_count']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_staff_count(self, obj):
        return obj.assigned_employees.count()


class BranchDropdownSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ['id', 'name', 'code']
