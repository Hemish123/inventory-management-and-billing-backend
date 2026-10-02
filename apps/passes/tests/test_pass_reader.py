"""
Tests for the pass number reader service.

Mocks Azure OpenAI calls so tests run without API credentials.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.passes.services.pass_reader import (
    normalise_pass_number,
    read_pass_number,
    verify_pass_number,
)


class NormaliseTests(TestCase):
    """Tests for pass number normalisation."""

    def test_strip_whitespace(self):
        self.assertEqual(normalise_pass_number("  PASS-0001  "), "PASS-0001")

    def test_uppercase(self):
        self.assertEqual(normalise_pass_number("pass-0001"), "PASS-0001")

    def test_remove_noise(self):
        self.assertEqual(normalise_pass_number("PASS #0001"), "PASS0001")

    def test_preserve_dash(self):
        self.assertEqual(normalise_pass_number("VIP-1234"), "VIP-1234")

    def test_none(self):
        self.assertEqual(normalise_pass_number(None), "")

    def test_empty(self):
        self.assertEqual(normalise_pass_number(""), "")


class VerifyPassNumberTests(TestCase):
    """Tests for pass number verification logic."""

    def test_extracted_matches(self):
        is_valid, used, needs_review = verify_pass_number(
            extracted="PASS-0001",
            manual=None,
            expected="PASS-0001",
        )
        self.assertTrue(is_valid)
        self.assertEqual(used, "PASS-0001")
        self.assertFalse(needs_review)

    def test_manual_matches(self):
        is_valid, used, needs_review = verify_pass_number(
            extracted=None,
            manual="pass-0001",
            expected="PASS-0001",
        )
        self.assertTrue(is_valid)
        self.assertEqual(used, "PASS-0001")
        self.assertFalse(needs_review)

    def test_extracted_mismatch_no_manual(self):
        is_valid, used, needs_review = verify_pass_number(
            extracted="PASS-9999",
            manual=None,
            expected="PASS-0001",
        )
        self.assertFalse(is_valid)

    def test_manual_mismatch(self):
        is_valid, used, needs_review = verify_pass_number(
            extracted=None,
            manual="WRONG-1234",
            expected="PASS-0001",
        )
        self.assertFalse(is_valid)

    def test_nothing_extracted_no_manual_flags_review(self):
        is_valid, used, needs_review = verify_pass_number(
            extracted=None,
            manual=None,
            expected="PASS-0001",
        )
        self.assertTrue(is_valid)  # Allow but flag
        self.assertTrue(needs_review)

    def test_extracted_with_noise_matches(self):
        is_valid, used, needs_review = verify_pass_number(
            extracted="  pass - 0001 ",
            manual=None,
            expected="PASS-0001",
        )
        self.assertTrue(is_valid)

    def test_manual_fallback_when_extracted_wrong(self):
        is_valid, used, needs_review = verify_pass_number(
            extracted="WRONG-NUM",
            manual="PASS-0001",
            expected="PASS-0001",
        )
        self.assertTrue(is_valid)
        self.assertEqual(used, "PASS-0001")


class ReadPassNumberTests(TestCase):
    """Tests for the full read pipeline (mocking all backends)."""

    @patch("passes.services.pass_reader._try_azure_openai_vision", return_value=None)
    @patch("passes.services.pass_reader._try_pyzbar", return_value=None)
    @patch("passes.services.pass_reader._try_qr_opencv", return_value=None)
    def test_all_methods_fail_returns_none(self, mock_qr, mock_pyzbar, mock_azure):
        result = read_pass_number(b"fake_image_bytes")
        self.assertIsNone(result)

    @patch("passes.services.pass_reader._try_azure_openai_vision")
    @patch("passes.services.pass_reader._try_pyzbar", return_value=None)
    @patch("passes.services.pass_reader._try_qr_opencv", return_value="PASS-0042")
    def test_qr_succeeds_skips_rest(self, mock_qr, mock_pyzbar, mock_azure):
        result = read_pass_number(b"fake_image_bytes")
        self.assertEqual(result, "PASS-0042")
        mock_pyzbar.assert_not_called()
        mock_azure.assert_not_called()

    @patch("passes.services.pass_reader._try_azure_openai_vision", return_value="VIP-0007")
    @patch("passes.services.pass_reader._try_pyzbar", return_value=None)
    @patch("passes.services.pass_reader._try_qr_opencv", return_value=None)
    def test_azure_fallback(self, mock_qr, mock_pyzbar, mock_azure):
        result = read_pass_number(b"fake_image_bytes")
        self.assertEqual(result, "VIP-0007")
