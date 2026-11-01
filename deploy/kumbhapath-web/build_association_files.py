#!/usr/bin/env python3
"""
Builds the files https://kumbhapath.in/.well-known/ must serve, from
app_identity.json. Nothing here contacts a server.

    python build_association_files.py               # writes .well-known/
    python build_association_files.py --production  # also refuses to finish
                                                    # unless safe to publish
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LINK_PATH = "/join/family"
_FINGERPRINT = re.compile(r"^([0-9A-F]{2}:){31}[0-9A-F]{2}$")
_TEAM_ID = re.compile(r"^[A-Z0-9]{10}$")
MISSING_TEAM = "APPLE_TEAM_ID_REQUIRED"


def load_identity():
    return json.loads((HERE / "app_identity.json").read_text(encoding="utf8"))


def assetlinks(identity):
    # Debug fingerprints are listed so the app can be tested before release.
    # problems() stops them being published.
    fingerprints = [*identity["android_sha256"], *identity["android_debug_sha256"]]
    return [{
        "relation": ["delegate_permission/common.handle_all_urls"],
        "target": {
            "namespace": "android_app",
            "package_name": identity["android_package"],
            "sha256_cert_fingerprints": fingerprints,
        },
    }]


def apple(identity):
    team = identity["apple_team_id"] or MISSING_TEAM
    return {
        "applinks": {
            "details": [{
                "appIDs": [f"{team}.{identity['ios_bundle_id']}"],
                "components": [
                    {"/": LINK_PATH, "comment": "Family Safety Circle invitations"},
                    {"/": f"{LINK_PATH}/", "comment": "Same, with a trailing slash"},
                ],
            }],
        },
    }


def problems(identity):
    """Everything that makes these files unsafe or useless in production."""
    found = []
    for key in ("android_package", "ios_bundle_id"):
        if identity[key].startswith("com.example"):
            found.append(f"{key} is still a placeholder ({identity[key]}). Stores reject com.example.")
    release = identity["android_sha256"]
    if not release:
        found.append("android_sha256 is empty: add the release (Play app signing) SHA-256.")
    for fingerprint in release:
        if not _FINGERPRINT.match(fingerprint):
            found.append("android_sha256 has a value that isn't a SHA-256 fingerprint.")
        if fingerprint in identity["android_debug_sha256"]:
            found.append("android_sha256 includes the debug key. Anyone with it could receive invitations.")
    if not _TEAM_ID.match(identity["apple_team_id"] or ""):
        found.append("apple_team_id is missing or isn't a 10-character Team ID.")
    return found


def production_identity(identity):
    return {**identity, "android_debug_sha256": []}


def main():
    identity = load_identity()
    production = "--production" in sys.argv
    if production:
        found = problems(identity)
        if found:
            print("Not safe to publish:", file=sys.stderr)
            for problem in found:
                print(f"  - {problem}", file=sys.stderr)
            return 1
        identity = production_identity(identity)
    folder = HERE / ".well-known"
    folder.mkdir(exist_ok=True)
    (folder / "assetlinks.json").write_text(json.dumps(assetlinks(identity), indent=2) + "\n", encoding="utf8")
    (folder / "apple-app-site-association").write_text(
        json.dumps(apple(identity), indent=2) + "\n", encoding="utf8",
    )
    print(f"Wrote {folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
