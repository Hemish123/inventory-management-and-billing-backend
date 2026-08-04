from django.contrib import admin
from .models import Branch, Warehouse


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'phone', 'manager_name', 'is_active']
    search_fields = ['name', 'code']
    list_filter = ['is_active']


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'branch', 'is_active']
    list_filter = ['branch', 'is_active']
