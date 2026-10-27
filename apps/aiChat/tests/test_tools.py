import os
from datetime import date, timedelta
from unittest import mock

from django.test import SimpleTestCase
from django.utils import timezone

from apps.aiChat.rag import knowledge_service
from apps.aiChat.services import crowd_service, event_service, temple_service
from apps.aiChat.services.geo import map_links
from apps.aiChat.services.intent_service import detect_intents, primary_route
from apps.aiChat.tests.helpers import (
    GuruTestCase,
    make_event,
    make_incident,
    make_snapshot,
    make_temple,
    make_zone,
)


class EventToolTests(GuruTestCase):
    def test_only_visible_upcoming_events(self):
        keep = make_event("Keep")
        make_event("Past", days=-1)
        make_event("Hidden", show_in_app=False)
        make_event("Deleted", del_flag=1)
        make_event("Expired", auto_expire=True, expiry_date=date.today() - timedelta(days=1))
        make_event("Draft", status="DRAFT")
        names = [e["name"] for e in event_service.get_upcoming_verified_events()]
        self.assertEqual(names, ["Keep"])
        [event] = event_service.get_upcoming_verified_events()
        self.assertEqual(event["id"], str(keep.event_id))
        self.assertEqual(event["data_source"], "GOVT")

    def test_recently_changed_events(self):
        make_event("Changed")
        reply_events = event_service.get_recently_updated_events(days=1)
        self.assertEqual([e["name"] for e in reply_events], ["Changed"])

    def test_recent_change_question_routes_to_recent_mode(self):
        model = self.mock_model("ok")
        make_event("Changed Snan")
        self.reply(self.send("Which events have changed recently?"))
        self.assertIn("records changed recently", self.prompt_text(model))


class TempleToolTests(GuruTestCase):
    def test_alias_and_devanagari_matching(self):
        make_temple()
        make_temple("Sri Kala Rama Swamy Temple", "20.006800", "73.795200")
        names = temple_service.Temple.objects.values_list("name", flat=True)
        self.assertEqual(
            temple_service.match_temple_names("How do I reach Trimbak?", names),
            ["Trimbakeshwar Jyotirling Mandir"],
        )
        self.assertEqual(
            temple_service.match_temple_names("काळाराम मंदिर कुठे आहे?", names),
            ["Sri Kala Rama Swamy Temple"],
        )
        self.assertEqual(temple_service.match_temple_names("Is Nashik busy?", names), [])

    def test_navigation_links_are_validated(self):
        self.assertEqual(map_links(0, 0), {"map_url": None, "directions_url": None})
        self.assertEqual(map_links("x", 73), {"map_url": None, "directions_url": None})
        links = map_links(19.9324, 73.5308)
        self.assertEqual(
            links["directions_url"],
            "https://www.google.com/maps/dir/?api=1&destination=19.932400%2C73.530800",
        )

    def test_nearest_temples_from_location(self):
        model = self.mock_model("ok")
        make_temple()
        near = make_temple("Shree Kapaleshwar Mahadev Mandir", "19.998500", "73.792000")
        reply = self.reply(self.send("Which temples are near me?", latitude=19.9975, longitude=73.7910))
        self.assertEqual(reply["metadata"]["temples"][0]["id"], str(near.temple_id))
        self.assertIn("distance_km", reply["metadata"]["temples"][0])
        self.assertIn("nearest to the user's shared location", self.prompt_text(model))

    def test_general_temple_question_lists_database_temples(self):
        model = self.mock_model("ok")
        make_temple()
        self.reply(self.send("which temples should I visit?"))
        self.assertIn("no specific temple was named", self.prompt_text(model))

    def test_temple_advisory_is_not_presented_as_live(self):
        model = self.mock_model("ok")
        make_temple(crowd_level="High", crowd_message="Expect queues")
        self.reply(self.send("Tell me about Trimbakeshwar"))
        self.assertIn("admin advisory crowd level: High (Expect queues)", self.prompt_text(model))


