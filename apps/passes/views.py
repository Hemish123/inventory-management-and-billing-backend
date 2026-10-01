"""
Views for Navratri Face Pass — registration and gate verification.

No login required. Registration links are token-gated.
Gate is protected by GATE_KEY env var + rate limiting.
"""
from __future__ import annotations

import json
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .forms import RegistrationForm
from .models import EntryLog, Pass, Registration
from .services import face_engine, pass_reader, storage

logger = logging.getLogger("passes")


# ───────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────
def _get_client_ip(request: HttpRequest) -> str:
    """Extract client IP from request (respects X-Forwarded-For)."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "0.0.0.0")


def _check_gate_key(request: HttpRequest) -> bool:
    """Verify the gate key from query params."""
    return request.GET.get("key") == settings.GATE_KEY


# ───────────────────────────────────────────────
# Registration Views
# ───────────────────────────────────────────────
@require_http_methods(["GET", "POST"])
def register_view(request: HttpRequest) -> HttpResponse:
    """
    GET:  Show generic registration form.
    POST: Process face photo + pass photo, extract pass number, lookup Pass, create Registration.
    """
    if request.method == "GET":
        form = RegistrationForm()
        return render(request, "passes/register.html", {"form": form})

    # POST
    form = RegistrationForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(request, "passes/register.html", {"form": form, "show_manual_field": form.cleaned_data.get("manual_pass_number") != ""})

    try:
        # ── 1. Read image bytes ──
        customer_photo_file = form.cleaned_data["customer_photo"]
        pass_photo_file = form.cleaned_data.get("pass_photo")
        customer_bytes = customer_photo_file.read()
        pass_bytes = pass_photo_file.read() if pass_photo_file else b""

        # ── 2. Face detection + embedding ──
        try:
            face_result = face_engine.detect_and_embed(customer_bytes)
        except face_engine.QualityError as e:
            form.add_error("customer_photo", str(e))
            return render(request, "passes/register.html", {"form": form})

        # ── 3. Read pass number ──
        ocr_number = pass_reader.read_pass_number(pass_bytes) if pass_bytes else None
        manual_number = form.cleaned_data.get("manual_pass_number", "")
        
        # Determine the pass number to use
        used_number = pass_reader.normalise_pass_number(ocr_number or manual_number)
        
        if not used_number:
            form.add_error("manual_pass_number", "Please enter a valid pass number.")
            return render(request, "passes/register.html", {
                "form": form,
                "show_manual_field": True,
            })

        # Find or create the pass in the database
        pass_obj, created = Pass.objects.get_or_create(pass_number=used_number)

        # Check status
        if pass_obj.status == Pass.Status.REGISTERED:
            return render(request, "passes/already_registered.html", {"pass_obj": pass_obj})
        
        if pass_obj.status == Pass.Status.BLOCKED:
            return render(request, "passes/error.html", {
                "title": "Pass Blocked",
                "message": "This pass has been blocked. Please contact support.",
            })

        # ── 4. Upload photos ──
        customer_blob = storage.upload_photo(customer_bytes, prefix="customer_photos")
        pass_blob = storage.upload_photo(pass_bytes, prefix="pass_photos") if pass_bytes else ""

        # ── 5. Create registration atomically ──
        with transaction.atomic():
            locked_pass = Pass.objects.select_for_update().get(pk=pass_obj.pk)
            if locked_pass.status != Pass.Status.UNUSED:
                return render(request, "passes/already_registered.html", {"pass_obj": locked_pass})

            reg = Registration.objects.create(
                pass_obj=locked_pass,
                full_name=form.cleaned_data["full_name"],
                mobile=form.cleaned_data["mobile"],
                email=form.cleaned_data.get("email", ""),
                consent_given=True,
                customer_photo_blob=customer_blob,
                pass_photo_blob=pass_blob,
                face_embedding=face_engine.embedding_to_bytes(face_result.embedding),
                face_quality_score=face_result.quality_score,
                ocr_pass_number=used_number,
                needs_review=not ocr_number and bool(manual_number),  # Flag if they had to type it manually
                ip_address=_get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
            )

            locked_pass.status = Pass.Status.REGISTERED
            locked_pass.save(update_fields=["status"])

        # ── 6. Invalidate embedding cache ──
        face_engine.invalidate_embedding_cache()

        logger.info(
            "Registration complete: pass=%s name=%s quality=%.2f",
            locked_pass.pass_number,
            reg.full_name,
            face_result.quality_score,
        )

        return render(request, "passes/register_success.html", {
            "pass_obj": locked_pass,
            "registration": reg,
        })

    except Exception as e:
        logger.exception("Registration failed: %s", e)
        return render(request, "passes/error.html", {
            "title": "Registration Failed",
            "message": f"An error occurred: {e}. Please try again.",
        })


# ───────────────────────────────────────────────
# Gate Views
# ───────────────────────────────────────────────
@require_GET
def gate_scan_view(request: HttpRequest) -> HttpResponse:
    """Show the full-screen camera page for the security guard."""
    return render(request, "passes/gate_scan.html")


@csrf_exempt
@require_POST
def gate_verify_view(request: HttpRequest) -> JsonResponse:
    """
    Receive a scan photo, detect face, match against all embeddings.
    Returns JSON with match result.
    """

    scan_file = request.FILES.get("scan_photo")
    if not scan_file:
        return JsonResponse({"error": "No scan photo provided"}, status=400)

    try:
        scan_bytes = scan_file.read()

        # Detect face + embedding
        try:
            face_result = face_engine.detect_and_embed(scan_bytes)
        except face_engine.QualityError as e:
            return JsonResponse({
                "result": "ERROR",
                "message": str(e),
            })

        # Match against all registered embeddings
        matches = face_engine.match_against_all(face_result.embedding, top_k=5)

        if not matches:
            # Save scan photo
            scan_blob = storage.upload_photo(scan_bytes, prefix="gate_scans")
            EntryLog.objects.create(
                pass_obj=None,
                scan_photo_blob=scan_blob,
                similarity_score=0.0,
                result=EntryLog.Result.NO_MATCH,
                device_ip=_get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
            )
            return JsonResponse({
                "result": "NO_MATCH",
                "message": "No registered passes found in the system.",
            })

        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # 1. Gather all matches above the MATCH threshold
        valid_matches = [m for m in matches if m.score >= settings.FACE_MATCH_THRESHOLD]
        
        if valid_matches:
            best_pass = None
            best_reg = None
            best_score = 0.0
            
            # Try to find a pass that is NOT blocked and NOT already used today
            for m in valid_matches:
                try:
                    p = Pass.objects.get(pk=m.pass_id)
                    r = Registration.objects.get(pass_obj=p)
                except (Pass.DoesNotExist, Registration.DoesNotExist):
                    continue
                    
                if p.status == Pass.Status.BLOCKED:
                    continue
                    
                today_entries = EntryLog.objects.filter(
                    pass_obj=p,
                    result=EntryLog.Result.MATCHED,
                    admitted=True,
                    scanned_at__gte=today_start,
                ).count()
                
                if today_entries < settings.GATE_MAX_ENTRIES_PER_DAY:
                    best_pass, best_reg, best_score = p, r, m.score
                    break
            
            # If all valid matches are blocked/used, fall back to the very first (highest score) match
            if not best_pass:
                top = valid_matches[0]
                best_pass = Pass.objects.get(pk=top.pass_id)
                best_reg = Registration.objects.get(pass_obj=best_pass)
                best_score = top.score

            # Save scan photo
            scan_blob = storage.upload_photo(scan_bytes, prefix="gate_scans")

            # Check if pass is blocked
            if best_pass.status == Pass.Status.BLOCKED:
                entry = EntryLog.objects.create(
                    pass_obj=best_pass,
                    scan_photo_blob=scan_blob,
                    similarity_score=best_score,
                    result=EntryLog.Result.BLOCKED,
                    device_ip=_get_client_ip(request),
                    user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
                )
                return JsonResponse({
                    "result": "BLOCKED",
                    "message": "This pass has been BLOCKED.",
                    "pass_number": best_pass.pass_number,
                    "name": best_reg.full_name,
                    "similarity": round(best_score * 100, 1),
                    "entry_id": str(entry.pk),
                })

            # Check duplicate entry (anti-replay)
            today_entries = EntryLog.objects.filter(
                pass_obj=best_pass,
                result=EntryLog.Result.MATCHED,
                admitted=True,
                scanned_at__gte=today_start,
            ).count()

            if today_entries >= settings.GATE_MAX_ENTRIES_PER_DAY:
                last_entry = EntryLog.objects.filter(
                    pass_obj=best_pass,
                    result=EntryLog.Result.MATCHED,
                    admitted=True,
                    scanned_at__gte=today_start,
                ).order_by("-scanned_at").first()

                entry = EntryLog.objects.create(
                    pass_obj=best_pass,
                    scan_photo_blob=scan_blob,
                    similarity_score=best_score,
                    result=EntryLog.Result.DUPLICATE,
                    device_ip=_get_client_ip(request),
                    user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
                )

                last_time = last_entry.scanned_at.strftime("%I:%M %p") if last_entry else "earlier"
                return JsonResponse({
                    "result": "DUPLICATE",
                    "message": f"ALREADY ENTERED at {last_time}",
                    "pass_number": best_pass.pass_number,
                    "name": best_reg.full_name,
                    "similarity": round(best_score * 100, 1),
                    "entry_id": str(entry.pk),
                    "customer_photo_url": storage.get_photo_url(best_reg.customer_photo_blob),
                })

            # MATCHED
            entry = EntryLog.objects.create(
                pass_obj=best_pass,
                scan_photo_blob=scan_blob,
                similarity_score=best_score,
                result=EntryLog.Result.MATCHED,
                device_ip=_get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
            )

            return JsonResponse({
                "result": "MATCHED",
                "pass_number": best_pass.pass_number,
                "name": best_reg.full_name,
                "similarity": round(best_score * 100, 1),
                "customer_photo_url": storage.get_photo_url(best_reg.customer_photo_blob),
                "entry_id": str(entry.pk),
                "timestamp": entry.scanned_at.strftime("%I:%M %p"),
            })

        elif best_score >= settings.FACE_REVIEW_THRESHOLD:
            # REVIEW zone — show top 3 candidates
            entry = EntryLog.objects.create(
                pass_obj=best_pass,
                scan_photo_blob=scan_blob,
                similarity_score=best_score,
                result=EntryLog.Result.REVIEW,
                device_ip=_get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
            )

            candidates = []
            for m in matches[:3]:
                try:
                    p = Pass.objects.get(pk=m.pass_id)
                    r = Registration.objects.get(pass_obj=p)
                    candidates.append({
                        "pass_number": p.pass_number,
                        "name": r.full_name,
                        "similarity": round(m.score * 100, 1),
                        "customer_photo_url": storage.get_photo_url(r.customer_photo_blob),
                        "pass_id": str(p.pk),
                    })
                except (Pass.DoesNotExist, Registration.DoesNotExist):
                    continue

            return JsonResponse({
                "result": "REVIEW",
                "message": "Borderline match — please verify manually.",
                "candidates": candidates,
                "entry_id": str(entry.pk),
            })

        else:
            # NO MATCH
            entry = EntryLog.objects.create(
                pass_obj=None,
                scan_photo_blob=scan_blob,
                similarity_score=best_score,
                result=EntryLog.Result.NO_MATCH,
                device_ip=_get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
            )
            return JsonResponse({
                "result": "NO_MATCH",
                "message": "No matching pass found.",
                "best_score": round(best_score * 100, 1),
            })

    except Exception as e:
        logger.exception("Gate verification error: %s", e)
        return JsonResponse({
            "result": "ERROR",
            "message": f"Server error: {e}",
        }, status=500)


@csrf_exempt
@require_POST
def gate_confirm_view(request: HttpRequest) -> JsonResponse:
    """Mark an entry as admitted (Confirm Entry button)."""
    gate_key = request.POST.get("key") or request.GET.get("key", "")
    if gate_key != settings.GATE_KEY:
        return JsonResponse({"error": "Invalid gate key"}, status=403)

    entry_id = request.POST.get("entry_id")
    if not entry_id:
        return JsonResponse({"error": "Missing entry_id"}, status=400)

    try:
        with transaction.atomic():
            entry = EntryLog.objects.select_for_update().get(pk=entry_id)
            entry.admitted = True
            entry.save(update_fields=["admitted"])

        return JsonResponse({"status": "ok", "admitted": True})

    except EntryLog.DoesNotExist:
        return JsonResponse({"error": "Entry not found"}, status=404)
    except Exception as e:
        logger.exception("Confirm entry error: %s", e)
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_POST
def gate_manual_match_view(request: HttpRequest) -> JsonResponse:
    """
    Guard manually selects a candidate from the REVIEW zone.
    Creates a new MATCHED entry log for the selected pass.
    """
    gate_key = request.POST.get("key") or request.GET.get("key", "")
    if gate_key != settings.GATE_KEY:
        return JsonResponse({"error": "Invalid gate key"}, status=403)

    pass_id = request.POST.get("pass_id")
    entry_id = request.POST.get("entry_id")

    if not pass_id or not entry_id:
        return JsonResponse({"error": "Missing pass_id or entry_id"}, status=400)

    try:
        pass_obj = Pass.objects.get(pk=pass_id)
        original_entry = EntryLog.objects.get(pk=entry_id)

        # Update the original entry to mark as matched
        with transaction.atomic():
            original_entry.pass_obj = pass_obj
            original_entry.result = EntryLog.Result.MATCHED
            original_entry.admitted = True
            original_entry.save(update_fields=["pass_obj", "result", "admitted"])

        return JsonResponse({"status": "ok", "pass_number": pass_obj.pass_number})

    except (Pass.DoesNotExist, EntryLog.DoesNotExist):
        return JsonResponse({"error": "Not found"}, status=404)
    except Exception as e:
        logger.exception("Manual match error: %s", e)
        return JsonResponse({"error": str(e)}, status=500)
