from rest_framework import serializers
from .models import StockMovement, StockTransfer, StockTransferItem


class StockMovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.email', read_only=True, default='')

    class Meta:
        model = StockMovement
        fields = ['id', 'product', 'product_name', 'branch', 'branch_name',
                  'warehouse', 'movement_type', 'reason', 'quantity',
                  'balance_after', 'reference_type', 'reference_id',
                  'notes', 'created_by', 'created_by_name', 'created_at']
        read_only_fields = ['id', 'balance_after', 'created_by', 'created_at']


class StockTransferItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = StockTransferItem
        fields = ['id', 'product', 'product_name', 'quantity', 'received_quantity']
        read_only_fields = ['id']


class StockTransferSerializer(serializers.ModelSerializer):
    items = StockTransferItemSerializer(many=True, read_only=True)
    from_branch_name = serializers.CharField(source='from_branch.name', read_only=True)
    to_branch_name = serializers.CharField(source='to_branch.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.email', read_only=True, default='')
    approved_by_name = serializers.CharField(source='approved_by.email', read_only=True, default='')

    class Meta:
        model = StockTransfer
        fields = ['id', 'transfer_number', 'from_branch', 'from_branch_name',
                  'to_branch', 'to_branch_name', 'status', 'notes',
                  'rejected_reason', 'created_by', 'created_by_name',
                  'approved_by', 'approved_by_name',
                  'created_at', 'approved_at', 'received_at', 'items']
        read_only_fields = ['id', 'transfer_number', 'created_by', 'created_at',
                            'approved_by', 'approved_at']


class StockTransferCreateSerializer(serializers.Serializer):
    """Create a stock transfer with items."""
    from_branch = serializers.IntegerField()
    to_branch = serializers.IntegerField()
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    items = StockTransferItemSerializer(many=True)
