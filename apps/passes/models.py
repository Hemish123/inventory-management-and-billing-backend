"""
Data models for the Navratri Face Pass system.

Pass          – one per purchased pass (token + pass_number)
Registration  – one-to-one with Pass (face data, photos, contact info)
EntryLog      – every gate scan attempt (match or miss)
"""
from __future__ import annotations

import secrets
import uuid

from django.db import models
from django.utils import timezone


def generate_pass_token() -> str:
    return secrets.token_urlsafe(24)


class Pass(models.Model):
    """A purchased Navratri pass identified by a unique pass_number and access token."""

    class Status(models.TextChoices):
        UNUSED = "UNUSED", "Unused"
        REGISTERED = "REGISTERED", "Registered"
        BLOCKED = "BLOCKED", "Blocked"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pass_number = models.CharField(max_length=50, unique=True, db_index=True)
    token = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        default=generate_pass_token,
    )
    pass_type = models.CharField(max_length=50, blank=True, default="")
    event_date_from = models.DateField(null=True, blank=True)
    event_date_to = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.UNUSED,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Pass"
        verbose_name_plural = "Passes"

    def __str__(self) -> str:
        return f"Pass {self.pass_number} ({self.status})"

    @property
    def registration_url(self) -> str:
        """Relative URL for customer registration."""
        return f"/p/{self.token}/"

    @property
    def is_registered(self) -> bool:
        return self.status == self.Status.REGISTERED


class Registration(models.Model):
    """Customer registration linked one-to-one to a Pass."""

    pass_obj = models.OneToOneField(
        Pass,
        on_delete=models.CASCADE,
        related_name="registration",
    )
    full_name = models.CharField(max_length=200)
    mobile = models.CharField(max_length=20)
    email = models.EmailField(blank=True, default="")
    consent_given = models.BooleanField(default=False)

    # Images stored as blob paths (Azure) or relative media paths (local)
    customer_photo_blob = models.CharField(max_length=500)
    pass_photo_blob = models.CharField(max_length=500)

    # 512-d float32 embedding, L2-normalised, stored as raw bytes (2048 bytes)
    face_embedding = models.BinaryField()
    face_quality_score = models.FloatField(default=0.0)

    # Pass number extracted via OCR / QR from the pass photo
    ocr_pass_number = models.CharField(max_length=50, blank=True, default="")
    # If True, OCR couldn't read the pass number — admin should review
    needs_review = models.BooleanField(default=False)

    registered_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-registered_at"]

    def __str__(self) -> str:
        return f"Reg: {self.full_name} → {self.pass_obj.pass_number}"


class EntryLog(models.Model):
    """Log of every gate scan attempt."""

    class Result(models.TextChoices):
        MATCHED = "MATCHED", "Matched"
        NO_MATCH = "NO_MATCH", "No Match"
        REVIEW = "REVIEW", "Review"
        DUPLICATE = "DUPLICATE", "Duplicate Entry"
        BLOCKED = "BLOCKED", "Blocked"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pass_obj = models.ForeignKey(
        Pass,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entry_logs",
    )
    scan_photo_blob = models.CharField(max_length=500, blank=True, default="")
    similarity_score = models.FloatField(default=0.0)
    result = models.CharField(max_length=20, choices=Result.choices, db_index=True)
    admitted = models.BooleanField(default=False)
    scanned_at = models.DateTimeField(auto_now_add=True, db_index=True)
    device_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-scanned_at"]
        indexes = [
            models.Index(fields=["pass_obj", "scanned_at"]),
        ]

    def __str__(self) -> str:
        pass_num = self.pass_obj.pass_number if self.pass_obj else "—"
        return f"Scan {self.scanned_at:%H:%M} → {pass_num} ({self.result})"
