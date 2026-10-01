"""URL configuration for the passes app."""
from django.urls import path

from . import views

app_name = "passes"

urlpatterns = [
    # Customer registration (open for everyone)
    path("", views.register_view, name="register"),

    # Gate endpoints (protected by GATE_KEY)
    path("gate/", views.gate_scan_view, name="gate_scan"),
    path("gate/verify/", views.gate_verify_view, name="gate_verify"),
    path("gate/confirm/", views.gate_confirm_view, name="gate_confirm"),
    path("gate/manual-match/", views.gate_manual_match_view, name="gate_manual_match"),
]
