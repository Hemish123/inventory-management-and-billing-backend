from django.contrib import admin
from .models import Purchase, PurchaseItem


class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    extra = 0


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ['po_number', 'branch', 'supplier', 'purchase_date', 'status', 'total_amount']
    list_filter = ['status', 'branch']
    search_fields = ['po_number', 'supplier__name']
    inlines = [PurchaseItemInline]
