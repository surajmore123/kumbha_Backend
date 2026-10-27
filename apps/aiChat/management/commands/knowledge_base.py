"""
Manage the Guru AI knowledge base (Qdrant collection `kumbh_knowledge`).

    python manage.py knowledge_base list
    python manage.py knowledge_base ingest knowledge/manifest.json [--dry-run]
    python manage.py knowledge_base remove --doc-id nmc-bathing-schedule-2027
    python manage.py knowledge_base mark-test --source-prefix local-test/

A manifest lists approved source files and their provenance, so schedules
and notices are updated by editing data, not Python:

    {
      "documents": [
        {
          "doc_id": "nmc-bathing-schedule-2027",
          "path": "sources/bathing-schedule.pdf",
          "title": "Simhastha 2027 bathing schedule",
          "organization": "Issuing authority name",
          "source_url": "https://…",
          "publication_date": "2026-01-15",
          "effective_date": "2027-07-01",
          "version": "1",
          "language": "en",
          "verification_status": "verified",
          "verified_by": "Name / how it was checked against the authority"
        }
      ]
    }

`verification_status: "verified"` is refused unless `verified_by` names
the evidence. Re-ingesting a doc_id replaces its earlier chunks.

The local Qdrant store is a folder (QDRANT_LOCAL_PATH, default
data/qdrant). Back it up by copying that folder while the server is
stopped before removing or re-labelling records.
"""

import json
import time
from collections import defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.aiChat.attachments.detection import detect_file
from apps.aiChat.attachments.documents import extract_document
from apps.aiChat.attachments.errors import AttachmentError
from apps.aiChat.rag import knowledge_service
from apps.aiChat.rag.ingestion_service import ingest_sections

_PROVENANCE = (
    "title", "organization", "source_url", "publication_date",
    "effective_date", "version", "language", "verification_status",
    "verified_by",
)


class Command(BaseCommand):
    help = "List, ingest, remove or re-label knowledge base documents."

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest="action", required=True)
        sub.add_parser("list", help="Summarise stored documents.")

        ingest = sub.add_parser("ingest", help="Ingest documents from a manifest.")
        ingest.add_argument("manifest")
        ingest.add_argument("--dry-run", action="store_true")
        ingest.add_argument(
            "--skip-existing", action="store_true",
            help="Leave documents whose doc_id is already stored (resume an interrupted run).",
        )

        remove = sub.add_parser("remove", help="Delete one document's chunks.")
        remove.add_argument("--doc-id")
        remove.add_argument("--source")

        mark = sub.add_parser("mark-test", help="Label synthetic records as test data.")
        mark.add_argument("--source-prefix", default="local-test/")

    def handle(self, *args, **options):
        action = options["action"]
        if action == "list":
            self._list()
        elif action == "ingest":
            self._ingest(
                Path(options["manifest"]), options["dry_run"], options["skip_existing"],
            )
        elif action == "remove":
            if not (options.get("doc_id") or options.get("source")):
                raise CommandError("Give --doc-id or --source.")
            count = knowledge_service.remove_documents(
                doc_id=options.get("doc_id"), source=options.get("source"),
            )
            self.stdout.write(self.style.SUCCESS(f"Removed {count} chunk(s)."))
        elif action == "mark-test":
            count = knowledge_service.set_verification_status(
                "test", options["source_prefix"],
            )
            self.stdout.write(self.style.SUCCESS(
                f"Labelled {count} chunk(s) under '{options['source_prefix']}' as test data."
            ))

    def _list(self):
        groups = defaultdict(lambda: {"chunks": 0})
        for point in knowledge_service.iterate_points():
            payload = point.payload or {}
            key = payload.get("doc_id") or payload.get("source", "?")
            group = groups[key]
            group["chunks"] += 1
            group["source"] = payload.get("source")
            group["status"] = payload.get("verification_status", "unlabelled")
            group["trusted"] = knowledge_service.is_trusted_payload(payload)
            group["title"] = payload.get("title", "")
        if not groups:
            self.stdout.write("The knowledge base is empty.")
        for key, group in sorted(groups.items()):
            usage = "used in answers" if group["trusted"] else "EXCLUDED from answers"
            self.stdout.write(
                f"{key}: {group['chunks']} chunk(s), status={group['status']}, "
                f"{usage}, source={group['source']} {group['title']}"
            )

    def _ingest(self, manifest: Path, dry_run: bool, skip_existing: bool = False):
        try:
            entries = json.loads(manifest.read_text(encoding="utf-8"))["documents"]
        except (OSError, ValueError, KeyError) as exc:
            raise CommandError(f"Can't read manifest: {exc}") from exc
        stored = (
            {(p.payload or {}).get("doc_id") for p in knowledge_service.iterate_points()}
            if skip_existing else set()
        )

        base = manifest.parent
        for entry in entries:
            doc_id = str(entry.get("doc_id") or "").strip()
            if not doc_id or not entry.get("path") or not entry.get("title"):
                raise CommandError("Every document needs doc_id, path and title.")
            status = entry.get("verification_status", "unverified")
            if status not in ("verified", "unverified"):
                raise CommandError(f"{doc_id}: verification_status must be verified or unverified.")
            if status == "verified" and not str(entry.get("verified_by") or "").strip():
                raise CommandError(
                    f"{doc_id}: 'verified' needs verified_by describing the evidence."
                )

            path = (base / entry["path"]).resolve()
            try:
                data = path.read_bytes()
                detected = detect_file(data, path.name, None)
                document = extract_document(data, detected.mime_type, path.name)
            except OSError as exc:
                raise CommandError(f"{doc_id}: can't read {path}: {exc}") from exc
            except AttachmentError as exc:
                raise CommandError(f"{doc_id}: rejected ({exc.code}).") from exc
            if document.scanned or not document.sections:
                raise CommandError(
                    f"{doc_id}: no text layer found. Provide a text version of the document."
                )

            if doc_id in stored:
                self.stdout.write(f"{doc_id}: already stored, skipped.")
                continue

            metadata = {"doc_id": doc_id}
            metadata.update({k: entry[k] for k in _PROVENANCE if entry.get(k)})
            metadata["verification_status"] = status
            source = entry.get("source_url") or f"doc:{doc_id}"

            if dry_run:
                self.stdout.write(
                    f"[dry run] {doc_id}: {len(document.sections)} section(s), "
                    f"{document.char_count} characters"
                    + (" (truncated)" if document.truncated else "")
                )
                continue
            count = self._with_quota_retry(
                doc_id,
                lambda: ingest_sections(
                    [{"text": s.text, "location": s.location} for s in document.sections],
                    source=source,
                    metadata=metadata,
                ),
            )
            self.stdout.write(self.style.SUCCESS(f"{doc_id}: stored {count} chunk(s)."))

    def _with_quota_retry(self, doc_id, step, attempts=6):
        """Embedding quotas are per minute (100 on the free tier): wait and retry."""
        for attempt in range(1, attempts + 1):
            try:
                return step()
            except Exception as exc:  # noqa: BLE001 - provider error types vary
                text = str(exc)
                if "RESOURCE_EXHAUSTED" not in text and "429" not in text:
                    raise
                if attempt == attempts:
                    raise CommandError(
                        f"{doc_id}: embedding quota still exhausted; run again later "
                        "with --skip-existing."
                    ) from exc
                self.stdout.write(f"{doc_id}: embedding quota reached, waiting 65 s ...")
                time.sleep(65)
