"""
Django admin configuration for Passes, Registrations, and EntryLogs.

Features:
- Search / filter on all key fields
- CSV export actions
- Bulk-generate pass tokens
- Read-only photo previews via short-lived URLs
- Admin action to reset a registration (allow re-upload)
"""
from __future__ import annotations

import csv
import secrets
from io import StringIO
from typing import Any

from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.utils.html import format_html

from .models import EntryLog, Pass, Registration
from .services.storage import get_photo_url


# ───────────────────────────────────────────────
# Inline
# ───────────────────────────────────────────────
class RegistrationInline(admin.StackedInline):
    model = Registration
    extra = 0
    readonly_fields = (
        "full_name",
        "mobile",
        "email",
        "customer_photo_preview",
        "pass_photo_preview",
        "face_quality_score",
        "ocr_pass_number",
        "needs_review",
        "registered_at",
        "ip_address",
    )
    exclude = ("face_embedding", "user_agent")

    @admin.display(description="Customer Photo")
    def customer_photo_preview(self, obj: Registration) -> str:
        url = get_photo_url(obj.customer_photo_blob)
        if url:
            return format_html('<img src="{}" style="max-height:200px;border-radius:8px;" />', url)
        return "—"

    @admin.display(description="Pass Photo")
    def pass_photo_preview(self, obj: Registration) -> str:
        url = get_photo_url(obj.pass_photo_blob)
        if url:
            return format_html('<img src="{}" style="max-height:200px;border-radius:8px;" />', url)
        return "—"


# ───────────────────────────────────────────────
# Pass Admin
# ───────────────────────────────────────────────
@admin.register(Pass)
class PassAdmin(admin.ModelAdmin):
    list_display = ("pass_number", "status", "pass_type", "event_date_from", "event_date_to", "created_at")
    list_filter = ("status", "pass_type", "event_date_from")
    search_fields = ("pass_number", "token")
    readonly_fields = ("id", "token", "created_at", "registration_link")
    inlines = [RegistrationInline]
    actions = ["export_csv", "bulk_generate_tokens", "reset_registration", "block_passes"]

    @admin.display(description="Registration Link")
    def registration_link(self, obj: Pass) -> str:
        return format_html(
            '<a href="{url}" target="_blank">{url}</a>',
            url=obj.registration_url,
        )

    # ── Actions ──

    @admin.action(description="📤 Export selected passes as CSV")
    def export_csv(self, request: HttpRequest, queryset: Any) -> HttpResponse:
        buf = StringIO()
        writer = csv.writer(buf)
        writer.writerow(["pass_number", "token", "link", "status", "pass_type"])
        for p in queryset:
            writer.writerow([p.pass_number, p.token, p.registration_url, p.status, p.pass_type])
        response = HttpResponse(buf.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = "attachment; filename=passes_export.csv"
        return response

    @admin.action(description="🔑 Bulk-generate 50 new passes (PASS-XXXX)")
    def bulk_generate_tokens(self, request: HttpRequest, queryset: Any) -> None:
        """Generate 50 new passes with sequential pass numbers."""
        last = Pass.objects.order_by("-pass_number").first()
        start = 1
        if last and last.pass_number.startswith("PASS-"):
            try:
                start = int(last.pass_number.split("-")[1]) + 1
            except (ValueError, IndexError):
                pass
        created = []
        for i in range(50):
            num = f"PASS-{start + i:04d}"
            created.append(Pass(pass_number=num, token=secrets.token_urlsafe(24)))
        Pass.objects.bulk_create(created, ignore_conflicts=True)
        self.message_user(request, f"✅ Created {len(created)} passes starting from {created[0].pass_number}")

    @admin.action(description="🔄 Reset registration (allow re-upload)")
    def reset_registration(self, request: HttpRequest, queryset: Any) -> None:
        count = 0
        for p in queryset.filter(status=Pass.Status.REGISTERED):
            Registration.objects.filter(pass_obj=p).delete()
            p.status = Pass.Status.UNUSED
            p.save(update_fields=["status"])
            count += 1
        self.message_user(request, f"🔄 Reset {count} registration(s)")

    @admin.action(description="🚫 Block selected passes")
    def block_passes(self, request: HttpRequest, queryset: Any) -> None:
        updated = queryset.update(status=Pass.Status.BLOCKED)
        self.message_user(request, f"🚫 Blocked {updated} pass(es)")


# ───────────────────────────────────────────────
# Registration Admin
# ───────────────────────────────────────────────
@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ("full_name", "pass_number_display", "mobile", "needs_review", "registered_at")
    list_filter = ("needs_review", "registered_at")
    search_fields = ("full_name", "mobile", "email", "pass_obj__pass_number")
    readonly_fields = (
        "customer_photo_preview",
        "pass_photo_preview",
        "face_quality_score",
        "ocr_pass_number",
        "registered_at",
        "ip_address",
    )
    exclude = ("face_embedding", "user_agent")

    @admin.display(description="Pass #", ordering="pass_obj__pass_number")
    def pass_number_display(self, obj: Registration) -> str:
        return obj.pass_obj.pass_number

    @admin.display(description="Customer Photo")
    def customer_photo_preview(self, obj: Registration) -> str:
        url = get_photo_url(obj.customer_photo_blob)
        if url:
            return format_html('<img src="{}" style="max-height:200px;border-radius:8px;" />', url)
        return "—"

    @admin.display(description="Pass Photo")
    def pass_photo_preview(self, obj: Registration) -> str:
        url = get_photo_url(obj.pass_photo_blob)
        if url:
            return format_html('<img src="{}" style="max-height:200px;border-radius:8px;" />', url)
        return "—"


# ───────────────────────────────────────────────
# EntryLog Admin
# ───────────────────────────────────────────────
@admin.register(EntryLog)
class EntryLogAdmin(admin.ModelAdmin):
    list_display = ("scanned_at", "pass_display", "result", "similarity_score", "admitted", "device_ip")
    list_filter = ("result", "admitted", "scanned_at")
    search_fields = ("pass_obj__pass_number", "device_ip")
    readonly_fields = ("id", "scanned_at", "scan_photo_preview")
    actions = ["export_csv"]

    @admin.display(description="Pass #", ordering="pass_obj__pass_number")
    def pass_display(self, obj: EntryLog) -> str:
        return obj.pass_obj.pass_number if obj.pass_obj else "—"

    @admin.display(description="Scan Photo")
    def scan_photo_preview(self, obj: EntryLog) -> str:
        url = get_photo_url(obj.scan_photo_blob)
        if url:
            return format_html('<img src="{}" style="max-height:200px;border-radius:8px;" />', url)
        return "—"

    @admin.action(description="📤 Export selected logs as CSV")
    def export_csv(self, request: HttpRequest, queryset: Any) -> HttpResponse:
        buf = StringIO()
        writer = csv.writer(buf)
        writer.writerow(["scanned_at", "pass_number", "result", "similarity", "admitted", "device_ip"])
        for log in queryset.select_related("pass_obj"):
            writer.writerow([
                log.scanned_at.isoformat(),
                log.pass_obj.pass_number if log.pass_obj else "",
                log.result,
                f"{log.similarity_score:.4f}",
                log.admitted,
                log.device_ip or "",
            ])
        response = HttpResponse(buf.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = "attachment; filename=entry_logs_export.csv"
        return response
