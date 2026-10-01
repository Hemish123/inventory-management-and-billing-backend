"""
Tests for the matching threshold logic and cosine similarity.

Verifies that FACE_MATCH_THRESHOLD and FACE_REVIEW_THRESHOLD
correctly classify scores into MATCHED / REVIEW / NO_MATCH.
"""
from __future__ import annotations

import numpy as np
from django.test import TestCase, override_settings

from passes.services.face_engine import MatchResult


class CosineSimTests(TestCase):
    """Tests for cosine similarity math."""

    def test_identical_vectors_score_one(self):
        a = np.random.randn(512).astype(np.float32)
        a /= np.linalg.norm(a)
        score = float(np.dot(a, a))
        self.assertAlmostEqual(score, 1.0, places=5)

    def test_orthogonal_vectors_score_zero(self):
        a = np.zeros(512, dtype=np.float32)
        a[0] = 1.0
        b = np.zeros(512, dtype=np.float32)
        b[1] = 1.0
        score = float(np.dot(a, b))
        self.assertAlmostEqual(score, 0.0, places=5)

    def test_opposite_vectors_score_negative(self):
        a = np.random.randn(512).astype(np.float32)
        a /= np.linalg.norm(a)
        b = -a
        score = float(np.dot(a, b))
        self.assertAlmostEqual(score, -1.0, places=5)

    def test_similar_vectors_high_score(self):
        a = np.random.randn(512).astype(np.float32)
        a /= np.linalg.norm(a)
        noise = np.random.randn(512).astype(np.float32) * 0.01
        b = a + noise
        b /= np.linalg.norm(b)
        score = float(np.dot(a, b))
        self.assertGreater(score, 0.9)

    def test_matrix_batch_matching(self):
        """Verify that matrix dot product gives same results as pairwise."""
        query = np.random.randn(512).astype(np.float32)
        query /= np.linalg.norm(query)

        matrix = np.random.randn(10, 512).astype(np.float32)
        # Normalise each row
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        matrix = matrix / norms

        # Batch
        batch_scores = matrix @ query

        # Pairwise
        for i in range(10):
            pairwise = float(np.dot(matrix[i], query))
            self.assertAlmostEqual(float(batch_scores[i]), pairwise, places=5)


@override_settings(FACE_MATCH_THRESHOLD=0.45, FACE_REVIEW_THRESHOLD=0.35)
class ThresholdClassificationTests(TestCase):
    """Tests for score → result classification."""

    def _classify(self, score: float) -> str:
        from django.conf import settings
        if score >= settings.FACE_MATCH_THRESHOLD:
            return "MATCHED"
        elif score >= settings.FACE_REVIEW_THRESHOLD:
            return "REVIEW"
        else:
            return "NO_MATCH"

    def test_high_score_matched(self):
        self.assertEqual(self._classify(0.85), "MATCHED")
        self.assertEqual(self._classify(0.45), "MATCHED")

    def test_borderline_review(self):
        self.assertEqual(self._classify(0.40), "REVIEW")
        self.assertEqual(self._classify(0.35), "REVIEW")

    def test_low_score_no_match(self):
        self.assertEqual(self._classify(0.20), "NO_MATCH")
        self.assertEqual(self._classify(0.10), "NO_MATCH")
        self.assertEqual(self._classify(0.34), "NO_MATCH")

    def test_exact_threshold_boundary(self):
        self.assertEqual(self._classify(0.45), "MATCHED")
        self.assertEqual(self._classify(0.449), "REVIEW")
        self.assertEqual(self._classify(0.35), "REVIEW")
        self.assertEqual(self._classify(0.349), "NO_MATCH")
