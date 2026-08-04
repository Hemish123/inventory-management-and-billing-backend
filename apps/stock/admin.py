from django.contrib import admin
from .models import StockMovement, StockTransfer, StockTransferItem


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ['product', 'branch', 'movement_type', 'reason', 'quantity',
                    'balance_after', 'reference_id', 'created_at']
    list_filter = ['movement_type', 'reason', 'branch']
    search_fields = ['product__name', 'reference_id']
    readonly_fields = ['created_at']


class TransferItemInline(admin.TabularInline):
    model = StockTransferItem
    extra = 0


@admin.register(StockTransfer)
class StockTransferAdmin(admin.ModelAdmin):
    list_display = ['id', 'from_branch', 'to_branch', 'status', 'created_at']
    list_filter = ['status']
    inlines = [TransferItemInline]
