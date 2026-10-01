"""
Management command: create_demo_pass

Creates demo passes for testing. Outputs pass numbers and registration links.
Can also export as CSV.

Usage:
    python manage.py create_demo_pass                # creates 5 demo passes
    python manage.py create_demo_pass --count 20     # creates 20
    python manage.py create_demo_pass --csv demo.csv # export to CSV
    python manage.py create_demo_pass --prefix VIP   # prefix: VIP-0001
"""
from __future__ import annotations

import csv
import secrets
from io import StringIO

from django.core.management.base import BaseCommand

from passes.models import Pass


class Command(BaseCommand):
    help = "Create demo passes with unique tokens and pass numbers."

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=5,
            help="Number of passes to create (default: 5)",
        )
        parser.add_argument(
            "--prefix",
            type=str,
            default="PASS",
            help="Pass number prefix (default: PASS)",
        )
        parser.add_argument(
            "--pass-type",
            type=str,
            default="",
            help="Pass type label (e.g., VIP, General)",
        )
        parser.add_argument(
            "--csv",
            type=str,
            default="",
            help="Export to CSV file path",
        )

    def handle(self, *args, **options):
        count: int = options["count"]
        prefix: str = options["prefix"].upper()
        pass_type: str = options["pass_type"]
        csv_path: str = options["csv"]

        # Find the highest existing number with this prefix
        start = 1
        existing = (
            Pass.objects.filter(pass_number__startswith=f"{prefix}-")
            .order_by("-pass_number")
            .first()
        )
        if existing:
            try:
                start = int(existing.pass_number.split("-")[1]) + 1
            except (ValueError, IndexError):
                pass

        created_passes: list[Pass] = []
        for i in range(count):
            num = f"{prefix}-{start + i:04d}"
            p = Pass(
                pass_number=num,
                token=secrets.token_urlsafe(24),
                pass_type=pass_type,
            )
            created_passes.append(p)

        Pass.objects.bulk_create(created_passes, ignore_conflicts=True)

        self.stdout.write(
            self.style.SUCCESS(f"\n✅ Created {count} passes ({prefix}-{start:04d} → {prefix}-{start+count-1:04d}):\n")
        )

        # Print table
        self.stdout.write(f"{'Pass Number':<16} {'Token':<36} {'Status'}")
        self.stdout.write("-" * 90)
        for p in created_passes:
            self.stdout.write(f"{p.pass_number:<16} {p.token:<36} {p.status}")

        # CSV export
        if csv_path:
            with open(csv_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["pass_number", "token", "status"])
                for p in created_passes:
                    writer.writerow([p.pass_number, p.token, p.status])
            self.stdout.write(self.style.SUCCESS(f"\n📄 CSV exported to: {csv_path}"))
