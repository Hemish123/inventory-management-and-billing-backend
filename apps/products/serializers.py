from rest_framework import serializers
from .models import Category, Brand, Supplier, Product, BranchStock


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'description', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ['id', 'name', 'description', 'is_active']
        read_only_fields = ['id']


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ['id', 'name', 'contact_person', 'phone', 'email',
                  'address', 'gstin', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']


class BranchStockSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True, default='')

    class Meta:
        model = BranchStock
        fields = ['id', 'product', 'branch', 'branch_name', 'warehouse',
                  'warehouse_name', 'quantity']
        read_only_fields = ['id']


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True, default='')
    brand_name = serializers.CharField(source='brand.name', read_only=True, default='')
    supplier_name = serializers.CharField(source='supplier.name', read_only=True, default='')
    total_stock = serializers.IntegerField(read_only=True)
    branch_stocks = BranchStockSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'sku', 'barcode', 'name', 'description',
            'category', 'category_name', 'brand', 'brand_name',
            'supplier', 'supplier_name',
            'unit', 'cost_price', 'selling_price',
            'hsn_code', 'tax_percentage', 'minimum_stock_level', 'reorder_level',
            'dead_stock_days',
            'image', 'is_active',
            'total_stock', 'branch_stocks',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'barcode': {'required': False},
            'selling_price': {'required': False},
            'cost_price': {'required': False}
        }


class ProductListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    category_name = serializers.CharField(source='category.name', read_only=True, default='')
    brand_name = serializers.CharField(source='brand.name', read_only=True, default='')
    supplier_name = serializers.CharField(source='supplier.name', read_only=True, default='')
    total_stock = serializers.IntegerField(read_only=True)

    class Meta:
        model = Product
        fields = ['id', 'sku', 'barcode', 'name', 'description', 'category_name', 'brand_name', 'supplier_name',
                  'unit', 'cost_price', 'selling_price', 'hsn_code', 'tax_percentage', 'total_stock',
                  'minimum_stock_level', 'reorder_level', 'dead_stock_days', 'is_active']


class ProductDropdownSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'name', 'barcode', 'sku', 'selling_price', 'cost_price',
                  'tax_percentage', 'hsn_code', 'unit']
