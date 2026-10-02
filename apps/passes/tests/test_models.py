"""Tests for the Pass, Registration, and EntryLog models."""
from __future__ import annotations

import uuid

from django.test import TestCase

from apps.passes.models import EntryLog, Pass, Registration


class PassModelTests(TestCase):
    """Tests for the Pass model."""

    def test_create_pass(self):
        p = Pass.objects.create(pass_number="PASS-0001")
        self.assertEqual(p.pass_number, "PASS-0001")
        self.assertEqual(p.status, Pass.Status.UNUSED)
        self.assertTrue(len(p.token) > 20)  # token_urlsafe(24)
        self.assertIsInstance(p.id, uuid.UUID)

    def test_pass_str(self):
        p = Pass.objects.create(pass_number="PASS-0002")
        self.assertIn("PASS-0002", str(p))
        self.assertIn("UNUSED", str(p))

    def test_token_unique(self):
        p1 = Pass.objects.create(pass_number="PASS-0010", token="tok1")
        with self.assertRaises(Exception):
            Pass.objects.create(pass_number="PASS-0011", token="tok1")

    def test_pass_number_unique(self):
        Pass.objects.create(pass_number="PASS-0020")
        with self.assertRaises(Exception):
            Pass.objects.create(pass_number="PASS-0020")

    def test_registration_url(self):
        p = Pass.objects.create(pass_number="PASS-0030", token="abc123")
        self.assertEqual(p.registration_url, "/p/abc123/")

    def test_is_registered(self):
        p = Pass.objects.create(pass_number="PASS-0040", status=Pass.Status.REGISTERED)
        self.assertTrue(p.is_registered)


class RegistrationModelTests(TestCase):
    """Tests for the Registration model."""

    def test_create_registration(self):
        p = Pass.objects.create(pass_number="PASS-0100")
        reg = Registration.objects.create(
            pass_obj=p,
            full_name="Test User",
            mobile="9876543210",
            consent_given=True,
            customer_photo_blob="test/photo.jpg",
            pass_photo_blob="test/pass.jpg",
            face_embedding=b"\x00" * 2048,  # 512 * 4 bytes
        )
        self.assertEqual(reg.full_name, "Test User")
        self.assertIn("Test User", str(reg))

    def test_one_to_one_constraint(self):
        p = Pass.objects.create(pass_number="PASS-0101")
        Registration.objects.create(
            pass_obj=p,
            full_name="User 1",
            mobile="111",
            consent_given=True,
            customer_photo_blob="a.jpg",
            pass_photo_blob="b.jpg",
            face_embedding=b"\x00" * 2048,
        )
        with self.assertRaises(Exception):
            Registration.objects.create(
                pass_obj=p,
                full_name="User 2",
                mobile="222",
                consent_given=True,
                customer_photo_blob="c.jpg",
                pass_photo_blob="d.jpg",
                face_embedding=b"\x00" * 2048,
            )


class EntryLogModelTests(TestCase):
    """Tests for the EntryLog model."""

    def test_create_entry_log_with_pass(self):
        p = Pass.objects.create(pass_number="PASS-0200")
        log = EntryLog.objects.create(
            pass_obj=p,
            similarity_score=0.92,
            result=EntryLog.Result.MATCHED,
        )
        self.assertEqual(log.result, "MATCHED")
        self.assertFalse(log.admitted)
        self.assertIn("PASS-0200", str(log))

    def test_create_entry_log_without_pass(self):
        log = EntryLog.objects.create(
            pass_obj=None,
            similarity_score=0.15,
            result=EntryLog.Result.NO_MATCH,
        )
        self.assertIsNone(log.pass_obj)
        self.assertIn("—", str(log))

    def test_admitted_flag(self):
        p = Pass.objects.create(pass_number="PASS-0201")
        log = EntryLog.objects.create(
            pass_obj=p,
            similarity_score=0.88,
            result=EntryLog.Result.MATCHED,
        )
        log.admitted = True
        log.save()
        log.refresh_from_db()
        self.assertTrue(log.admitted)
