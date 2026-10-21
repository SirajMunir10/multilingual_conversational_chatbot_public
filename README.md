# XO — XOTO Conversational Assistant

XO is XOTO's chat and voice assistant for UAE real estate and mortgages. It helps buyers, investors, agents, brokers, bankers and mortgage advisors find properties, estimate affordability and payments, understand fees and regulations from XOTO's knowledge base, and request an advisor callback, in 15 languages. The authoritative requirements are in [`prd.md`](prd.md) and [`Xobia_KB_v2_FINAL.md`](Xobia_KB_v2_FINAL.md); mortgage eligibility and calculations follow the approved [`Mortgage Eligibility Calculations.pdf`](Mortgage%20Eligibility%20Calculations.pdf).

## Models (confirmed, override PRD §6.2)

| Purpose | Model |
|---|---|
| LLM | OpenAI `gpt-6-luna` (reasoning effort `none`, function calling) |
| Speech-to-text | OpenAI `gpt-live-transcribe` (Realtime transcription session, streamed through the backend) |
| Text-to-speech | ElevenLabs `eleven_v4_turbo`, voice Horatius `qXpMhyvQqiRxWQs4qSSB` |
| Embeddings (RAG) | OpenAI `text-embedding-3-small` |

All model names come from environment variables. See [`.env.example`](.env.example).

## How it works

```
Browser widget (Next.js / React)
  ├─ POST /api/chat/stream  (SSE: session → status → tokens → final)
  ├─ WS   /api/voice/stt    (24 kHz PCM → gpt-live-transcribe → live captions)
  ├─ POST /api/handoff/confirm (advisor callback card: user confirms or edits → saved to the PostgreSQL lead store)
  ├─ POST /api/voice/speak-timed (reply pieces → eleven_v4_turbo MP3 + word timings; played while streaming, spoken word highlighted)
  └─ POST /api/voice/speak  (plain MP3 stream)

Conversation orchestrator (FastAPI)
  ├─ gpt-6-luna with function calling (multi-step tool loop, real token streaming)
  ├─ Tools: search_properties · get_listing_details · find_similar · compare_listings
  │         calc_affordability · calc_emi · check_eligibility · calc_purchase_costs
  │         get_lending_rules · get_mortgage_products · estimate_offers · retrieve_kb
  │         get_service_pricing · shortlist_property · get_my_saved_properties
  │         get_my_application_status · request_human_handoff · set_language
  ├─ Mortgage engine — deterministic, reads versioned rule/fee/rate tables (no LLM math)
  ├─ Property discovery — live GRID off-plan feed + sample ready listings
  ├─ RAG — embeddings → vector search → passages → model answer (or "I don't know" + advisor)
  └─ Handoff — consent-gated, saved to PostgreSQL, routed to Vault (mortgage) or GRID (sales)
```

The LLM understands intent, details, language and consent from the conversation. Every number, listing, rule and fact comes from a tool. Nothing is invented.

## Business data (no code changes needed)

Everything business-specific lives in versioned files under [`backend/app/data/config/`](backend/app/data/config/):

| File | Contents |
|---|---|
| `mortgage_rules.json` | Approved eligibility rules: bank settings (age, minimum income, stress test, card-limit debt, non-resident LTV), Central Bank values (50% debt burden, 25-year term, income multiple, rent vacancy), ordered LTV table, benchmark rate |
| `fees.json` | Purchase fees by emirate (KB Article 2) |
| `bank_products.json` | Indicative bank products (pending Mortgage Team confirmation) |
| `communities.json` | Communities, emirates and their aliases |
| `inventory_sample.json` | Sample ready listings for the prototype (off-plan is live) |
| `locales.json` | 15 languages: STT/TTS codes, server messages |
| `services_pricing.json` | Service quotations |
| `pricing.json` | Provider prices for cost monitoring |
| `prompts/system_prompt.md` | XO's persona and conversation rules |

