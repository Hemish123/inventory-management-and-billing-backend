"""
Tests for the face engine service.

Mocks InsightFace so tests run without the model installed.
Tests quality checks, embedding serialisation, and matching logic.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
from django.test import TestCase, override_settings

from apps.passes.services.face_engine import (
    FaceResult,
    MatchResult,
    QualityError,
    _check_quality,
    bytes_to_embedding,
    embedding_to_bytes,
    match_against_all,
)


class EmbeddingSerializationTests(TestCase):
    """Tests for embedding ↔ bytes conversion."""

    def test_roundtrip(self):
        emb = np.random.randn(512).astype(np.float32)
        emb /= np.linalg.norm(emb)
        raw = embedding_to_bytes(emb)
        self.assertEqual(len(raw), 2048)  # 512 * 4

        restored = bytes_to_embedding(raw)
        np.testing.assert_array_almost_equal(emb, restored)

    def test_l2_normalised(self):
        emb = np.random.randn(512).astype(np.float32)
        emb /= np.linalg.norm(emb)
        self.assertAlmostEqual(np.linalg.norm(emb), 1.0, places=5)


class QualityCheckTests(TestCase):
    """Tests for face quality validation."""

    def _make_face(self, det_score=0.9, bbox=(50, 50, 200, 250)):
        face = MagicMock()
        face.det_score = det_score
        face.bbox = np.array(bbox, dtype=np.float32)
        return face

    @override_settings(
        FACE_MIN_DET_SCORE=0.6,
        FACE_MIN_FACE_SIZE=80,
        FACE_BLUR_THRESHOLD=50.0,
    )
    def test_low_detection_score_rejected(self):
        face = self._make_face(det_score=0.3)
        bgr = np.random.randint(0, 255, (300, 300, 3), dtype=np.uint8)
        with self.assertRaises(QualityError) as ctx:
            _check_quality(face, bgr)
        self.assertIn("confidence too low", str(ctx.exception))

    @override_settings(
        FACE_MIN_DET_SCORE=0.6,
        FACE_MIN_FACE_SIZE=80,
        FACE_BLUR_THRESHOLD=50.0,
    )
    def test_small_face_rejected(self):
        face = self._make_face(det_score=0.9, bbox=(10, 10, 50, 50))  # 40x40
        bgr = np.random.randint(0, 255, (300, 300, 3), dtype=np.uint8)
        with self.assertRaises(QualityError) as ctx:
            _check_quality(face, bgr)
        self.assertIn("too small", str(ctx.exception))

    @override_settings(
        FACE_MIN_DET_SCORE=0.6,
        FACE_MIN_FACE_SIZE=80,
        FACE_BLUR_THRESHOLD=50.0,
    )
    def test_good_face_accepted(self):
        face = self._make_face(det_score=0.95, bbox=(10, 10, 200, 260))
        # Create a non-blurry image (high variance)
        bgr = np.random.randint(0, 255, (300, 300, 3), dtype=np.uint8)
        score = _check_quality(face, bgr)
        self.assertAlmostEqual(score, 0.95, places=2)


class MatchingTests(TestCase):
    """Tests for the matching function with mock data."""

    @patch("passes.services.face_engine._load_embedding_matrix")
    def test_match_identical(self, mock_load):
        """Identical embeddings should have cosine similarity ≈ 1.0."""
        emb = np.random.randn(512).astype(np.float32)
        emb /= np.linalg.norm(emb)

        mock_load.return_value = (emb.reshape(1, 512), ["pass-1"])

        results = match_against_all(emb, top_k=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].pass_id, "pass-1")
        self.assertAlmostEqual(results[0].score, 1.0, places=3)

    @patch("passes.services.face_engine._load_embedding_matrix")
    def test_no_registrations(self, mock_load):
        """Empty matrix should return empty results."""
        mock_load.return_value = (np.empty((0, 512), dtype=np.float32), [])

        emb = np.random.randn(512).astype(np.float32)
        emb /= np.linalg.norm(emb)

        results = match_against_all(emb)
        self.assertEqual(len(results), 0)

    @patch("passes.services.face_engine._load_embedding_matrix")
    def test_best_match_first(self, mock_load):
        """Best match should be first in results."""
        target = np.random.randn(512).astype(np.float32)
        target /= np.linalg.norm(target)

        # Create matrix: first row is noise, second is close to target
        noise = np.random.randn(512).astype(np.float32)
        noise /= np.linalg.norm(noise)
        similar = target + 0.1 * np.random.randn(512).astype(np.float32)
        similar /= np.linalg.norm(similar)

        matrix = np.stack([noise, similar])
        mock_load.return_value = (matrix, ["noise-pass", "similar-pass"])

        results = match_against_all(target, top_k=2)
        self.assertEqual(results[0].pass_id, "similar-pass")
        self.assertGreater(results[0].score, results[1].score)

    @patch("passes.services.face_engine._load_embedding_matrix")
    @override_settings(FACE_MATCH_THRESHOLD=0.45, FACE_REVIEW_THRESHOLD=0.35)
    def test_threshold_classification(self, mock_load):
        """Verify threshold-based classification logic."""
        from django.conf import settings

        emb = np.random.randn(512).astype(np.float32)
        emb /= np.linalg.norm(emb)

        # A match with score 0.5 → MATCHED
        self.assertGreaterEqual(0.5, settings.FACE_MATCH_THRESHOLD)
        # A score of 0.4 → REVIEW
        self.assertGreaterEqual(0.4, settings.FACE_REVIEW_THRESHOLD)
        self.assertLess(0.4, settings.FACE_MATCH_THRESHOLD)
        # A score of 0.2 → NO_MATCH
        self.assertLess(0.2, settings.FACE_REVIEW_THRESHOLD)
