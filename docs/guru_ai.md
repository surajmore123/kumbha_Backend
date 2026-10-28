# Guru AI — multimodal KumbhaPath assistant

This document covers the chatbot behind `POST /api/chat/chat-send/` and
`GET /api/chat/chat-history/`: how it works, how to configure and test it,
and what is still missing before production.

## 1. Audit before this change

| # | Capability | Before |
|---|---|---|
| 1 | Text conversations | Implemented (LangGraph), **no tests** |
| 2 | Image understanding | **Missing** natively (forwarded to n8n at a hardcoded ngrok URL) |
| 3 | Audio / speech recognition | **Missing** natively (n8n; read file via `default_storage.path()`) |
| 4 | Voice replies | Missing |
| 5 | PDF / documents | Missing (n8n only; no parsers installed) |
| 6 | Text + attachment in one message | Missing (Flutter sent no caption) |
| 7 | History / context | Partial: stored and paginated, **never used** for follow-ups |
| 8 | Gemini integration | Partial: new client per call; `settings.AI` config unused; errors not classified |
| 9 | LangGraph routing | Partial: keyword routing, single route, "when"/"date" sent everything to events |
| 10 | RAG | Partial: only 3 synthetic `local-test/*` records, no provenance, no ingestion workflow |
| 11 | Events | Implemented but missed `del_flag` and `expiry_date`, untested |
| 12 | Temples / Maps | Implemented; no alias/Devanagari matching, coordinates not validated |
| 13 | Crowd / incidents | **Missing** (latest snapshot in the DB was from Feb 2026) |
| 14 | English / Hindi / Marathi | Model-dependent only; fixed replies English-only |
| 15 | Security / rate limits | Partial: JWT + ownership OK; no rate limit, user filenames used as storage paths, no upload validation |
| 16 | Flutter rendering | Partial: newlines collapsed, no links/sources, no documents, no captions |
| 17 | Tests | **None** (placeholder `tests.py`) |

## 2. Architecture

```
Flutter ─► POST /api/chat/chat-send/ (JWT, per-user throttle)
  ChatRequestSerializer        validation, session ownership, response shape
  services/chat_orchestrator   one turn: store user msg → context → graph → store reply
    attachments/pipeline       detect (magic bytes) → image | audio | document prep
    services/history_service   last N messages of THIS session within a char budget
    graph.chat_graph (LangGraph)
      understand   speech recognition (audio), provider OCR (scanned PDF)
      route        deterministic multi-intent rules (intent_service)
      gather       read-only tools: temples+maps, events, crowd+incidents,
                   knowledge base, uploaded document, image
      compose      one grounded Gemini call, or a fixed reply / factual fallback
    voice_service (optional TTS), storage of extracts and voice files
```

Design rules enforced in code:
- One Gemini client wrapper (`services/gemini_service.py`, LangChain) for
  text, image, audio and PDF input — the bytes are sent inline. TTS uses the
  `google-genai` SDK directly because the chat wrapper cannot return audio.
