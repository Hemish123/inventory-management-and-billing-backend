import csv
from io import StringIO
from django.contrib import admin
from django.http import HttpResponse
from .models import VisitorSession, SessionFeedback, ClaimTrial, ExpoVoiceAgent


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
        'user_name',
        'email',
        'phone_number',
        'company_name',
        'industry',
        'created_at',
    )
    list_filter = ('industry', 'created_at')
    search_fields = ('id', 'user_name', 'email', 'phone_number', 'company_name', 'industry', 'address')
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
                c.created_at.isoformat() if c.created_at else '',
            ])
        response = HttpResponse(buf.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="expo_claim_trials.csv"'
        return response


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


