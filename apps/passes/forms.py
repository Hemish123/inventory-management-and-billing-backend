"""
Registration form for the Navratri Face Pass system.
Validates images server-side (type, size, resolution).
"""
from __future__ import annotations

from django import forms
from PIL import Image

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE = 8 * 1024 * 1024  # 8 MB
MIN_RESOLUTION = 200  # px, minimum width or height


def _validate_image(file: forms.FileField, field_name: str) -> None:
    """Validate uploaded image: MIME type, size, and minimum resolution."""
    if file.content_type not in ALLOWED_TYPES:
        raise forms.ValidationError(
            f"{field_name}: Only JPG, PNG, or WebP images are allowed."
        )
    if file.size > MAX_FILE_SIZE:
        raise forms.ValidationError(
            f"{field_name}: File size must be under 8 MB (got {file.size / 1024 / 1024:.1f} MB)."
        )
    # Check the image can actually be opened and meets minimum resolution
    try:
        file.seek(0)
        img = Image.open(file)
        img.verify()
        file.seek(0)
        img = Image.open(file)
        w, h = img.size
        if w < MIN_RESOLUTION or h < MIN_RESOLUTION:
            raise forms.ValidationError(
                f"{field_name}: Image is too small ({w}×{h}). "
                f"Minimum resolution is {MIN_RESOLUTION}×{MIN_RESOLUTION}px."
            )
        file.seek(0)
    except forms.ValidationError:
        raise
    except Exception:
        raise forms.ValidationError(f"{field_name}: Could not read image — file may be corrupted.")


class RegistrationForm(forms.Form):
    """Customer-facing registration form (no Django auth)."""

    full_name = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Full Name",
            "autocomplete": "name",
        }),
    )
    mobile = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Mobile Number",
            "type": "tel",
            "autocomplete": "tel",
        }),
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            "class": "form-control",
            "placeholder": "Email (optional)",
            "autocomplete": "email",
        }),
    )
    customer_photo = forms.FileField(
        widget=forms.ClearableFileInput(attrs={
            "class": "form-control",
            "accept": "image/*",
            "capture": "user",
        }),
        help_text="Clear front-facing photo of your face",
    )
    pass_photo = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(attrs={
            "class": "form-control",
            "accept": "image/*",
        }),
        help_text="Photo or screenshot of your purchased Navratri pass",
    )
    manual_pass_number = forms.CharField(
        required=False,
        max_length=50,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Pass number (if OCR fails)",
        }),
        help_text="Enter your pass number manually if auto-detection fails",
    )
    consent = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        error_messages={
            "required": "You must consent to face data storage to register.",
        },
    )

    def clean_customer_photo(self) -> forms.FileField:
        f = self.cleaned_data["customer_photo"]
        _validate_image(f, "Customer Photo")
        return f

    def clean_pass_photo(self) -> forms.FileField | None:
        f = self.cleaned_data.get("pass_photo")
        if f:
            _validate_image(f, "Pass Photo")
        return f

    def clean(self):
        cleaned_data = super().clean()
        pass_photo = cleaned_data.get("pass_photo")
        manual_pass_number = cleaned_data.get("manual_pass_number")

        if not pass_photo and not manual_pass_number:
            raise forms.ValidationError("You must either upload a pass photo or manually enter the pass number.")
        return cleaned_data
