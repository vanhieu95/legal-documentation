from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.documents.reconciliation import (
    PrivateStorageConfigurationError,
    reconcile_private_files,
)


class Command(BaseCommand):
    help = "Verify private template and generated artifact integrity against database metadata."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--check",
            action="store_true",
            help="Run the read-only integrity check and fail when a finding is detected.",
        )
        parser.add_argument(
            "--cleanup-stale-staging",
            action="store_true",
            help="Remove only recognized immutable staging files older than 24 hours.",
        )

    def handle(self, *args: object, **options: object) -> None:
        check_only = bool(options["check"])
        cleanup_stale_staging = bool(options["cleanup_stale_staging"])
        if check_only and cleanup_stale_staging:
            raise CommandError("--check and --cleanup-stale-staging cannot be combined.")
        try:
            report = reconcile_private_files(
                cleanup_stale_staging=cleanup_stale_staging,
            )
        except PrivateStorageConfigurationError as error:
            raise CommandError(str(error)) from None
        self.stdout.write(json.dumps(report.as_event(), separators=(",", ":"), sort_keys=True))
        if report.status != "ok":
            raise CommandError("Private file reconciliation detected integrity findings.")
