from django.contrib import admin
from .models import Bill, BillItem, BillSequence


class BillItemInline(admin.TabularInline):
    model = BillItem
    extra = 0
    readonly_fields = ['product', 'product_name', 'quantity', 'unit_price', 'line_total']


@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = ['bill_number', 'branch', 'customer_name', 'grand_total',
                    'payment_method', 'status', 'cashier', 'billing_date']
    search_fields = ['bill_number', 'customer_name']
    list_filter = ['status', 'payment_method', 'branch']
    inlines = [BillItemInline]


@admin.register(BillSequence)
class BillSequenceAdmin(admin.ModelAdmin):
    list_display = ['branch', 'date', 'last_number']
