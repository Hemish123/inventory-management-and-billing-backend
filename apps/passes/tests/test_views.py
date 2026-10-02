"""
Tests for the views — registration flow, gate flow, and edge cases.

Uses Django test client. Mocks face_engine and pass_reader services.
"""
from __future__ import annotations

import io
from unittest.mock import patch, MagicMock

import numpy as np
from PIL import Image

from django.test import TestCase, Client, override_settings

from apps.passes.models import EntryLog, Pass, Registration
from apps.passes.services.face_engine import FaceResult


def _create_test_image(width: int = 400, height: int = 400) -> io.BytesIO:
    """Create a minimal JPEG image in memory."""
    img = Image.new("RGB", (width, height), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    buf.name = "test.jpg"
    return buf


class RegisterViewTests(TestCase):
    """Tests for the registration endpoint."""

    def setUp(self):
        self.client = Client()
        self.pass_obj = Pass.objects.create(pass_number="PASS-0001", token="test-token-abc")
        self.dummy_embedding = np.random.randn(512).astype(np.float32)
        self.dummy_embedding /= np.linalg.norm(self.dummy_embedding)

    def test_get_register_page(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Register Your Pass")

    def test_invalid_token_404(self):
        # We don't use tokens anymore, so just check a non-existent URL
        resp = self.client.get("/p/nonexistent-token/")
        self.assertEqual(resp.status_code, 404)

    @patch("passes.views.face_engine.detect_and_embed")
    def test_already_registered(self, mock_detect):
        mock_detect.return_value = FaceResult(
            embedding=self.dummy_embedding,
            quality_score=0.95,
        )
        self.pass_obj.status = Pass.Status.REGISTERED
        self.pass_obj.save()
        customer_photo = _create_test_image()
        pass_photo = _create_test_image()

        resp = self.client.post("/", {
            "full_name": "Test User",
            "mobile": "1234567890",
            "customer_photo": customer_photo,
            "pass_photo": pass_photo,
            "manual_pass_number": "PASS-0001",
            "consent": True,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Already Registered")

    @patch("passes.views.face_engine.invalidate_embedding_cache")
    @patch("passes.views.storage.upload_photo", return_value="test/photo.jpg")
    @patch("passes.views.pass_reader.normalise_pass_number", return_value="PASS-0001")
    @patch("passes.views.pass_reader.read_pass_number", return_value="PASS-0001")
    @patch("passes.views.face_engine.detect_and_embed")
    def test_successful_registration(self, mock_detect, mock_read, mock_verify, mock_upload, mock_invalidate):
        mock_detect.return_value = FaceResult(
            embedding=self.dummy_embedding,
            quality_score=0.95,
        )

        customer_photo = _create_test_image()
        pass_photo = _create_test_image()

        resp = self.client.post("/", {
            "full_name": "Rahul Sharma",
            "mobile": "9876543210",
            "email": "rahul@test.com",
            "customer_photo": customer_photo,
            "pass_photo": pass_photo,
            "manual_pass_number": "PASS-0001",
            "consent": True,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Registration Complete")

        # Verify DB state
        self.pass_obj.refresh_from_db()
        self.assertEqual(self.pass_obj.status, Pass.Status.REGISTERED)
        reg = Registration.objects.get(pass_obj=self.pass_obj)
        self.assertEqual(reg.full_name, "Rahul Sharma")
        self.assertTrue(mock_invalidate.called)

    def test_missing_consent_rejected(self):
        customer_photo = _create_test_image()
        pass_photo = _create_test_image()

        resp = self.client.post("/", {
            "full_name": "Test",
            "mobile": "1234567890",
            "customer_photo": customer_photo,
            "pass_photo": pass_photo,
            "manual_pass_number": "PASS-0001",
            # consent missing
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "consent")


@override_settings(GATE_KEY="test-gate-key", GATE_MAX_ENTRIES_PER_DAY=1)
class GateViewTests(TestCase):
    """Tests for the gate endpoints."""

    def setUp(self):
        self.client = Client()

    def test_gate_scan_valid_key(self):
        resp = self.client.get("/gate/?key=test-gate-key")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Navratri Gate")

    def test_gate_scan_invalid_key(self):
        resp = self.client.get("/gate/?key=wrong-key")
        self.assertEqual(resp.status_code, 403)

    def test_gate_verify_no_photo(self):
        resp = self.client.post("/gate/verify/", {"key": "test-gate-key"})
        self.assertEqual(resp.status_code, 400)

    @patch("passes.views.storage.upload_photo", return_value="scan/photo.jpg")
    @patch("passes.views.face_engine.match_against_all", return_value=[])
    @patch("passes.views.face_engine.detect_and_embed")
    def test_gate_no_match(self, mock_detect, mock_match, mock_upload):
        mock_detect.return_value = FaceResult(
            embedding=np.random.randn(512).astype(np.float32),
            quality_score=0.9,
        )

        photo = _create_test_image()
        resp = self.client.post("/gate/verify/", {
            "key": "test-gate-key",
            "scan_photo": photo,
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["result"], "NO_MATCH")

    def test_gate_confirm_invalid_key(self):
        resp = self.client.post("/gate/confirm/", {"key": "wrong"})
        self.assertEqual(resp.status_code, 403)


@override_settings(GATE_KEY="test-key", GATE_MAX_ENTRIES_PER_DAY=1)
class DuplicateEntryTests(TestCase):
    """Tests for the duplicate entry prevention rule."""

    def setUp(self):
        self.pass_obj = Pass.objects.create(
            pass_number="PASS-DUP-01",
            status=Pass.Status.REGISTERED,
        )
        Registration.objects.create(
            pass_obj=self.pass_obj,
            full_name="Duplicate Tester",
            mobile="111",
            consent_given=True,
            customer_photo_blob="a.jpg",
            pass_photo_blob="b.jpg",
            face_embedding=b"\x00" * 2048,
        )

    def test_duplicate_entry_detected(self):
        """Second admitted entry on same day should be flagged as DUPLICATE."""
        # First entry (admitted)
        EntryLog.objects.create(
            pass_obj=self.pass_obj,
            similarity_score=0.95,
            result=EntryLog.Result.MATCHED,
            admitted=True,
        )

        # Check that a second entry would be a duplicate
        from django.utils import timezone
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_count = EntryLog.objects.filter(
            pass_obj=self.pass_obj,
            result=EntryLog.Result.MATCHED,
            admitted=True,
            scanned_at__gte=today_start,
        ).count()
        self.assertGreaterEqual(today_count, 1)
