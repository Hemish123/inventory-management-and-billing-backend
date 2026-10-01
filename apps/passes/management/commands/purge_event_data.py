"""
Management command: purge_event_data

Deletes face embeddings, photos (local + Azure), registrations, and entry logs
after the event is over. Keeps Pass records but resets their status.

⚠️  DESTRUCTIVE — requires --confirm flag.

Usage:
    python manage.py purge_event_data --confirm
    python manage.py purge_event_data --dry-run
    python manage.py purge_event_data --confirm --keep-logs  # keep entry logs
"""
from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from passes.models import EntryLog, Pass, Registration
from passes.services.face_engine import invalidate_embedding_cache

logger = logging.getLogger("passes")


class Command(BaseCommand):
    help = "Purge all face data, photos, and entry logs after the event."

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Required flag to confirm the destructive operation.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting.",
        )
        parser.add_argument(
            "--keep-logs",
            action="store_true",
            help="Keep EntryLog records (delete only registrations and photos).",
        )

    def handle(self, *args, **options):
        confirm: bool = options["confirm"]
        dry_run: bool = options["dry_run"]
        keep_logs: bool = options["keep_logs"]

        reg_count = Registration.objects.count()
        log_count = EntryLog.objects.count()

        self.stdout.write(f"\n📊 Current data:")
        self.stdout.write(f"   Registrations: {reg_count}")
        self.stdout.write(f"   Entry logs:    {log_count}")

        if dry_run:
            self.stdout.write(self.style.WARNING("\n🔍 DRY RUN — no data will be deleted."))
            self.stdout.write(f"   Would delete: {reg_count} registrations")
            if not keep_logs:
                self.stdout.write(f"   Would delete: {log_count} entry logs")
            self.stdout.write(f"   Would reset:  {Pass.objects.filter(status='REGISTERED').count()} passes to UNUSED")
            return

        if not confirm:
            self.stdout.write(
                self.style.ERROR(
                    "\n⚠️  This is a DESTRUCTIVE operation. Add --confirm to proceed."
                )
            )
            return

        # Delete local photo files
        if not settings.USE_AZURE_STORAGE:
            media_dirs = ["customer_photos", "pass_photos", "gate_scans"]
            for d in media_dirs:
                dir_path = Path(settings.MEDIA_ROOT) / d
                if dir_path.exists():
                    import shutil
                    shutil.rmtree(dir_path)
                    self.stdout.write(f"   🗑  Deleted local directory: {dir_path}")

        # Delete Azure blobs (if configured)
        if settings.USE_AZURE_STORAGE:
            self._purge_azure_blobs()

        # Delete registrations
        deleted_regs, _ = Registration.objects.all().delete()
        self.stdout.write(f"   🗑  Deleted {deleted_regs} registration(s)")

        # Delete entry logs
        if not keep_logs:
            deleted_logs, _ = EntryLog.objects.all().delete()
            self.stdout.write(f"   🗑  Deleted {deleted_logs} entry log(s)")

        # Reset pass statuses
        reset_count = Pass.objects.filter(status=Pass.Status.REGISTERED).update(
            status=Pass.Status.UNUSED
        )
        self.stdout.write(f"   🔄 Reset {reset_count} pass(es) to UNUSED")

        # Invalidate embedding cache
        invalidate_embedding_cache()

        self.stdout.write(self.style.SUCCESS("\n✅ Event data purged successfully."))

    def _purge_azure_blobs(self):
        """Delete all blobs in the Azure container."""
        try:
            from azure.storage.blob import BlobServiceClient

            if settings.AZURE_STORAGE_CONNECTION_STRING:
                client = BlobServiceClient.from_connection_string(
                    settings.AZURE_STORAGE_CONNECTION_STRING
                )
            else:
                client = BlobServiceClient(
                    account_url=f"https://{settings.AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net",
                    credential=settings.AZURE_STORAGE_ACCOUNT_KEY,
                )

            container = client.get_container_client(settings.AZURE_STORAGE_CONTAINER)
            blobs = list(container.list_blobs())
            for blob in blobs:
                container.delete_blob(blob.name)
            self.stdout.write(f"   🗑  Deleted {len(blobs)} Azure blob(s)")
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"   ⚠️  Azure blob purge failed: {e}"))
