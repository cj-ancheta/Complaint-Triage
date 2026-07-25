# Local retention deadline checkpoint

Status: QA-109 accepted; GitHub Actions run 30164562588 passed

ADR 0009 requires deletion of covered local CFPB narratives and the PostgreSQL
volume by the end of 2026-11-19 Asia/Singapore (`2026-11-19T15:59:59Z`). The
checkpoint reports one of three deterministic states:

- `scheduled`: more than 30 days remain;
- `due_soon`: 30 days or fewer remain, including the final second; or
- `overdue`: the deadline has passed and cleanup is required.

The report contains only policy, time, state, remaining-day, command-template,
and privacy fields. It does not enumerate the filesystem, connect to
PostgreSQL, read raw bytes, upload data, or include narratives/complaint IDs.

## Automated reminder

The `Retention checkpoint` GitHub workflow runs every Monday and on manual
dispatch. It fails at `due_soon`, causing the repository's normal workflow
notification 30 days before the deadline. CI has no local raw data; this is a
deadline reminder, not deletion evidence and not a backup.

## Maintainer procedure

Run the local checkpoint at any time:

```powershell
$env:PYTHONPATH = "src"
python -m complaint_triage.retention_checkpoint --fail-on due_soon
```

Before the deadline, run `cleanup-real-data` first as a dry run, review its
aggregate inventory, then execute with the exact run ID confirmation. The
existing cleanup command deletes only manifest-named content-addressed files,
temporary parts, containers, and the PostgreSQL volume; it verifies absence and
writes aggregate deletion evidence under `data/manifests/cfpb/deletions/`.
Retain that small manifest in Git. Do not retain, copy, synchronize, or back up
the deleted narratives or volume.

The scheduled workflow does not replace this local procedure. After cleanup,
verify the deletion manifest, confirm the ignored raw directories contain no
covered artifacts, and record owner acceptance without reopening the frozen
test or model-selection workflow.

GitHub Actions run
[`30164562588`](https://github.com/cj-ancheta/Complaint-Triage/actions/runs/30164562588)
passed the standard, CPU-transformer, and security gates on the implementation
commit. The deadline remains an operational obligation until aggregate local
deletion evidence is recorded.