- Every model call shares a per-request time budget (`AI_REQUEST_BUDGET_SECONDS`).
- Uploaded content, knowledge passages and history are fenced as untrusted
  data (`<untrusted_document>`, `<knowledge>`, `<conversation>`; `<` and `>`
  inside them are neutralised so they can't close the block).
- Missing evidence gives a fixed, localised reply without a model call;
  model failure gives a factual fallback built from the evidence, or an
  explicit "couldn't analyse this image/voice message/document".
- Crowd answers always end with the measurement time, or a stale warning.
- Synthetic knowledge records (`local-test/*` or `verification_status=test`)
  are never used.

## 3. Files

Backend (`D:\python project\kumbha_Backend`):

| File | Change |
|---|---|
| `apps/aiChat/ai_config.py` | **New.** All settings, read from env at call time |
| `apps/aiChat/messages.py` | **New.** Fixed replies in en/hi/mr, language detection |
| `apps/aiChat/attachments/{__init__,errors,detection,images,audio,documents,storage,pipeline}.py` | **New.** Upload detection/validation, image/audio/document preparation, owner-checked storage |
| `apps/aiChat/services/{answer_composer,chat_orchestrator,crowd_service,geo,history_service,intent_service,language_service,n8n_service,ocr_service,transcription_service,voice_service}.py` | **New** |
| `apps/aiChat/services/gemini_service.py` | Multimodal `invoke_gemini`, JSON mode, cached client, timeout/quota error classes; `generate_reply` kept |
| `apps/aiChat/services/event_service.py` | `del_flag`/expiry filters, more fields, recent changes, by-id lookup |
| `apps/aiChat/services/temple_service.py` | Aliases incl. Devanagari, validated links, nearest temples, by-id lookup |
| `apps/aiChat/graph.py` | New state and nodes (understand → route → gather → compose); `chat_graph` name kept |
| `apps/aiChat/rag/knowledge_service.py` | Provenance metadata, test-record exclusion, remove/re-label |
| `apps/aiChat/rag/ingestion_service.py` | `metadata` parameter, `ingest_sections` (replaces a doc_id) |
| `apps/aiChat/rag/vector_store.py` | Relative `QDRANT_LOCAL_PATH` resolved from the project |
| `apps/aiChat/serializers.py` | Validation + response only; optional `language`, `latitude`, `longitude`, `voice_reply`; internal metadata hidden |
| `apps/aiChat/views.py` | Per-user throttle on chat-send |
| `apps/aiChat/management/commands/knowledge_base.py` | **New.** list / ingest manifest / remove / mark-test |
| `apps/aiChat/management/commands/purge_chat_media.py` | **New.** Retention for voice files and extracts |
| `apps/aiChat/tests/` | **New** (replaces `tests.py`): 106 mocked tests + 7 opt-in live tests |
| `requirements.txt` | + `pypdf`, `python-docx`, `openpyxl`; `qdrant-client` pinned (file kept UTF-16) |
| `docs/guru_ai.md`, `docs/guru_ai.env.example` | **New** |

Left in place but no longer on the request path: `services/event_answer_service.py`,
`services/temple_answer_service.py`, `rag/answer_service.py` (safe to delete).

Flutter (`D:\flutter projects\kumbha_path`): see section 5.

**Database migrations: none.** `ChatSession`/`ChatMessage` are unchanged;
new data lives in the existing `metadata` JSON field.

## 4. API contract (backward compatible)

Request (`multipart/form-data` or JSON). Existing fields unchanged:
`message`, `session_id`, `file`. New optional fields: `language`
(`en|hi|mr`), `latitude` + `longitude`, `voice_reply` (bool).

Response shape is unchanged: `{"status", "data": {"session_id", "messages": [user, assistant]}}`.
Each message keeps `message_id, role, message_type, content, file_url,
metadata, created_at, session_id`.

User message `metadata` (media): `original_name`, `content_type`, `size`
(as before) plus `attachment` (`kind`, `width/height`, `duration_seconds`,
`converted`, `page_count`, `pages_read`, `truncated`, `scanned`,
`ocr_used`, `characters`, or `rejected` + `reason`) and `transcript`
(`text`, `language`, `speech_detected`). Content is now the caption
(previously `null` for media).

Assistant message `metadata`:

```json
{
  "provider": "langgraph",
  "route": "temple | events | crowd | safety | rag | document | image | audio | attachment | direct",
  "intents": ["temple", "crowd"],
  "status": "ok | degraded | error | rejected",
  "language": "en | hi | mr",
  "sources": ["temple:<id>", "event:<id>", "crowd:<code>", "document:<name>", "<knowledge source>"],
  "citations": [{"type": "knowledge|document|event|temple|crowd|incident", "...": "..."}],
  "temples": [{"id", "name", "latitude", "longitude", "image_url", "crowd_level", "crowd_level_source": "admin_advisory", "map_url", "directions_url", "distance_km?"}],
  "events": [{"id", "name", "date", "start_time", "end_time", "location", "data_source", "map_url", "directions_url", "...": "..."}],
  "crowd": {"zones": [...], "incidents": [...], "freshness": {"calculated_at", "age_minutes", "stale"}},
  "transcript": {"text", "language", "speech_detected"},
  "voice": {"status": "ok|failed|disabled", "url?", "mime_type?"},
  "warnings": ["events_unavailable"],
  "error": "<code when rejected>"
}
```

Internal storage keys are kept under `metadata._internal` and are removed
from every API response.

## 4a. Reply language

The answer is in the language of the user's question, not the app's UI
language (`messages.analyze_language`):

1. An explicit request wins: "answer in Marathi", "explain this in Hindi",
   "मराठीत सांगा", "हिंदी में बताइए".
2. Otherwise the question's own language: its script (Gujarati, Punjabi,
   Bengali, Odia, Tamil, Telugu, Kannada, Malayalam, Urdu, Devanagari);
   Hindi vs Marathi by common words and the Marathi letter ळ; romanized
   Hindi/Marathi ("Amrit snan kab hai?", "gardi aahe ka?") is answered in
   the same Latin-letter style.
