# Private file reconciliation operations

The reconciliation command compares immutable database metadata with the configured private
filesystem. It verifies every template version and finalized generated artifact by existence, exact
byte size, and SHA-256 checksum. It also inventories the private root for unreferenced files,
interrupted immutable-write staging files, symlinks, special entries, and scan errors.

## Routine read-only check

Run the check from the same release and settings profile as the application:

```bash
.venv/bin/python manage.py reconcile_private_files --check --settings=config.settings.production
```

The command is safe to retry and is read-only by default. Schedule it at least daily and after every
backup restore. A successful run exits zero. Missing, modified, orphaned, unsafe, unreadable, or stale
staging content exits nonzero. An interrupted scan is not converted into a successful result.

Standard output contains one bounded JSON event named
`private_file_reconciliation_completed`. It contains a UTC timestamp, severity, correlation ID,
status, duration, and fixed-category counts. It never contains storage keys, display filenames, file
contents, snapshots, exception text, or user values. Forward this event to the operational log
pipeline and alert on a nonzero exit or a status other than `ok`.

## Stale staging cleanup

Ordinary checks never delete files. After confirming that no deployment or document generation is
still writing to the private volume, an operator may remove only immutable staging files that match
the application-owned staging-name contract and are at least 24 hours old:

```bash
.venv/bin/python manage.py reconcile_private_files --cleanup-stale-staging \
  --settings=config.settings.production
```

The cleanup mode cannot be combined with `--check`. It rechecks file type and age immediately before
unlinking, refuses symlinks and special files, and never removes a finalized template, generated
artifact, or other orphan. Re-running it is idempotent.

## Responding to findings

1. Quiesce template activation and document generation when a referenced file is missing, modified,
   unreadable, or unsafe.
2. Preserve logs and the coordinated database/filesystem recovery set. Do not overwrite a canonical
   artifact, edit its checksum metadata, or regenerate it in place.
3. Investigate filesystem access, deployment activity, backup history, and host integrity. The
   command intentionally omits sensitive paths; authorized operators may inspect the private volume
   directly under the deployment's access controls.
4. Do not delete a final-file orphan through this command. Retain or quarantine it through a separately
   authorized incident procedure until its origin and any database recovery need are understood.
5. Restore PostgreSQL and private files from the same recovery set when restoration is required. The
   target remains RTO at most eight hours and RPO at most 24 hours.
6. Re-run the read-only check, then verify representative authorized downloads against their recorded
   checksums. Record the restore time, recovery point, reconciliation event, download evidence, and
   remediation in the quarterly restore record.

Escalate any unexplained integrity finding before generation resumes. A zero result after cleanup does
not explain how an abandoned staging file was created; repeated staging findings require an application
or host investigation.
