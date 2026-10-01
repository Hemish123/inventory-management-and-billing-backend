"""
Management command: rebuild_embeddings

Reloads all face embeddings from the database into the in-memory cache.
Useful after manual DB edits or when switching workers.

Usage:
    python manage.py rebuild_embeddings
"""
from __future__ import annotations

import numpy as np

from django.core.management.base import BaseCommand

from passes.models import Registration
from passes.services.face_engine import invalidate_embedding_cache


class Command(BaseCommand):
    help = "Rebuild the in-memory face embedding cache from the database."

    def handle(self, *args, **options):
        count = Registration.objects.filter(pass_obj__status="REGISTERED").count()

        if count == 0:
            self.stdout.write(self.style.WARNING("No registered embeddings found."))
            return

        # Validate embeddings
        valid = 0
        invalid = 0
        for reg in Registration.objects.filter(pass_obj__status="REGISTERED"):
            try:
                emb = np.frombuffer(bytes(reg.face_embedding), dtype=np.float32)
                if emb.shape == (512,):
                    valid += 1
                else:
                    invalid += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f"  ✗ {reg.pass_obj.pass_number}: shape={emb.shape} (expected (512,))"
                        )
                    )
            except Exception as e:
                invalid += 1
                self.stdout.write(
                    self.style.ERROR(f"  ✗ {reg.pass_obj.pass_number}: {e}")
                )

        # Invalidate cache so next access reloads
        invalidate_embedding_cache()

        self.stdout.write(
            self.style.SUCCESS(
                f"\n✅ Embedding cache invalidated. "
                f"{valid} valid, {invalid} invalid out of {count} total."
            )
        )
