"""
Pass number reader — extracts the pass number from a pass photo.

Strategy (stops at first success):
    1. QR / barcode decode with OpenCV QRCodeDetector + pyzbar (if installed).
    2. Azure OpenAI Vision (gpt-4o) with a strict extraction prompt.
    3. Fallback: return None → the view asks the customer for manual entry.

The extracted number is normalised (stripped, uppercased) and validated
against the expected Pass.pass_number.
"""
from __future__ import annotations

import base64
import json
import logging
import re
from io import BytesIO

import cv2
import numpy as np
from PIL import Image, ImageOps

logger = logging.getLogger("passes")


def normalise_pass_number(raw: str | None) -> str:
    """Strip whitespace, uppercase, remove common punctuation noise."""
    if not raw:
        return ""
    cleaned = raw.strip().upper()
    # Remove stray characters that aren't alphanumeric or dash
    cleaned = re.sub(r"[^A-Z0-9\-]", "", cleaned)
    return cleaned


# ───────────────────────────────────────────────
# 1. QR / Barcode
# ───────────────────────────────────────────────
def _try_qr_opencv(image_bytes: bytes) -> str | None:
    """Try OpenCV's built-in QR code detector."""
    try:
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return None
        detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(img)
        if data:
            logger.info("QR code detected via OpenCV: %s", data[:50])
            return data
    except Exception as e:
        logger.debug("OpenCV QR detection failed: %s", e)
    return None


def _try_pyzbar(image_bytes: bytes) -> str | None:
    """Try pyzbar for QR codes and barcodes (optional dependency)."""
    try:
        from pyzbar.pyzbar import decode as pyzbar_decode

        img = Image.open(BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img)
        results = pyzbar_decode(img)
        if results:
            data = results[0].data.decode("utf-8", errors="ignore")
            logger.info("Barcode detected via pyzbar: %s", data[:50])
            return data
    except ImportError:
        logger.debug("pyzbar not installed, skipping barcode detection")
    except Exception as e:
        logger.debug("pyzbar detection failed: %s", e)
    return None


# ───────────────────────────────────────────────
# 2. Azure OpenAI Vision OCR
# ───────────────────────────────────────────────
def _try_azure_openai_vision(image_bytes: bytes) -> str | None:
    """
    Use Azure OpenAI gpt-4o vision to extract the pass number.
    Only used for text extraction from pass images — NEVER for face work.
    """
    from django.conf import settings

    if not settings.AZURE_OPENAI_ENDPOINT or not settings.AZURE_OPENAI_API_KEY:
        logger.debug("Azure OpenAI not configured, skipping vision OCR")
        return None

    try:
        from openai import AzureOpenAI

        client = AzureOpenAI(
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
        )

        # Encode image as base64
        b64_image = base64.b64encode(image_bytes).decode("utf-8")

        # Determine MIME type from bytes
        mime = "image/jpeg"
        if image_bytes[:4] == b"\x89PNG":
            mime = "image/png"
        elif image_bytes[:4] == b"RIFF":
            mime = "image/webp"

        response = client.chat.completions.create(
            model=settings.AZURE_OPENAI_DEPLOYMENT,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You extract pass numbers from Navratri event pass images. "
                        "Return ONLY valid JSON: {\"pass_number\": \"...\"} and nothing else. "
                        "If you cannot find a pass number, return {\"pass_number\": null}."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extract only the pass number from this Navratri pass image.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime};base64,{b64_image}",
                                "detail": "high",
                            },
                        },
                    ],
                },
            ],
            max_tokens=100,
            temperature=0.0,
        )

        raw_text = response.choices[0].message.content.strip()
        logger.info("Azure OpenAI OCR response: %s", raw_text[:100])

        # Parse JSON response
        parsed = json.loads(raw_text)
        number = parsed.get("pass_number")
        if number:
            return str(number)

    except json.JSONDecodeError as e:
        logger.warning("Azure OpenAI returned non-JSON: %s", e)
    except Exception as e:
        logger.warning("Azure OpenAI vision OCR failed: %s", e)

    return None


# ───────────────────────────────────────────────
# Public API
# ───────────────────────────────────────────────
def read_pass_number(image_bytes: bytes) -> str | None:
    """
    Try to extract the pass number from a pass photo.

    Returns:
        Normalised pass number string, or None if extraction failed.
    """
    # 1. QR / barcode
    result = _try_qr_opencv(image_bytes)
    if result:
        return normalise_pass_number(result)

    result = _try_pyzbar(image_bytes)
    if result:
        return normalise_pass_number(result)

    # 2. Azure OpenAI Vision
    result = _try_azure_openai_vision(image_bytes)
    if result:
        return normalise_pass_number(result)

    # 3. Fallback — caller should prompt for manual entry
    logger.info("All pass-number extraction methods failed; manual entry needed")
    return None


def verify_pass_number(
    extracted: str | None,
    manual: str | None,
    expected: str,
) -> tuple[bool, str, bool]:
    """
    Verify the extracted/manual pass number against the expected one.

    Returns:
        (is_valid, used_number, needs_review)
    """
    expected_norm = normalise_pass_number(expected)

    # Try extracted first
    if extracted:
        extracted_norm = normalise_pass_number(extracted)
        if extracted_norm == expected_norm:
            return True, extracted_norm, False

    # Try manual
    if manual:
        manual_norm = normalise_pass_number(manual)
        if manual_norm == expected_norm:
            return True, manual_norm, False

    # If extraction produced something but it doesn't match, and no manual provided
    if extracted and not manual:
        return False, normalise_pass_number(extracted), False

    # If nothing worked, flag for review
    if not extracted and not manual:
        return True, "", True  # Allow registration but flag for admin review

    # Manual provided but doesn't match
    return False, normalise_pass_number(manual or ""), False
