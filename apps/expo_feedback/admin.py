import csv
from io import StringIO
from django.contrib import admin
from django.http import HttpResponse
from .models import VisitorSession, SessionFeedback


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
