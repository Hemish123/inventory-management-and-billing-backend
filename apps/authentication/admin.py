from django.contrib import admin
from django.contrib.auth import get_user_model
from apps.expo_feedback.models import UserCredit

User = get_user_model()


class UserCreditInline(admin.StackedInline):
    model = UserCredit
    can_delete = False
    extra = 0
    fields = ('credits', 'total_earned', 'total_spent', 'has_claimed_trial', 'updated_at')
    readonly_fields = ('updated_at',)


@admin.register(User)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ['email', 'username', 'get_credits', 'company', 'phone', 'is_active', 'created_at']
    search_fields = ['email', 'username', 'company__name']
    list_filter = ['is_active', 'is_staff', 'created_at']
    ordering = ['-created_at']
    inlines = [UserCreditInline]

    @admin.display(description='Credits')
    def get_credits(self, obj):
        credit = getattr(obj, 'ai_credit', None)
        return credit.credits if credit else 0
