from django.contrib import admin
from .models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'company', 'phone', 'email', 'gstin', 'is_active', 'created_at']
    search_fields = ['name', 'company', 'email', 'phone', 'gstin']
    list_filter = ['is_active', 'created_at']
    ordering = ['name']
    fieldsets = (
        ('Basic Info', {
            'fields': ('name', 'phone', 'email', 'company', 'address', 'gstin',
                        'is_active', 'msme_owner')
        }),
    )
