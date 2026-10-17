"""Website CMS: editable page text and an image library, managed from the admin panel (Pages, Media).

Values are stored per key ("home.hero.title"). The website keeps a built-in default for every key
(kumbh-path src/lib/cms.ts), so only edited fields live here and resetting a field deletes its row.
"""

from typing import Annotated

from django.db import transaction
from django.http import HttpResponse
from pydantic import Field

from ..core import AppError, endpoint
from ..images import TYPES, dimensions, sniff
from ..models import MediaFile, SiteContent
from ..schemas import ContentEntry, ContentUpdate, MediaOut, Message, PageId

MAX_IMAGE_BYTES = 5 * 1024 * 1024


def media_url(m: MediaFile) -> str:
    """Path under /api/v1, e.g. /media/<id>.webp (the website adds its API base URL)."""
    return f"/media/{m.id}.{m.ext}"


def _media_out(m: MediaFile) -> MediaOut:
    return MediaOut(
        id=m.id,
        name=m.name,
        url=media_url(m),
        content_type=m.content_type,
        size=m.size,
        width=m.width,
        height=m.height,
        created_at=m.created_at,
    )


# ───────────────────────── public ─────────────────────────


@endpoint(path={"page": PageId})
def page_content(ctx, page: str):
    """Edited values for one page. Keys not listed use the website's built-in text."""
    ctx.headers["Cache-Control"] = "public, max-age=30"
    return dict(SiteContent.objects.filter(page=page).values_list("key", "value"))


@endpoint()
def media_file(ctx, filename: str):
    media_id, _, ext = filename.partition(".")
    row = MediaFile.objects.filter(pk=media_id[:32], ext=ext).values("data", "content_type").first()
    if not row:
        raise AppError(404, "not_found", "Image not found.")
    resp = HttpResponse(bytes(row["data"]), content_type=row["content_type"])
    # A file id never changes content, so browsers and CDNs may keep it for a year.
    resp["Cache-Control"] = "public, max-age=31536000, immutable"
    resp["Cross-Origin-Resource-Policy"] = "cross-origin"
    return resp


# ───────────────────────── admin: page text ─────────────────────────


def _entries(page: str) -> list[ContentEntry]:
    rows = SiteContent.objects.filter(page=page).select_related("updated_by")
    return [
        ContentEntry(key=r.key, value=r.value, updated_at=r.updated_at, updated_by_name=r.updated_by.name if r.updated_by else None) for r in rows
    ]


@endpoint(auth="admin", path={"page": PageId})
def admin_page_content(ctx, page: str):
    return _entries(page)


@endpoint(auth="admin", path={"page": PageId}, body=ContentUpdate)
def save_page_content(ctx, page: str):
    values = ctx.body.values
    for key in values:
        if not key.startswith(f"{page}."):
            raise AppError(422, "wrong_page", f"{key} does not belong to the {page} page.")
    with transaction.atomic():
        for key, value in values.items():
            if value is None:  # back to the built-in text
                SiteContent.objects.filter(key=key).delete()
            else:
                SiteContent.objects.update_or_create(key=key, defaults={"page": page, "value": value, "updated_by": ctx.admin})
    return _entries(page)


# ───────────────────────── admin: image library ─────────────────────────


@endpoint(auth="admin")
def list_media(ctx):
    rows = MediaFile.objects.defer("data").order_by("-created_at")[:500]
    return [_media_out(m) for m in rows]


@endpoint(
    auth="admin",
    query={"name": Annotated[str, Field(min_length=1, max_length=160)]},
    limit=("media-upload", 30),
    max_body=MAX_IMAGE_BYTES + 1024,
    status=201,
)
def upload_media(ctx):
    """Upload one image as the raw request body (PNG, JPEG, WebP or GIF, up to 5 MB)."""
    # Read the stream directly: request.body is capped by DATA_UPLOAD_MAX_MEMORY_SIZE (2.5 MB).
    data = ctx.request.read(MAX_IMAGE_BYTES + 1)
    if not data:
        raise AppError(422, "empty_file", "The file is empty.")
    if len(data) > MAX_IMAGE_BYTES:
        raise AppError(413, "payload_too_large", "Images can be at most 5 MB.")
    ext = sniff(data)
    if not ext:
        raise AppError(415, "unsupported_image", "Upload a PNG, JPEG, WebP or GIF image.")
    size = dimensions(data, ext)
    m = MediaFile.objects.create(
        name=(ctx.query.get("name") or "image").strip()[:160] or "image",
        content_type=TYPES[ext],
        ext=ext,
        size=len(data),
        width=size[0] if size else None,
        height=size[1] if size else None,
        data=data,
        uploaded_by=ctx.admin,
    )
    return _media_out(m)


@endpoint(auth="admin")
def delete_media(ctx, media_id: str):
    m = MediaFile.objects.defer("data").filter(pk=media_id[:32]).first()
    if not m:
        raise AppError(404, "not_found", "Image not found.")
    used = list(SiteContent.objects.filter(value=media_url(m)).values_list("key", flat=True))
    if used:
        raise AppError(409, "image_in_use", f"This image is used on the website ({', '.join(used)}). Choose another image there first.")
    m.delete()
    return Message(message="Image deleted")
