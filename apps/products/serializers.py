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


def _get_product_initial_movement(obj):
    if hasattr(obj, 'initial_movements'):
        return obj.initial_movements[0] if obj.initial_movements else None
    return obj.stock_movements.filter(reason='INITIAL').select_related('branch').order_by('created_at').first()


def _get_product_initial_stock(obj):
    movement = _get_product_initial_movement(obj)
    if movement:
        return movement.quantity
    if hasattr(obj, '_prefetched_objects_cache') and 'branch_stocks' in obj._prefetched_objects_cache:
        stocks = list(obj.branch_stocks.all())
    else:
        stocks = list(obj.branch_stocks.all()[:1])
    if stocks and not obj.stock_movements.exists():
        return stocks[0].quantity
    return 0


def _get_product_initial_branch_id(obj):
    movement = _get_product_initial_movement(obj)
    if movement:
        return movement.branch_id
    if hasattr(obj, '_prefetched_objects_cache') and 'branch_stocks' in obj._prefetched_objects_cache:
        stocks = list(obj.branch_stocks.all())
    else:
        stocks = list(obj.branch_stocks.all()[:1])
    if stocks:
        return stocks[0].branch_id
    return None


def _get_product_initial_branch_name(obj):
    movement = _get_product_initial_movement(obj)
    if movement and movement.branch:
        return movement.branch.name
    if hasattr(obj, '_prefetched_objects_cache') and 'branch_stocks' in obj._prefetched_objects_cache:
        stocks = list(obj.branch_stocks.all())
    else:
        stocks = list(obj.branch_stocks.select_related('branch')[:1])
    if stocks and stocks[0].branch:
        return stocks[0].branch.name
    return ''


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True, default='')
    brand_name = serializers.CharField(source='brand.name', read_only=True, default='')
    supplier_name = serializers.CharField(source='supplier.name', read_only=True, default='')
    total_stock = serializers.IntegerField(read_only=True)
    branch_stocks = BranchStockSerializer(many=True, read_only=True)
    initial_stock = serializers.SerializerMethodField()
    initial_stock_branch = serializers.SerializerMethodField()
    initial_stock_branch_name = serializers.SerializerMethodField()

    def get_initial_stock(self, obj):
        return _get_product_initial_stock(obj)

    def get_initial_stock_branch(self, obj):
        return _get_product_initial_branch_id(obj)

    def get_initial_stock_branch_name(self, obj):
        return _get_product_initial_branch_name(obj)

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
            'initial_stock', 'initial_stock_branch', 'initial_stock_branch_name',
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
    initial_stock = serializers.SerializerMethodField()
    initial_stock_branch = serializers.SerializerMethodField()
    initial_stock_branch_name = serializers.SerializerMethodField()

    def get_initial_stock(self, obj):
        return _get_product_initial_stock(obj)

    def get_initial_stock_branch(self, obj):
        return _get_product_initial_branch_id(obj)

    def get_initial_stock_branch_name(self, obj):
        return _get_product_initial_branch_name(obj)

    class Meta:
        model = Product
        fields = ['id', 'sku', 'barcode', 'name', 'description', 'category_name', 'brand_name', 'supplier_name',
                  'unit', 'cost_price', 'selling_price', 'hsn_code', 'tax_percentage', 'total_stock',
                  'minimum_stock_level', 'reorder_level', 'dead_stock_days',
                  'initial_stock', 'initial_stock_branch', 'initial_stock_branch_name', 'is_active']


class ProductDropdownSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'name', 'barcode', 'sku', 'selling_price', 'cost_price',
                  'tax_percentage', 'hsn_code', 'unit']
