import csv
from io import StringIO
from django.contrib import admin
from django.http import HttpResponse
from .models import VisitorSession, SessionFeedback, ClaimTrial, UserCredit, CreditTransaction,ExpoVoiceAgent


class SessionFeedbackInline(admin.TabularInline):
    model = SessionFeedback
    extra = 0
    readonly_fields = ('id', 'rating', 'feedback_description', 'submitted_at')


@admin.register(VisitorSession)
class VisitorSessionAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user_name',
        'email_id',
        'phone_number',
        'status',
        'rating',
        'started_at',
        'completed_at',
    )
    list_filter = ('status', 'rating', 'started_at', 'completed_at')
    search_fields = ('id', 'user_name', 'email_id', 'phone_number', 'feedback_description')
    readonly_fields = ('id', 'started_at', 'completed_at', 'updated_at')
    inlines = [SessionFeedbackInline]
    actions = ['export_csv']

    @admin.action(description='Export selected sessions as CSV')
    def export_csv(self, request, queryset):
        buf = StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            'session_id',
            'user_name',
            'email_id',
            'phone_number',
            'status',
            'rating',
            'feedback_description',
            'started_at',
            'completed_at',
        ])
        for s in queryset:
            writer.writerow([
                str(s.id),
                s.user_name,
                s.email_id,
                s.phone_number,
                s.status,
                s.rating if s.rating is not None else '',
                s.feedback_description,
                s.started_at.isoformat() if s.started_at else '',
                s.completed_at.isoformat() if s.completed_at else '',
            ])
        response = HttpResponse(buf.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="expo_feedback_sessions.csv"'
        return response


@admin.register(SessionFeedback)
class SessionFeedbackAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'rating', 'submitted_at')
    list_filter = ('rating', 'submitted_at')
    search_fields = ('session__user_name', 'session__email_id', 'session__phone_number', 'feedback_description')
    readonly_fields = ('id', 'submitted_at')


@admin.register(ClaimTrial)
class ClaimTrialAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'user_name',
        'email',
        'phone_number',
        'company_name',
        'industry',
        'credits_granted',
        'created_at',
    )
    list_filter = ('industry', 'credits_granted', 'created_at')
    search_fields = ('id', 'user_name', 'email', 'phone_number', 'company_name', 'industry', 'address', 'user__email', 'user__username')
    readonly_fields = ('id', 'created_at', 'updated_at')
    actions = ['export_csv']

    @admin.action(description='Export selected trial claims as CSV')
    def export_csv(self, request, queryset):
        buf = StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            'id',
            'session_id',
            'user_name',
            'email',
            'phone_number',
            'company_name',
            'industry',
            'address',
            'credits_granted',
            'created_at',
        ])
        for c in queryset:
            writer.writerow([
                str(c.id),
                str(c.session_id) if c.session_id else '',
                c.user_name,
                c.email,
                c.phone_number,
                c.company_name,
                c.industry,
                c.address,
                c.credits_granted,
                c.created_at.isoformat() if c.created_at else '',
            ])
        response = HttpResponse(buf.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="expo_claim_trials.csv"'
        return response


@admin.register(UserCredit)
class UserCreditAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'credits',
        'total_earned',
        'total_spent',
        'has_claimed_trial',
        'updated_at',
    )
    list_editable = ('credits',)
    list_filter = ('has_claimed_trial', 'updated_at', 'created_at')
    search_fields = ('user__email', 'user__username', 'user__first_name', 'user__last_name')
    readonly_fields = ('total_earned', 'total_spent', 'created_at', 'updated_at')
    actions = ['add_500_credits', 'add_1000_credits', 'reset_trial_status']

    def save_model(self, request, obj, form, change):
        if change:
            old_obj = UserCredit.objects.filter(pk=obj.pk).first()
            if old_obj and old_obj.credits != obj.credits:
                diff = obj.credits - old_obj.credits
                if diff > 0:
                    obj.total_earned += diff
                elif diff < 0:
                    obj.total_spent += abs(diff)
                super().save_model(request, obj, form, change)
                CreditTransaction.objects.create(
                    user=obj.user,
                    amount=diff,
                    balance_after=obj.credits,
                    action=CreditTransaction.Action.ADMIN_ADJUSTMENT,
                    description=f"Admin {request.user.username or request.user.email} manual adjustment by {diff:+d} (balance: {old_obj.credits} -> {obj.credits})",
                )
                return
        super().save_model(request, obj, form, change)

    @admin.action(description='Grant +500 Credits to selected users')
    def add_500_credits(self, request, queryset):
        count = 0
        for uc in queryset:
            uc.grant_credits(
                amount=500,
                action=CreditTransaction.Action.ADMIN_ADJUSTMENT,
                description=f"Admin {request.user.username or request.user.email} bulk grant (+500 credits)",
            )
            count += 1
        self.message_user(request, f"Successfully added 500 credits to {count} user(s).")

    @admin.action(description='Grant +1000 Credits to selected users')
    def add_1000_credits(self, request, queryset):
        count = 0
        for uc in queryset:
            uc.grant_credits(
                amount=1000,
                action=CreditTransaction.Action.ADMIN_ADJUSTMENT,
                description=f"Admin {request.user.username or request.user.email} bulk grant (+1000 credits)",
            )
            count += 1
        self.message_user(request, f"Successfully added 1000 credits to {count} user(s).")

    @admin.action(description='Reset Trial Claimed status for selected users')
    def reset_trial_status(self, request, queryset):
        updated = queryset.update(has_claimed_trial=False)
        self.message_user(request, f"Reset trial claimed status for {updated} user(s).")


@admin.register(CreditTransaction)
class CreditTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'amount_display',
        'balance_after',
        'action',
        'description',
        'created_at',
    )
    list_filter = ('action', 'created_at')
    search_fields = ('user__email', 'user__username', 'description', 'action')
    readonly_fields = ('id', 'user', 'amount', 'balance_after', 'action', 'description', 'created_at')

    @admin.display(description='Amount', ordering='amount')
    def amount_display(self, obj):
        if obj.amount > 0:
            return f"+{obj.amount}"
        return str(obj.amount)
@admin.register(ExpoVoiceAgent)
class ExpoVoiceAgentAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'name',
        'app_id',
        'language',
        'accent',
        'include_agent_variables',
        'created_at',
        'updated_at',
    )
    list_filter = ('language', 'accent', 'include_agent_variables', 'created_at')
    search_fields = ('id', 'name', 'app_id', 'description', 'language', 'accent')
    readonly_fields = ('created_at', 'updated_at')


