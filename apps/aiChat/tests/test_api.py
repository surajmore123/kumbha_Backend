from unittest import mock

from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.aiChat.models import ChatMessage, ChatSession
from apps.aiChat.services.gemini_service import GeminiQuotaError, GeminiTimeoutError
from apps.aiChat.tests.helpers import (
    HISTORY_URL,
    SEND_URL,
    GuruTestCase,
    make_event,
    make_temple,
)
from apps.authentication.models import User


class AuthAndOwnershipTests(GuruTestCase):
    def test_unauthenticated_request_is_rejected(self):
        response = APIClient().post(SEND_URL, {"message": "hi"}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_jwt_bearer_token_is_accepted(self):
        self.mock_model("Namaste!")
        client = APIClient()
        token = RefreshToken.for_user(self.user).access_token
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = client.post(SEND_URL, {"message": "Hello"}, format="json")
        self.assertEqual(response.status_code, 200)

    def test_other_users_session_is_not_found(self):
        other = User.objects.create_user(phone_number="9000000002")
        foreign = ChatSession.objects.create(user=other, title="x")
        response = self.send("Hello", session_id=str(foreign.session_id))
        self.assertEqual(response.status_code, 400)
        self.assertIn("session_id", response.json()["errors"])
        self.assertFalse(ChatMessage.objects.filter(session=foreign).exists())

    def test_history_of_other_users_session_is_not_found(self):
        other = User.objects.create_user(phone_number="9000000003")
        foreign = ChatSession.objects.create(user=other, title="x")
        response = self.client.get(HISTORY_URL, {"session_id": str(foreign.session_id)})
        self.assertEqual(response.status_code, 400)

    def test_message_or_file_is_required(self):
        response = self.send("   ")
        self.assertEqual(response.status_code, 400)

    def test_invalid_coordinates_are_rejected(self):
        response = self.send("temples near me", latitude=95, longitude=73)
        self.assertEqual(response.status_code, 400)


class TextTurnTests(GuruTestCase):
    def test_general_question_and_backward_compatible_response(self):
        model = self.mock_model("Paris is the capital of France.")
        response = self.send("What is the capital of France?")
        data = response.json()["data"]

        self.assertEqual(response.json()["status"], "success")
        self.assertIn("session_id", data)
        user_message, reply = data["messages"]
        for message in (user_message, reply):
            for key in ("message_id", "role", "content", "file_url", "metadata",
                        "created_at", "session_id"):
                self.assertIn(key, message)
        self.assertEqual(user_message["role"], "user")
        self.assertEqual(reply["role"], "assistant")
        self.assertEqual(reply["message_type"], "text")
        self.assertEqual(reply["content"], "Paris is the capital of France.")
        self.assertEqual(reply["metadata"]["route"], "direct")
        self.assertEqual(reply["metadata"]["provider"], "langgraph")
        self.assertEqual(reply["metadata"]["sources"], [])
        self.assertIn("Never invent dates", self.system_prompt(model))

    def test_messages_are_persisted_and_session_updated(self):
        self.mock_model("Namaste!")
        self.send("Hello")
        stored = self.messages()
        self.assertEqual([m.role for m in stored], ["user", "assistant"])
        self.assertEqual(stored[0].content, "Hello")
        self.assertIsNotNone(self.session().last_message_at)

    def test_temple_question_returns_temple_and_navigation(self):
        model = self.mock_model("Trimbakeshwar is a Jyotirlinga temple.")
        temple = make_temple()
        reply = self.reply(self.send("Tell me about Trimbakeshwar temple"))

        self.assertEqual(reply["metadata"]["route"], "temple")
        [found] = reply["metadata"]["temples"]
        self.assertEqual(found["id"], str(temple.temple_id))
        self.assertTrue(found["directions_url"].startswith("https://www.google.com/maps/dir/?api=1"))
        self.assertIn(f"temple:{temple.temple_id}", reply["metadata"]["sources"])
        self.assertIn("Trimbakeshwar Jyotirling Mandir", self.prompt_text(model))

    def test_event_question_uses_published_verified_events_only(self):
        model = self.mock_model("The next Amrit Snan is on ...")
        visible = make_event("Second Amrit Snan")
        make_event("Draft Snan", status="DRAFT")
        make_event("Archived Snan", status="ARCHIVED")
        make_event("Unverified Snan", is_verified=False)
        reply = self.reply(self.send("When is the next Amrit Snan?"))

        self.assertEqual(reply["metadata"]["route"], "events")
        self.assertEqual([e["id"] for e in reply["metadata"]["events"]], [str(visible.event_id)])
        prompt = self.prompt_text(model)
        self.assertIn("Second Amrit Snan", prompt)
        self.assertNotIn("Draft Snan", prompt)
        self.assertNotIn("Archived Snan", prompt)

    def test_event_question_without_events_does_not_call_model(self):
        model = self.mock_model()
        reply = self.reply(self.send("What is the upcoming event schedule?"))
        self.assertIn("couldn't find any upcoming published and verified events", reply["content"])
        model.assert_not_called()

    def test_new_question_after_temple_turn_is_not_treated_as_follow_up(self):
        # Reported: "where will the ganga aarthi happening" after a temple
        # question returned that temple's map and "no information".
        self.mock_model("Kapaleshwar is a Shiva temple.")
        make_temple("Shree Kapaleshwar Mahadev Mandir", "19.998500", "73.792000")
        self.send("Tell me about Kapaleshwar temple")

        model = self.mock_model("The Godavari aarti is held every evening at Ramkund.")
        reply = self.reply(self.send("where will the ganga aarthi happening"))
        self.assertEqual(reply["metadata"]["temples"], [])
        self.assertEqual(reply["metadata"]["route"], "rag")
        self.assertIn("well-established general knowledge", self.prompt_text(model))
        self.assertEqual(reply["content"], "The Godavari aarti is held every evening at Ramkund.")

    def test_important_kumbh_dates_use_the_event_records(self):
        # Reported: "give me impo dates for kumbha mela" answered
        # "couldn't find enough information" although events exist.
        model = self.mock_model("Key dates: First Amrit Snan ...")
        make_event("First Amrit Snan", days=30)
        make_event("Flag hoisting", days=5, event_category="KUMBH_LIFECYCLE")
        reply = self.reply(self.send("give me impo dates for kumbha mela"))
        self.assertEqual(reply["metadata"]["route"], "events")
        self.assertEqual(len(reply["metadata"]["events"]), 2)
        prompt = self.prompt_text(model)
        self.assertIn("First Amrit Snan", prompt)
        self.assertIn("Flag hoisting", prompt)

    def test_follow_up_uses_temple_from_previous_turn(self):
        self.mock_model("Here is the temple.")
        temple = make_temple()
        self.send("Tell me about Trimbakeshwar temple")

        model = self.mock_model("Use the directions button.")
        reply = self.reply(self.send("How do I reach there?"))
        self.assertEqual([t["id"] for t in reply["metadata"]["temples"]], [str(temple.temple_id)])
        prompt = self.prompt_text(model)
        self.assertIn("discussed earlier in this conversation", prompt)
        self.assertIn("Tell me about Trimbakeshwar temple", prompt)

    def test_history_is_limited_to_the_session_and_budget(self):
        self.mock_model("ok")
        for index in range(6):
            self.send(f"message number {index}")
        with mock.patch.dict("os.environ", {"AI_HISTORY_MAX_MESSAGES": "2"}):
            model = self.mock_model("ok")
            self.send("latest question")
        prompt = self.prompt_text(model)
        self.assertIn("message number 5", prompt)
        self.assertNotIn("message number 3", prompt)

    def test_marathi_question_gets_marathi_fixed_reply(self):
        self.mock_model()
        reply = self.reply(self.send("पुढचा शाही स्नान कधी आहे?"))
        self.assertEqual(reply["metadata"]["language"], "mr")
        self.assertIn("कार्यक्रम सापडला नाही", reply["content"])

    def test_app_language_is_only_a_fallback(self):
        model = self.mock_model("Hello!")
        reply = self.reply(self.send("Hello", language="hi"))
        self.assertEqual(reply["metadata"]["language"], "en")
        self.assertIn("The user wrote in English", self.system_prompt(model))


class FailureTests(GuruTestCase):
    def test_model_timeout_with_evidence_returns_factual_fallback(self):
        self.mock_model(side_effect=GeminiTimeoutError("slow"))
        make_temple()
        reply = self.reply(self.send("Tell me about Trimbakeshwar temple"))
        self.assertEqual(reply["metadata"]["status"], "degraded")
        self.assertIn("Trimbakeshwar Jyotirling Mandir", reply["content"])
        # Links go to the app's buttons, not the text.
        self.assertNotIn("http", reply["content"])
        self.assertTrue(reply["metadata"]["temples"][0]["directions_url"])

    def test_urls_written_by_the_model_are_removed_from_the_text(self):
        self.mock_model(
            "Trimbakeshwar is 28 km away.\nDirections: "
            "https://www.google.com/maps/dir/?api=1&destination=19.93,73.53\n"
            "See [the map](https://maps.google.com/?q=x) for more."
        )
        make_temple()
        reply = self.reply(self.send("How do I reach Trimbakeshwar temple?"))
        self.assertNotIn("http", reply["content"])
        self.assertIn("See the map for more.", reply["content"])
        self.assertEqual(reply["metadata"]["temple_mode"], "matched")

    def test_model_quota_error_without_evidence(self):
        self.mock_model(side_effect=GeminiQuotaError("429"))
        reply = self.reply(self.send("What is the capital of France?"))
        self.assertEqual(reply["metadata"]["status"], "error")
        self.assertIn("busy", reply["content"])

    def test_graph_crash_still_stores_a_reply(self):
        with mock.patch("apps.aiChat.services.chat_orchestrator.chat_graph") as graph:
            graph.invoke.side_effect = RuntimeError("boom")
            reply = self.reply(self.send("Hello"))
        self.assertEqual(reply["metadata"]["status"], "error")
        self.assertEqual(len(self.messages()), 2)

    def test_tool_failure_is_reported_not_guessed(self):
        model = self.mock_model("Events are unavailable right now.")
        with mock.patch(
            "apps.aiChat.graph.event_service.get_upcoming_verified_events",
            side_effect=RuntimeError("db down"),
        ):
            reply = self.reply(self.send("Upcoming events?"))
        self.assertIn("events_unavailable", reply["metadata"]["warnings"])
        self.assertIn("temporarily unavailable", self.prompt_text(model))


class HistoryTests(GuruTestCase):
    def test_cursor_pagination_and_internal_metadata_is_hidden(self):
        self.mock_model("ok")
        for index in range(3):
            self.send(f"q{index}")
        session = self.session()
        first = ChatMessage.objects.filter(session=session).first()
        first.metadata = {"_internal": {"storage_key": "chat/x/y.png"}, "content_type": "image/png"}
        first.save()

        page = self.client.get(HISTORY_URL, {"session_id": str(session.session_id), "limit": 4}).json()["data"]
        self.assertTrue(page["has_more"])
        self.assertEqual(len(page["messages"]), 4)
        older = self.client.get(HISTORY_URL, {
            "session_id": str(session.session_id), "limit": 4, "cursor": page["next_cursor"],
        }).json()["data"]
        self.assertFalse(older["has_more"])
        self.assertEqual(len(older["messages"]), 2)
        self.assertEqual(older["messages"][0]["metadata"], {"content_type": "image/png"})


class ThrottleTests(GuruTestCase):
    env = {"AI_CHAT_RATE": "2/min"}

    def test_chat_send_is_rate_limited_per_user(self):
        cache.clear()
        self.mock_model("ok")
        self.assertEqual(self.send("one").status_code, 200)
        self.assertEqual(self.send("two").status_code, 200)
        self.assertEqual(self.send("three").status_code, 429)