3. Voice messages are answered in the language that was spoken.
4. Only when there is no language signal (a photo without a caption, a
   bare place name) is the app's `language` field used.

English, Hindi and Marathi have prepared fixed replies. For any other
language (`services/language_service.py`) an English version of the
question is made for routing and search (one extra model call), the
original question is answered, and fixed replies are translated by the
model — falling back to English text if that call fails.

## 5. Flutter changes (`D:\flutter projects\kumbha_path`)

- `lib/src/models/chat_messages.dart` — links, sources, transcript, file name,
  document type; parsers for the metadata above.
- `lib/src/bloc/webhook_bloc/*` — `ChatPayloadType.document`, captions on
  photo/document events, `language` sent with every message, transcript
  shown on the sent voice note, paragraphs kept (no newline collapsing),
  history maps documents/captions/links/sources.
- `lib/src/components/chat_screen/chat_input.dart` — "Choose a document"
  (PDF/DOCX/TXT/CSV/XLSX via `file_picker`), selected-file chip, text typed
  with a photo or document is sent as its caption.
- `lib/src/components/chat_screen/chat_bubble.dart` — directions chips
  (opened with `url_launcher`, https only), "Sources:" line, photo caption,
  voice transcript, `ChatDocumentBubble`.
- `lib/src/network/api/{user_chat_api,api}.dart`, `repository/app_repository.dart`,
  `constant/document_type.dart` — extra multipart fields, document MIME types,
  removed logging of tokens, headers and response bodies.
- `pubspec.yaml` — `file_picker`, `path` (was used without being declared).
- Translations: 8 new `ai_*` keys in en/hi/mr; `ai_attach` text updated.
- Tests: `test/ai_chat_test.dart` (rich replies), new `test/ai_chat_contract_test.dart`.