class CrowdToolTests(GuruTestCase):
    def test_missing_crowd_data_gives_fixed_reply(self):
        model = self.mock_model()
        make_zone()
        reply = self.reply(self.send("Is Ramkund crowded?"))
        self.assertIn("No crowd measurements are available", reply["content"])
        model.assert_not_called()

    def test_fresh_crowd_data_has_freshness_footer(self):
        self.mock_knowledge()
        model = self.mock_model("Ramkund is moderately busy.")
        zone = make_zone()
        make_snapshot(zone, minutes_ago=3)
        reply = self.reply(self.send("How crowded is Ramkund right now?"))
        self.assertIn("status MEDIUM, occupancy 55.0%", self.prompt_text(model))
        self.assertIn("(3 min ago)", reply["content"])
        self.assertFalse(reply["metadata"]["crowd"]["freshness"]["stale"])

    def test_stale_crowd_data_is_flagged(self):
        self.mock_knowledge()
        model = self.mock_model("It was busy.")
        zone = make_zone()
        make_snapshot(zone, minutes_ago=600)
        reply = self.reply(self.send("Is Ramkund crowded?"))
        self.assertIn("STALE", self.prompt_text(model))
        self.assertIn("may not reflect current conditions", reply["content"])
        self.assertTrue(reply["metadata"]["crowd"]["freshness"]["stale"])

    def test_active_incidents_only(self):
        zone = make_zone()
        active = make_incident(zone)
        make_incident(zone, title="Old", end_time=timezone.now() - timedelta(minutes=1))
        make_incident(zone, title="Closed", is_active=False)
        make_incident(zone, title="Future", start_time=timezone.now() + timedelta(hours=1))
        incidents = crowd_service.get_active_incidents()
        self.assertEqual([i["id"] for i in incidents], [str(active.id)])

    def test_temple_crowd_uses_nearby_zone_not_advisory(self):
        self.mock_knowledge()
        model = self.mock_model("ok")
        make_temple("Shree Kapaleshwar Mahadev Mandir", "19.998500", "73.792000")
        zone = make_zone()
        make_snapshot(zone, minutes_ago=2, status="HIGH", occupancy=88.0)
        self.reply(self.send("Is Kapaleshwar temple crowded?"))
        prompt = self.prompt_text(model)
        self.assertIn("Ramkund: status HIGH", prompt)

    def test_safety_question_gets_incidents_and_no_invented_numbers_rule(self):
        self.mock_knowledge()
        model = self.mock_model("Go to the nearest police help desk.")
        zone = make_zone()
        make_incident(zone, incident_type="MEDICAL", title="Medical camp moved")
        self.reply(self.send("I lost my child, what should I do? Emergency help"))
        self.assertIn("Medical camp moved", self.prompt_text(model))
        self.assertIn("Do not state any phone number that is not in the evidence", self.system_prompt(model))


