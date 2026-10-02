"""
Face detection, embedding, and matching engine.

Uses InsightFace (ArcFace, buffalo_l model pack) with ONNX Runtime.
Model is loaded ONCE per process (lazy singleton with threading lock).

Key functions:
    detect_and_embed(image_bytes) -> (embedding, quality_score)
    match_against_all(embedding) -> list of (pass_id, score) sorted desc
    invalidate_embedding_cache() -> bump version so all workers reload

Matching uses an in-memory numpy matrix of L2-normalised 512-d embeddings.
Cosine similarity is computed via a single matrix–vector dot product.

Thresholds (from settings):
    >= FACE_MATCH_THRESHOLD  → MATCHED
    >= FACE_REVIEW_THRESHOLD → REVIEW
    <  FACE_REVIEW_THRESHOLD → NO_MATCH
"""
from __future__ import annotations

import logging
import struct
import threading
from io import BytesIO
from typing import Any, NamedTuple

import cv2
import numpy as np
from PIL import Image, ImageOps

logger = logging.getLogger("passes")

# ───────────────────────────────────────────────
# Singleton model
# ───────────────────────────────────────────────
_model: Any | None = None
_model_lock = threading.Lock()


def _get_model() -> Any:
    """Lazy-load the InsightFace model (once per worker process)."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                import insightface
                from django.conf import settings

                providers = (
                    ["CUDAExecutionProvider", "CPUExecutionProvider"]
                    if settings.FACE_USE_GPU
                    else ["CPUExecutionProvider"]
                )
                _model = insightface.app.FaceAnalysis(
                    name=settings.FACE_MODEL_PACK,
                    providers=providers,
                )
                ctx_id = 0 if settings.FACE_USE_GPU else -1
                _model.prepare(ctx_id=ctx_id, det_size=(640, 640))
                logger.info("InsightFace model loaded (pack=%s, gpu=%s)", settings.FACE_MODEL_PACK, settings.FACE_USE_GPU)
    return _model


# ───────────────────────────────────────────────
# Image pre-processing
# ───────────────────────────────────────────────
def _preprocess_image(image_bytes: bytes) -> np.ndarray:
    """
    Load image bytes → fix EXIF orientation → resize if huge → convert to
    BGR numpy array (what InsightFace expects).
    """
    img = Image.open(BytesIO(image_bytes))
    # Fix EXIF rotation
    img = ImageOps.exif_transpose(img)
    # Convert to RGB
    img = img.convert("RGB")
    # Resize very large images to save compute (max 1920 on longest side)
    max_side = 1920
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.LANCZOS)
    # PIL RGB → numpy BGR (for OpenCV / InsightFace)
    arr = np.array(img)[:, :, ::-1].copy()
    return arr


# ───────────────────────────────────────────────
# Quality checks
# ───────────────────────────────────────────────
class QualityError(Exception):
    """Raised when the customer photo fails quality checks."""

    pass


def _check_quality(face: Any, bgr_img: np.ndarray) -> float:
    """
    Run quality checks on a detected face.
    Returns the detection score. Raises QualityError on failure.
    """
    from django.conf import settings

    det_score: float = float(face.det_score)
    if det_score < settings.FACE_MIN_DET_SCORE:
        raise QualityError(
            f"Face detection confidence too low ({det_score:.2f}). "
            "Please upload a clearer, well-lit photo."
        )

    # Face bounding box size
    bbox = face.bbox.astype(int)
    face_w = bbox[2] - bbox[0]
    face_h = bbox[3] - bbox[1]
    min_size = settings.FACE_MIN_FACE_SIZE
    if face_w < min_size or face_h < min_size:
        raise QualityError(
            f"Face is too small in the image ({face_w}×{face_h}px). "
            f"Minimum is {min_size}×{min_size}px. Move closer to the camera."
        )

    # Blur check (Laplacian variance on the face crop)
    x1, y1, x2, y2 = bbox
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(bgr_img.shape[1], x2), min(bgr_img.shape[0], y2)
    face_crop = bgr_img[y1:y2, x1:x2]
    if face_crop.size > 0:
        gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
        lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        if lap_var < 10.0:  # Reduced from settings threshold for webcam friendliness
            raise QualityError(
                f"Photo appears blurry (sharpness={lap_var:.1f}). "
                "Please take a sharper photo."
            )
        # Simple brightness check
        mean_brightness = gray.mean()
        if mean_brightness < 10:  # Reduced from 40
            raise QualityError("Photo is too dark. Please use better lighting.")
        if mean_brightness > 250:
            raise QualityError("Photo is overexposed. Please reduce lighting.")

    return det_score


# ───────────────────────────────────────────────
# Core functions
# ───────────────────────────────────────────────
class FaceResult(NamedTuple):
    embedding: np.ndarray   # float32, shape (512,), L2-normalised
    quality_score: float


def detect_and_embed(image_bytes: bytes) -> FaceResult:
    """
    Detect faces and compute embedding from an image.

    Returns:
        FaceResult with L2-normalised 512-d embedding and quality score.
    Raises:
        QualityError if 0 faces, >1 face, blurry, too small, etc.
    """
    bgr = _preprocess_image(image_bytes)
    model = _get_model()
    faces = model.get(bgr)

    if len(faces) == 0:
        raise QualityError(
            "No face detected in the photo. Please upload a clear, "
            "front-facing photo with your full face visible."
        )
        
    # If multiple faces, pick the largest one (the main subject)
    if len(faces) > 1:
        faces = sorted(
            faces,
            key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]),
            reverse=True,
        )

    face = faces[0]
    quality = _check_quality(face, bgr)

    emb = face.normed_embedding  # Already L2-normalised by InsightFace
    emb = emb.astype(np.float32)
    # Double-check normalisation
    norm = np.linalg.norm(emb)
    if norm > 0:
        emb = emb / norm

    return FaceResult(embedding=emb, quality_score=quality)


def embedding_to_bytes(embedding: np.ndarray) -> bytes:
    """Serialize a 512-d float32 embedding to raw bytes (2048 bytes)."""
    return embedding.astype(np.float32).tobytes()


def bytes_to_embedding(data: bytes) -> np.ndarray:
    """Deserialize raw bytes back to a 512-d float32 numpy array."""
    return np.frombuffer(data, dtype=np.float32).copy()


# ───────────────────────────────────────────────
# Embedding matrix cache (for fast gate matching)
# ───────────────────────────────────────────────
_embedding_cache: dict[str, Any] = {
    "version": None,
    "matrix": None,
    "pass_ids": None,
}
_cache_lock = threading.Lock()


def invalidate_embedding_cache() -> None:
    """
    Bump the embedding version in Django cache.
    All workers will reload the matrix on next match attempt.
    """
    from django.core.cache import cache

    version = cache.get("embedding_version", 0)
    cache.set("embedding_version", version + 1, timeout=None)
    logger.info("Embedding cache invalidated (new version=%d)", version + 1)


def _load_embedding_matrix() -> tuple[np.ndarray, list]:
    """
    Load all registered embeddings into a numpy matrix.
    Uses a version counter in Django cache so multiple workers stay in sync.
    """
    from django.core.cache import cache
    from apps.passes.models import Registration

    current_version = cache.get("embedding_version", 0)

    # Fast path: cache is current
    if (
        _embedding_cache["version"] == current_version
        and _embedding_cache["matrix"] is not None
    ):
        return _embedding_cache["matrix"], _embedding_cache["pass_ids"]

    with _cache_lock:
        # Double-check after acquiring lock
        current_version = cache.get("embedding_version", 0)
        if (
            _embedding_cache["version"] == current_version
            and _embedding_cache["matrix"] is not None
        ):
            return _embedding_cache["matrix"], _embedding_cache["pass_ids"]

        registrations = list(
            Registration.objects.select_related("pass_obj")
            .filter(pass_obj__status="REGISTERED")
            .values_list("pass_obj_id", "face_embedding")
        )

        if not registrations:
            _embedding_cache["version"] = current_version
            _embedding_cache["matrix"] = np.empty((0, 512), dtype=np.float32)
            _embedding_cache["pass_ids"] = []
            return _embedding_cache["matrix"], _embedding_cache["pass_ids"]

        pass_ids = []
        embeddings = []
        for pass_id, emb_data in registrations:
            pass_ids.append(pass_id)
            emb = np.frombuffer(bytes(emb_data), dtype=np.float32).copy()
            embeddings.append(emb)

        matrix = np.stack(embeddings)
        _embedding_cache["version"] = current_version
        _embedding_cache["matrix"] = matrix
        _embedding_cache["pass_ids"] = pass_ids

        logger.info(
            "Embedding matrix loaded: %d registrations (cache version=%d)",
            len(pass_ids),
            current_version,
        )
        return matrix, pass_ids


class MatchResult(NamedTuple):
    pass_id: Any
    score: float


def match_against_all(embedding: np.ndarray, top_k: int = 5) -> list[MatchResult]:
    """
    Compare a query embedding against all registered embeddings.

    Args:
        embedding: L2-normalised 512-d float32 array
        top_k: max number of results to return

    Returns:
        List of MatchResult(pass_id, score) sorted by score descending.
        Empty list if no registrations exist.
    """
    matrix, pass_ids = _load_embedding_matrix()
    if matrix.shape[0] == 0:
        return []

    # Cosine similarity via dot product (both sides L2-normalised)
    scores = matrix @ embedding  # shape (N,)
    top_indices = np.argsort(scores)[::-1][:top_k]

    results = []
    for idx in top_indices:
        results.append(MatchResult(pass_id=pass_ids[idx], score=float(scores[idx])))
    return results


# ───────────────────────────────────────────────
# Optional: pgvector implementation stub
# ───────────────────────────────────────────────
# To switch to pgvector for large-scale deployments:
#
# 1. Add to Registration model:
#    from pgvector.django import VectorField
#    face_embedding_vector = VectorField(dimensions=512)
#
# 2. Replace match_against_all() with:
#    from pgvector.django import CosineDistance
#    Registration.objects.annotate(
#        distance=CosineDistance('face_embedding_vector', query_embedding)
#    ).order_by('distance')[:top_k]
#
# 3. Install: pip install pgvector django-pgvector
#    CREATE EXTENSION vector; in PostgreSQL
