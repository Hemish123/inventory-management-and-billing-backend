from rest_framework import serializers
from .models import Bill, BillItem, BillPayment, BillSequence


class BillItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillItem
        fields = ['id', 'product', 'product_name', 'barcode', 'hsn_code',
                  'quantity', 'unit_price',
                  'discount_type', 'discount_percentage', 'discount_amount',
                  'tax_percentage', 'tax_amount', 'line_total']
        read_only_fields = ['id']


class BillPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillPayment
        fields = ['id', 'payment_method', 'amount', 'reference', 'created_at']
        read_only_fields = ['id', 'created_at']


class BillSerializer(serializers.ModelSerializer):
    items = BillItemSerializer(many=True, read_only=True)
    payments = BillPaymentSerializer(many=True, read_only=True)
    cashier_name = serializers.CharField(source='cashier.email', read_only=True, default='')
    branch_name = serializers.CharField(source='branch.name', read_only=True, default='')

    class Meta:
        model = Bill
        fields = [
            'id', 'bill_number', 'branch', 'branch_name',
            'customer', 'customer_name', 'customer_phone',
            'billing_date', 'status',
            'subtotal', 'tax_total',
            'discount_type', 'discount_amount', 'discount_percentage',
            'round_off', 'grand_total',
            'payment_method', 'amount_received', 'change_due',
            'notes', 'cashier', 'cashier_name',
            'items', 'payments',
        ]
        read_only_fields = ['id', 'bill_number', 'billing_date', 'cashier']


class BillItemCreateSerializer(serializers.Serializer):
    """Serializer for bill line items in create/draft requests."""
    product = serializers.IntegerField()
    product_name = serializers.CharField(max_length=255)
    barcode = serializers.CharField(max_length=50, required=False, allow_blank=True, default='')
    hsn_code = serializers.CharField(max_length=20, required=False, allow_blank=True, default='')
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2)
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    discount_type = serializers.ChoiceField(choices=['NONE', 'PERCENTAGE', 'FIXED'], default='NONE')
    discount_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_amount = serializers.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_percentage = serializers.IntegerField(default=0)
    tax_amount = serializers.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_total = serializers.DecimalField(max_digits=14, decimal_places=2)


class BillPaymentCreateSerializer(serializers.Serializer):
    """Serializer for split payment details."""
    payment_method = serializers.ChoiceField(choices=['CASH', 'UPI', 'CARD', 'NET_BANKING', 'CREDIT'])
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')


class BillCreateSerializer(serializers.Serializer):
    """Custom serializer for creating/saving a bill with items in one request."""
    branch_id = serializers.IntegerField()
    customer_id = serializers.IntegerField(required=False, allow_null=True)
    customer_name = serializers.CharField(max_length=255, required=False, allow_blank=True, default='Walk-in Customer')
    customer_phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default='')
    payment_method = serializers.ChoiceField(choices=['CASH', 'UPI', 'CARD', 'NET_BANKING', 'CREDIT', 'SPLIT'])
    amount_received = serializers.DecimalField(max_digits=14, decimal_places=2, default=0)
    # Overall discount
    discount_type = serializers.ChoiceField(choices=['NONE', 'PERCENTAGE', 'FIXED'], default='NONE')
    discount_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_amount = serializers.DecimalField(max_digits=14, decimal_places=2, default=0)
    round_off = serializers.DecimalField(max_digits=5, decimal_places=2, default=0)
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    # Line items
    items = BillItemCreateSerializer(many=True)
    # Split payment details (only required when payment_method = SPLIT)
    payments = BillPaymentCreateSerializer(many=True, required=False, default=[])
    # Whether this is a draft/hold
    save_as_draft = serializers.BooleanField(default=False)
    save_as_hold = serializers.BooleanField(default=False)
    # Selected salesperson
    salesperson_id = serializers.IntegerField(required=False, allow_null=True)


class BillListSerializer(serializers.ModelSerializer):
    cashier_name = serializers.CharField(source='cashier.email', read_only=True, default='')
    branch_name = serializers.CharField(source='branch.name', read_only=True, default='')

    class Meta:
        model = Bill
        fields = ['id', 'bill_number', 'branch_name', 'customer_name',
                  'billing_date', 'grand_total', 'payment_method', 'status',
                  'cashier_name']
