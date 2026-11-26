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


class ClaimTrial(models.Model):
    """
    Stores details submitted via the Claim Trial form.
    Optionally linked to a VisitorSession if session_id is supplied.
    """

    INDUSTRY_CHOICES = [
        ('IT & Software', 'IT & Software'),
        ('Retail & E-Commerce', 'Retail & E-Commerce'),
        ('Automotive', 'Automotive'),
        ('Real Estate & Housing', 'Real Estate & Housing'),
        ('Healthcare', 'Healthcare'),
        ('Finance & Insurance', 'Finance & Insurance'),
        ('Manufacturing', 'Manufacturing'),
        ('Education', 'Education'),
        ('Hospitality & Travel', 'Hospitality & Travel'),
        ('Logistics & Supply Chain', 'Logistics & Supply Chain'),
        ('Professional Services', 'Professional Services'),
        ('Other', 'Other'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        VisitorSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='trial_claims',
    )
    user_name = models.CharField(max_length=255, blank=True, default='')
    email = models.CharField(max_length=255, blank=True, default='')
    phone_number = models.CharField(max_length=50, blank=True, default='')
    company_name = models.CharField(max_length=255, blank=True, default='')
    industry = models.CharField(
        max_length=255,
        choices=INDUSTRY_CHOICES,
        blank=True,
        default='',
    )
    address = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Claim Trial'
        verbose_name_plural = 'Claim Trials'

    def __str__(self):
        label = self.user_name or self.company_name or self.email or str(self.id)[:8]
        return f"Trial Claim: {label}"


class ExpoVoiceAgent(models.Model):
    """
    Stores voice agent configurations managed from the React admin UI
    so all visitors opening the link see the updated list of agents.
    """

    id = models.SlugField(max_length=100, primary_key=True)
    name = models.CharField(max_length=255)
    app_id = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, default='')
    language = models.CharField(max_length=100, blank=True, default='')
    accent = models.CharField(max_length=100, blank=True, default='')
    include_agent_variables = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Expo Voice Agent'
        verbose_name_plural = 'Expo Voice Agents'

    def __str__(self):
        return f"{self.name} ({self.id})"