After editing a file, call `POST /api/admin/reload-config` (header `X-Admin-Key`) to apply it without a redeploy. Open mortgage questions for the Mortgage Team are in [`XO_Mortgage_Policy_Review.xlsx`](XO_Mortgage_Policy_Review.xlsx).

## Security & privacy

- Identity comes only from a signed bearer token (HS256, `JWT_SECRET`). Client headers are never trusted.
- Transcripts, leads, usage and audit logs are only available under `/api/admin/*` with `X-Admin-Key`.
- Card numbers, IBANs and CVVs are removed before any text reaches the model. XO never handles payments.
- Phone numbers and names are masked in logs. CORS is restricted to `ALLOWED_ORIGINS`, and endpoints that spend credits are rate-limited.
- Chat text is rendered as markdown with HTML disabled, so no script injection is possible.

## Running locally

```bash
cp .env.example backend/.env        # add your keys
cd backend && pip install -r requirements.txt
uvicorn app.main:app --port 8000

cd frontend && npm install && npm run dev   # http://localhost:3000 (proxies /api; live voice connects to ws://127.0.0.1:8000, see frontend/.env.development)
```

`npm run build` writes a static site to `frontend/out/`, which nginx (Docker) or Vercel serves.

With Docker: set `POSTGRES_PASSWORD` and your keys in `.env`, then run `docker compose up --build`.

### Deployment notes

- **Backend (Render):** set every variable from `.env.example`. `ALLOWED_ORIGINS` must include the frontend origin, for example `https://xoto-blitz.vercel.app`. Set `DATABASE_URL`, or leads are kept in memory only.
- **Frontend (Vercel):** set `NEXT_PUBLIC_API_WS_BASE=wss://<backend-host>` (the old `VITE_API_WS_BASE` is still read). Vercel rewrites cannot proxy WebSockets, and live voice connects directly to the backend. The project's framework preset is Next.js (`frontend/vercel.json`).
- **Off-plan links:** set `OFFPLAN_LISTING_URL_TEMPLATE` (for example `https://xoto.ae/<path>/{slug}`) to show "View details". Without it, no link is shown.

## Tests

```bash
cd backend && python -m unittest discover -s tests -t .
```

The 69 offline tests cover:
- the mortgage engine against the 15 approved test cases (to the dirham), the KB's worked examples and the rule tables;
- property search (strict filters, ranges, alternatives, live-feed parsing);
- security (auth, admin key, CORS, rate limits, payment redaction, no leaks);
- the orchestrator, using a fake streaming LLM (tool loop, memory, language guard, failure handling);
- handoff truthfulness, voice text cleaning and RAG scoping.

## Repository

- `backend/app/` holds the FastAPI app: `orchestrator/` (engine, tools, sessions), `services/`, `gateways/`, `voice/`, `routers/`, `core/`, `db/` and `data/`.
- `frontend/src/xo/` holds the widget, self-contained so it can be moved into another Next.js site: `components/` (`ChatWidget.jsx`, `MessageItem.jsx`, `MortgageCard.jsx`, `HandoffCard.jsx`, `VoiceOrb.jsx` for the 3D voice orb, …), `hooks/useVoice.js` and `lib/voice.js` (live STT), `lib/speech.js` (streamed TTS playback), `lib/wordHighlight.js` (marks the spoken word), `i18n/ui.json` (15-language UI text), `lib/api.js`, `lib/markdown.js` and `styles/`.
- `frontend/src/shell/` holds the demo page around the widget (header, landing page, admin preview); `frontend/src/app/` is the Next.js entry.
- `e2e/` holds the frontend tests (Playwright, simulated backend): desktop, Android and iPhone, 13 screen sizes and screenshot comparison. Run `cd e2e && npm install && npx playwright install && BASE_URL=http://localhost:3000 npm test`.
- `docs/IMPLEMENTATION_PLAN.md` is the remediation plan these changes follow.
