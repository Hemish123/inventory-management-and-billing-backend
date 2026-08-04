from django.contrib import admin
from .models import Category, Brand, Supplier, Product, BranchStock


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at']
    search_fields = ['name']


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active']
    search_fields = ['name']


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ['name', 'contact_person', 'phone', 'email', 'gstin']
    search_fields = ['name', 'gstin']


class BranchStockInline(admin.TabularInline):
    model = BranchStock
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'sku', 'barcode', 'category', 'selling_price',
                    'cost_price', 'tax_percentage', 'is_active']
    search_fields = ['name', 'sku', 'barcode']
    list_filter = ['category', 'is_active']
    inlines = [BranchStockInline]
