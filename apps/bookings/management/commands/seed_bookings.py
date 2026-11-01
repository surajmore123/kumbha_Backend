"""
Loads areas, amenities, transport providers and the officially sourced stays.
Adds only what's missing. Stays stay in draft unless --publish is given.
"""

import json
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.akhadas.models import ContentSource
from apps.bookings import models, seed_content as seed
from apps.temples.models import Temple
from apps.website.models import Listing, ListingCategory, ListingStatus, Trust

_IMAGES = Path(__file__).resolve().parents[3] / "learn" / "seed_images"


class Command(BaseCommand):
    help = "Load starting Booking & Stay data."

    def add_arguments(self, parser):
        parser.add_argument("--publish", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        status = ListingStatus.published if options["publish"] else ListingStatus.draft
        images = {e["key"]: e for e in json.loads((_IMAGES / "manifest.json").read_text(encoding="utf-8"))}

        for position, (slug, en, hi, mr, image_key, where) in enumerate(seed.AREAS, start=1):
            area, _ = models.StayArea.objects.get_or_create(
                slug=slug, defaults={"position": position, "name": en, "name_hi": hi, "name_mr": mr},
            )
            if isinstance(where, tuple):
                area.latitude, area.longitude = where
            elif where:
                temple = Temple.objects.filter(name__icontains=where.split(":")[1], is_active=True).first()
                if temple:
                    area.latitude, area.longitude = temple.latitude, temple.longitude
            area.save()
            if not area.image:
                entry = images[image_key]
                area.image_usage, area.image_credit = entry["usage"], entry["credit"]
                area.image_source_url = entry["source_url"]
                with (_IMAGES / entry["file"]).open("rb") as image:
                    area.image.save(entry["file"], File(image), save=True)

        for position, (slug, en, hi, mr) in enumerate(seed.AMENITIES, start=1):
            models.Amenity.objects.get_or_create(
                slug=slug, defaults={"position": position, "name": en, "name_hi": hi, "name_mr": mr},
            )

        sources = {}
        for key, data in seed.SOURCES.items():
            values = {**data, "accessed_on": seed.CHECKED}
            sources[key], _ = ContentSource.objects.get_or_create(
                title=values.pop("title"), url=values.pop("url"), defaults=values,
            )

        added = 0
        for item in seed.STAYS:
            if models.StayProfile.objects.filter(listing__name=item["name"]).exists():
                continue
            listing = Listing.objects.create(
                category=ListingCategory.hotels, name=item["name"], type=item["type_label"],
                town=item["town"], area=item["area_text"], price_from=item["price_from"],
                unit=item["unit"], trust=Trust.official, status=status, source="official",
            )
            stay = models.StayProfile.objects.create(
                listing=listing, stay_type=item["stay_type"],
                area=models.StayArea.objects.get(slug=item["area"]), address=item["address"],
                phone=item.get("phone", ""), email=item.get("email", ""),
                website_url=item["website_url"], booking_url=item.get("booking_url", ""),
                price_status=item["price_status"], last_verified_on=seed.CHECKED,
                verification_status="verified" if item["verified"] else "unverified",
            )
            stay.amenities.set(models.Amenity.objects.filter(slug__in=item["amenities"]))
            stay.sources.set(sources[key] for key in item["sources"])
            for position, (en, hi, mr, price) in enumerate(item["rooms"]):
                models.StayRoom.objects.create(
                    stay=stay, position=position, name=en, name_hi=hi, name_mr=mr, price=price,
                )
            for language in ("en", "hi", "mr"):
                overview, how, cancellation, note = item[language]
                models.StayText.objects.create(
                    parent=stay, language=language, overview=overview, booking_instructions=how,
                    cancellation_policy=cancellation, price_note=note,
                )
            added += 1

        for position, row in enumerate(seed.TRANSPORT, start=1):
            slug, mode, name, official, website, action, can_book, note, hi, mr, terms = row
            models.TransportProvider.objects.get_or_create(slug=slug, defaults={
                "position": position, "mode": mode, "name": name, "is_official": official,
                "website_url": website, "action_url": action, "can_book": can_book, "note": note,
                "note_hi": hi, "note_mr": mr, "terms_notes": terms, "last_verified_on": seed.CHECKED,
            })
        self.stdout.write(self.style.SUCCESS(f"Added {added} stays ({status})."))