class KnowledgeTests(GuruTestCase):
    def test_rag_answer_cites_sources_with_provenance(self):
        model = self.mock_model("Ramkund is the main bathing ghat.")
        self.mock_knowledge([{
            "text": "Ramkund is the principal bathing ghat on the Godavari.",
            "source": "doc:ghats",
            "score": 0.9,
            "metadata": {"title": "Ghat guide", "organization": "Example Authority",
                         "verification_status": "unverified", "doc_id": "ghats"},
        }])
        reply = self.reply(self.send("What is the significance of Ramkund ghat?"))
        self.assertIn("doc:ghats", reply["metadata"]["sources"])
        [citation] = [c for c in reply["metadata"]["citations"] if c["type"] == "knowledge"]
        self.assertEqual(citation["title"], "Ghat guide")
        self.assertIn("Ghat guide (unverified", self.prompt_text(model))

    def test_no_matching_passage_still_gets_a_helpful_answer(self):
        model = self.mock_model("The ghats grew up around Ramkund ...")
        self.mock_knowledge([{"text": "x", "source": "doc:x", "score": 0.2, "metadata": {}}])
        reply = self.reply(self.send("Tell me the history of the Godavari ghats"))
        self.assertNotIn("couldn't find enough information", reply["content"])
        self.assertIn("well-established general knowledge", self.prompt_text(model))
        self.assertIn("Never reply only with what you don't know", self.system_prompt(model))

    def test_synthetic_records_are_never_trusted(self):
        self.assertFalse(knowledge_service.is_trusted_payload({"source": "local-test/nashik-kumbh"}))
        self.assertFalse(knowledge_service.is_trusted_payload({"source": "doc:a", "verification_status": "test"}))
        self.assertTrue(knowledge_service.is_trusted_payload({"source": "doc:a"}))

    def test_search_filters_test_records(self):
        class Point:
            def __init__(self, source, score):
                self.payload = {"text": "t", "source": source}
                self.score = score

        client = mock.Mock()
        client.query_points.return_value.points = [
            Point("local-test/trimbakeshwar", 0.99), Point("doc:real", 0.8),
        ]
        embeddings = mock.Mock()
        embeddings.embed_query.return_value = [0.0]
        session = mock.MagicMock()
        session.return_value.__enter__.return_value = client
        with mock.patch.object(knowledge_service, "qdrant_session", session), \
                mock.patch.object(knowledge_service, "get_embeddings", return_value=embeddings), \
                mock.patch.object(knowledge_service, "ensure_collection"):
            results = knowledge_service.search_documents("kumbh", limit=5)
        self.assertEqual([r["source"] for r in results], ["doc:real"])


class IntentTests(SimpleTestCase):
    def test_routes(self):
        cases = {
            "When is the next Amrit Snan?": "events",
            "How do I reach Trimbakeshwar temple?": "temple",
            "Is Ramkund crowded now?": "crowd",
            "What is the history of Kumbh Mela?": "rag",
            "Write a poem about rivers": "direct",
            "thanks!": "direct",
            "अगला शाही स्नान कब है?": "events",
            "रामकुंड येथे गर्दी आहे का?": "crowd",
            "मदद चाहिए, बच्चा खो गया": "safety",
        }
        for question, route in cases.items():
            with self.subTest(question=question):
                self.assertEqual(primary_route(detect_intents(question)), route)

    def test_temple_opening_question_is_not_an_event(self):
        intents = detect_intents("When does the temple open?")
        self.assertIn("temple", intents)
        self.assertNotIn("events", intents)

    def test_multi_tool_question(self):
        intents = detect_intents("Is Trimbakeshwar temple crowded and how do I get there?")
        self.assertEqual(intents[:2], ["temple", "crowd"])

    def test_follow_up_reuses_previous_topic(self):
        context = {"last_route": "events", "last_intents": ["events"]}
        self.assertEqual(detect_intents("what about tomorrow?", context=context), ["events"])
        self.assertEqual(detect_intents("ok thanks", context=context), ["direct"])

    def test_document_follow_up(self):
        context = {"document": {"extract_key": "k"}, "last_route": "document"}
        self.assertIn("document", detect_intents("what does the notice say about parking?", context=context))


class N8nFallbackTests(GuruTestCase):
    env = {"AI_MEDIA_PIPELINE": "n8n", "N8N_WEBHOOK_URL": "https://n8n.example.test/webhook/chat"}

    def test_media_goes_to_configured_webhook_when_selected(self):
        from apps.aiChat.tests.helpers import png_bytes, upload

        response = mock.Mock()
        response.json.return_value = {"reply": "From n8n"}
        with mock.patch("apps.aiChat.services.n8n_service.requests.post", return_value=response) as post:
            reply = self.reply(self.send(file=upload("p.png", png_bytes(), "image/png")))
        self.assertEqual(post.call_args.args[0], "https://n8n.example.test/webhook/chat")
        self.assertIn("file_base64", post.call_args.kwargs["json"])
        self.assertEqual(reply["content"], "From n8n")
        self.assertEqual(reply["metadata"]["provider"], "n8n")
        self.assertEqual(os.environ["AI_MEDIA_PIPELINE"], "n8n")
