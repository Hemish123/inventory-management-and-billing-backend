import uuid
from django.db import models


class VisitorSession(models.Model):
    """
    Represents one visitor session from entry form submission
    through feedback completion.
    """

    class Status(models.TextChoices):
        STARTED = 'STARTED', 'Started'
        COMPLETED = 'COMPLETED', 'Completed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_name = models.CharField(max_length=255, blank=True, default='')
    email_id = models.CharField(max_length=255, blank=True, default='')
    phone_number = models.CharField(max_length=50, blank=True, default='')

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.STARTED,
        db_index=True,
    )

    # Latest feedback snapshot stored directly on the session for easy querying
    rating = models.PositiveSmallIntegerField(null=True, blank=True)
    feedback_description = models.TextField(blank=True, default='')

    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-started_at']
        verbose_name = 'Visitor Session'
        verbose_name_plural = 'Visitor Sessions'

    def __str__(self):
        label = self.user_name or self.email_id or self.phone_number or str(self.id)[:8]
        return f"{label} ({self.status})"


class SessionFeedback(models.Model):
    """
    Stores every feedback submission linked to a VisitorSession so that
    repeated feedback submissions on the same session are always accepted
    and never lost.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        VisitorSession,
        on_delete=models.CASCADE,
        related_name='feedbacks',
    )
    rating = models.PositiveSmallIntegerField(null=True, blank=True)
    feedback_description = models.TextField(blank=True, default='')
    submitted_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-submitted_at']
        verbose_name = 'Session Feedback'
        verbose_name_plural = 'Session Feedbacks'

    def __str__(self):
        stars = f"{self.rating}/5" if self.rating is not None else "No rating"
        return f"Feedback {stars} — Session {str(self.session_id)[:8]}"
