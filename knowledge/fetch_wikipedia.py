"""
Download Wikipedia articles used as background knowledge for Guru AI and
write a manifest for `python manage.py knowledge_base ingest`.

    python knowledge/fetch_wikipedia.py

Wikipedia text is CC BY-SA 4.0; each file records its source URL and
revision so answers can be attributed. These are background sources
(verification_status "unverified"): official schedules come from the
events database, never from here.
"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

UA = "KumbhaPath-knowledge-ingestion/1.0 (pilgrim assistant app)"
HERE = Path(__file__).resolve().parent
OUT = HERE / "sources" / "wikipedia"

ARTICLES = [
    "Kumbh Mela",
    "Nashik-Trimbakeshwar Simhastha",
    "2015 Nashik-Trimbakeshwar Simhastha",
    "Nashik",
    "History of Nashik",
    "Trimbak",
    "Trimbakeshwar Temple",
    "Kalaram Temple",
    "Godavari River",
    "Akhara",
    "Naga Sadhu",
]

# Sections that are lists of links or references, not knowledge.
_DROP_SECTIONS = re.compile(
    r"^==+\s*(See also|References|External links|Further reading|Notes|Bibliography|Sources|Citations)\s*==+\s*$",
    re.I,
)


def fetch(title):
    params = {
        "action": "query", "prop": "extracts|revisions|info", "explaintext": 1,
        "rvprop": "ids|timestamp", "inprop": "url", "redirects": 1,
        "format": "json", "titles": title,
    }
    url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                pages = json.load(response)["query"]["pages"]
                return next(iter(pages.values()))
        except Exception:  # noqa: BLE001 - polite retry with backoff
            time.sleep(5 * (attempt + 1))
    return None


def clean(text):
    kept, skipping = [], False
    for line in text.splitlines():
        if line.startswith("=="):
            skipping = bool(_DROP_SECTIONS.match(line.strip()))
        if not skipping:
            kept.append(line)
    text = "\n".join(kept)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def slug(title):
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    documents = []
    for title in ARTICLES:
        page = fetch(title)
        time.sleep(2)
        if not page or "missing" in page or not page.get("extract"):
            print(f"skipped (not found): {title}", file=sys.stderr)
            continue
        text = clean(page["extract"])
        revision = page["revisions"][0]
        name = slug(page["title"])
        url = page.get("fullurl") or f"https://en.wikipedia.org/wiki/{urllib.parse.quote(page['title'])}"
        header = (
            f"Source: Wikipedia, \"{page['title']}\" ({url}), revision {revision['revid']} "
            f"of {revision['timestamp'][:10]}. Text licensed CC BY-SA 4.0.\n\n"
        )
        (OUT / f"{name}.txt").write_text(header + text + "\n", encoding="utf-8")
        documents.append({
            "doc_id": f"wikipedia-{name}",
            "path": f"sources/wikipedia/{name}.txt",
            "title": f"Wikipedia: {page['title']}",
            "organization": "Wikipedia (CC BY-SA 4.0)",
            "source_url": url,
            "publication_date": revision["timestamp"][:10],
            "version": str(revision["revid"]),
            "language": "en",
            "verification_status": "unverified",
        })
        print(f"saved {name}.txt ({len(text)} chars)")

    manifest = HERE / "wikipedia_manifest.json"
    manifest.write_text(
        json.dumps({"retrieved": date.today().isoformat(), "documents": documents}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"manifest: {manifest} ({len(documents)} documents)")


if __name__ == "__main__":
    main()
