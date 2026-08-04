from django.contrib import admin
from django.contrib.auth import get_user_model

User = get_user_model()


@admin.register(User)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ['email', 'username', 'company', 'phone', 'is_active', 'created_at']
    search_fields = ['email', 'username', 'company__name']
    list_filter = ['is_active', 'is_staff', 'created_at']
    ordering = ['-created_at']
