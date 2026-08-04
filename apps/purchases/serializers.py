from rest_framework import serializers
from .models import Purchase, PurchaseItem


class PurchaseItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = PurchaseItem
        fields = ['id', 'product', 'product_name', 'quantity',
                  'unit_cost', 'received_quantity', 'line_total']
        read_only_fields = ['id', 'line_total']


class PurchaseSerializer(serializers.ModelSerializer):
    items = PurchaseItemSerializer(many=True, read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)

    class Meta:
        model = Purchase
        fields = ['id', 'po_number', 'branch', 'branch_name', 'supplier',
                  'supplier_name', 'purchase_date', 'expected_delivery',
                  'invoice_number', 'status', 'notes', 'total_amount',
                  'gst_percentage', 'gst_amount',
                  'created_by', 'created_at', 'updated_at', 'items']
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']


class PurchaseListSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)

    class Meta:
        model = Purchase
        fields = ['id', 'po_number', 'branch_name', 'supplier_name',
                  'purchase_date', 'invoice_number', 'status', 'total_amount',
                  'gst_amount']
