"""Turns an article's editor-friendly text into structured blocks for the app."""

import re

_IMAGE = re.compile(r"^\[\[image:([\w-]+)\]\]$")
_CALLOUT = re.compile(r"^!(info|warn)\s+(.+)$", re.S)
WORDS_PER_MINUTE = 180


def parse_blocks(body):
    blocks = []
    for chunk in re.split(r"\n\s*\n", (body or "").replace("\r\n", "\n")):
        chunk = chunk.strip()
        if not chunk:
            continue
        image = _IMAGE.match(chunk)
        callout = _CALLOUT.match(chunk)
        lines = chunk.split("\n")
        if image:
            blocks.append({"type": "image", "key": image.group(1)})
        elif callout:
            blocks.append({"type": "callout", "tone": callout.group(1), "text": callout.group(2).strip()})
        elif chunk.startswith("## "):
            blocks.append({"type": "heading", "text": chunk[3:].strip()})
        elif chunk.startswith("> "):
            blocks.append({"type": "quote", "text": " ".join(l.lstrip("> ").strip() for l in lines)})
        elif all(line.startswith("- ") for line in lines):
            blocks.append({"type": "list", "items": [line[2:].strip() for line in lines]})
        else:
            blocks.append({"type": "paragraph", "text": " ".join(line.strip() for line in lines)})
    return blocks


def reading_minutes(body):
    return max(1, round(len((body or "").split()) / WORDS_PER_MINUTE))