Not done in Flutter: voice-reply playback (no audio player package; the
feature is off by default on the server), location sharing for "near me"
(the API accepts `latitude`/`longitude`; the chat doesn't send them yet).

## 6. Configuration

All variables with defaults: `docs/guru_ai.env.example`. Important:

- `GEMINI_API_KEY` — required. Never commit it.
- `AI_MEDIA_PIPELINE=native` (default) or `n8n` (legacy webhook at
  `N8N_WEBHOOK_URL`; the URL is no longer hardcoded).
- The embedding model is still `GEMINI_EMBEDDING_MODEL` (default
  `gemini-embedding-001`, 3072-dim, matching the existing collection).
  `AI_EMBEDDING_MODEL`/`AI_EMBEDDING_DIM` in `.env.local` are **not used**;
  switching models requires re-embedding into a new collection.
- `AI_TEMPERATURE`, `AI_MAX_RETRIES`, `AI_TIMEOUT_SECONDS` in `.env.local`
  are now honoured (previously hardcoded 0.2 / 2 / 30).
- ffmpeg (already in the Dockerfile; `FFMPEG_PATH` on Windows) is needed for
  M4A/WebM voice notes — the Flutter recorder produces M4A.

## 7. Knowledge base workflow

```bash
python manage.py knowledge_base list
python manage.py knowledge_base ingest knowledge/manifest.json --dry-run
python manage.py knowledge_base ingest knowledge/manifest.json
python manage.py knowledge_base remove --doc-id <doc_id>
python manage.py knowledge_base mark-test --source-prefix local-test/
```

Manifest format and rules are in the command's docstring. `verified`
requires `verified_by` naming the evidence. Back up `data/qdrant/` (copy the
folder with the server stopped) before `remove` or `mark-test`.

**Current state:** 254 passages from 11 Wikipedia articles (Kumbh Mela,
Nashik-Trimbakeshwar Simhastha and its 2015 edition, Nashik, History of
Nashik, Trimbak, Trimbakeshwar Temple, Kalaram Temple, Godavari River,
Akhara, Daśanāmi Sampradaya), stored as `unverified` with source URL and
revision. Refresh with `python knowledge/fetch_wikipedia.py` and
`python manage.py knowledge_base ingest knowledge/wikipedia_manifest.json`
(`--skip-existing` resumes after a free-tier embedding quota stop; the
command waits and retries on quota errors). The 3 synthetic `local-test/*`
chunks remain excluded. Add official PDFs/notices with their own manifest
(`verification_status: verified` + `verified_by`).

Answer policy: live facts (event dates, crowd, incidents) only from the
database; background knowledge from the passages, with general knowledge
filling gaps. Fixed "not available" replies are used only when live data
(events, crowd) is missing and nothing else can stand in for it. When the
database and published sources disagree, the answer gives the database
value and flags the difference.

Vector store: `QDRANT_URL` (+ `QDRANT_API_KEY`) uses a Qdrant server;
otherwise the local store is opened per operation (local mode locks its
folder, so holding it open blocked other processes).

## 8. Testing

```bash
# all mocked tests (no network, temp media folder, test database)
python manage.py test apps.aiChat
# live provider checks (uses GEMINI_API_KEY; ~10 calls)
RUN_LIVE_AI_TESTS=1 python manage.py test apps.aiChat.tests.test_live_gemini
# optional: a WAV of "When is the next Amrit Snan?" to avoid the TTS quota
LIVE_TEST_SPEECH_WAV=path/to/question.wav RUN_LIVE_AI_TESTS=1 python manage.py test apps.aiChat.tests.test_live_gemini.LiveEndToEndTests
```

Mocked tests patch the model, embeddings and Qdrant client to fail if
reached, so they cannot make live calls or touch `data/qdrant`.

## 9. Production readiness checklist

- [ ] Ingest approved, attributed Kumbh sources; remove or `mark-test` the synthetic chunks.
- [ ] Use a paid Gemini tier: the free tier hit 429 after ~20 calls during testing.
- [ ] Replace local-mode Qdrant with a Qdrant server: local mode holds a file lock, so only one gunicorn worker/process can open it.
- [ ] Configure a shared cache (Redis) so the chat throttle applies across workers (default cache is per-process memory).
- [ ] Keep the crowd engine running on a schedule; otherwise every crowd answer is (correctly) flagged stale.
- [ ] Media is served from `/media/` without auth. Chat files now have random names, but consider authenticated/signed URLs for chat uploads.
- [ ] Schedule `purge_chat_media --days N` and decide a retention period for uploads.
- [ ] Fix the Dockerfile: it installs `requirements-ai.txt`, which doesn't exist (uncommitted change).
- [ ] Add Celery/async processing if long documents or audio push requests past the gunicorn timeout (budget is 90 s).
- [ ] Load-test concurrent uploads; set gunicorn timeout ≥ `AI_REQUEST_BUDGET_SECONDS`.

## 10. Migrating away from n8n

1. Now: `AI_MEDIA_PIPELINE=native` is the default; n8n is only used if
   explicitly selected.
2. Run the live end-to-end tests on a key with quota until image, voice and
   document all pass (see results below), and test with real phone
   recordings in Hindi and Marathi.
3. Run in staging for a week; watch `status`/`warnings` in assistant metadata.
4. Then delete `services/n8n_service.py`, `_legacy_n8n_turn` in
   `chat_orchestrator.py`, the `AI_MEDIA_PIPELINE`/`N8N_WEBHOOK_URL` settings
   and `N8nFallbackTests`, and switch off the n8n workflow.

## 11. Known limitations

- Hindi/Marathi questions about an English document use a spread of
  passages, not term matching (lexical selection is language-bound).
- Temple aliases are a fixed list; new temples match only by name until
  aliases are added (no schema change was made).
- Hindi vs Marathi in Devanagari is decided by common words; a very short
  question with no such words uses the app language (or Hindi).
- Questions in languages other than English/Hindi/Marathi cost one extra
  model call (English version for routing), plus one per fixed reply.
- Crowd ↔ temple association uses zone radius/proximity (no FK exists).
- Voice reply quality/limits depend on the Gemini TTS preview model.
- Only one file per message.
