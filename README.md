# XO — Conversational AI Assistant
### Production Prototype Specification & System Architecture

XO is an enterprise-grade embedded conversational AI assistant designed for real-estate and mortgage discovery across web and product surfaces. It empowers visitors to seamlessly discover properties, calculate accurate mortgage affordability and EMI figures, resolve complex company/policy questions via RAG, access authenticated account records, and seamlessly escalate to human specialists in their native language across both text and voice.

---

## 1. Project Overview & Objective

- **Prototype Goal:** Fully functional marketing and production prototype of the **XO — Conversational AI Assistant**.
- **Implementation Target:** Rapid 2-day delivery cycle suitable for executive presentation, marketing demonstrations, and production scaling.
- **Core Value Propositions:**
  1. Real-estate property discovery, conversational filtering, and ranking.
  2. Deterministic mortgage affordability, eligibility, EMI, and offer estimation.
  3. Grounded knowledge-base Q&A (RAG) regarding Xoto, policies, products, and processes.
  4. Scoped, user-only authenticated account inquiry.
  5. Unified text & voice conversation orchestrator.
  6. Multilingual support across **English, Arabic, Hindi, and Urdu** with automatic language detection and manual override.
  7. High-conversion human handoff and CRM lead synchronization (GRID & Vault).
  8. Comprehensive Admin Back Office for non-technical content, prompt, rate, rule, and escalation management.

---

## 2. Technology Stack

| Layer | Technology | Details |
| :--- | :--- | :--- |
| **Frontend** | Vue.js (Vue 3) | Composition API, Vite, custom luxury styling system, WCAG 2.1 AA |
| **Backend** | Python & FastAPI | Asynchronous REST APIs, Pydantic v2 validation, SSE streaming |
| **Containerization** | Docker & Docker Compose | Multi-container architecture (`docker-compose.yml`); no venv deployment |
| **AI / LLM** | OpenAI `gpt-5-mini` | High-reasoning language model, system persona guardrails, function calling |
| **Speech-to-Text (STT)**| OpenAI `gpt-live-transcribe` | Real-time audio transcription across EN, AR, HI, UR |
| **Text-to-Speech (TTS)**| ElevenLabs `eleven_flash_v2_5` | Voice: Horatius (`qXpMhyvQqiRxWQs4qSSB`) - Energetic Character voice across EN, AR, HI, UR |
| **Voice Architecture** | Composed STT → LLM → TTS | Shared conversation orchestrator; identical business logic for text & voice |
| **Knowledge / RAG** | Vector DB & Embeddings | Scoped vector retrieval, cosine similarity, reranking, query caching |
| **Financial Engine** | Deterministic Calculation Service | Python math engine using UAE Central Bank rules (DBR, LTV, salary caps) |

---

## 3. High-Level Architecture

```
User (Web Widget / Product Surface — Text & Voice)
                      │
                      ▼
        Conversation Orchestrator (FastAPI)
 ├─ Automatic Language Detection (EN / AR / HI / UR) + Manual Override
 ├─ Voice Layer (STT: gpt-live-transcribe; TTS: eleven_flash_v2_5)
 ├─ Intent Routing (Property / Mortgage / General / Account)
 ├─ Session & Dialogue State Store
 │
 ├──► OpenAI LLM API (gpt-5-mini)
 │     └─ Strict Function Calling Boundaries (NO direct database access):
 │        • search_properties()
 │        • calc_affordability()
 │        • calc_emi()
 │        • get_my_saved_properties()
 │        • get_my_application_status()
 │        • retrieve_kb()
 │
 ├──► RAG Knowledge Layer (Vector DB + Document Ingestion + Scoped Retriever + Reranker)
 │
 ├──► Mortgage Calculation Service (Deterministic, Internal Versioned Rate/Rule Tables)
 │
 ├──► Property Inventory API Gateway (Live Listings, Scoped Fields, Read-Only)
 │
 ├──► In-House CRM Gateways:
 │     ├─ GRID Gateway (Real Estate CRM Leads & Shortlists)
 │     └─ Vault Gateway (Mortgage CRM Leads & Applications)
 │
 └──► Admin Module (KB CMS, Prompt Tuning, Rules Config, RBAC, Analytics, A/B Testing)
```

---

## 4. Key Architectural & Engineering Boundaries

### 4.1 Strict Data Access Boundary (Zero Direct Database Access)
- The LLM, bot layer, and conversation orchestrator **never connect directly to any production database** (GRID, Vault, or raw SQL/NoSQL stores).
- All customer and business data access occurs through a fixed set of narrow, purpose-built, read-scoped API endpoints.
- Endpoints return **only the specific fields required** for that specific conversational function—never raw records, dumps, or broad access credentials.
- Write actions (saving a shortlisted property, submitting a lead) go through equally narrow, explicitly defined, and strictly logged endpoints.

### 4.2 Deterministic Financial Engine (Zero LLM Math)
- The LLM **never** performs mathematical operations or interest calculations.
- All mortgage affordability, eligibility, EMI, and offer calculations are handled by the deterministic backend `MortgageCalculationService`.
- Calculators are powered by **internal, admin-managed, versioned rate and rule tables** reflecting UAE Central Bank standards (e.g. 50% Debt Burden Ratio, LTV limits).
- Every calculation output includes the mandatory disclaimer:
  > *"estimate only, subject to lender approval"*
  and is clearly identified as *"estimates, not offers"*.
- All calculator inputs and outputs are recorded in an auditable ledger.
- Explicit user consent is verified prior to storing any personal financial profile.

### 4.3 Composed Voice-to-Voice (V2V) Pipeline
- Voice interactions share the **identical** intent router, business rules, and state engine as text chat.
- User Audio → `gpt-live-transcribe` (STT) → Text → Conversation Orchestrator → `gpt-5-mini` → Response Text → `eleven_flash_v2_5` (TTS) → Audio Stream.
- Supported in all four launch languages: English, Arabic, Hindi, and Urdu.

### 4.4 Zero Payment Scope
- XO is strictly scoped to advisory discovery, estimation, support, and lead capture.
- XO **never** handles, collects, requests, initiates, confirms, or processes payments.

---

## 5. Repository & Project Structure

```
c:/Users/siraj/Documents/XOTO-Siraj-Munir_ChatBot/XO_Ai_Production_Prototype/
├── docker-compose.yml               # Unified multi-container orchestration
├── PHASE_PLAN.md                   # Formal project phase plan & gate tracking
├── IMPLEMENTATION_CHECKLIST.md     # Detailed 65-point requirements traceability checklist
├── README.md                       # Master system documentation (this file)
│
├── backend/                        # Python FastAPI Backend Service
│   ├── Dockerfile                  # Production container definition
│   ├── requirements.txt            # Python dependencies (FastAPI, OpenAI, Uvicorn, etc.)
│   └── app/
│       ├── main.py                 # Application entry point & router mounting
│       ├── core/                   # Configuration, security, audit logging, exceptions
│       ├── orchestrator/           # Conversation state engine & language detection
│       ├── voice/                  # STT (gpt-live-transcribe) & TTS (gpt-4o-mini-tts)
│       ├── llm/                    # OpenAI gpt-5-mini client & function calling
│       ├── calculators/            # Deterministic mortgage calculation service & rules
│       ├── rag/                    # Vector store, document processing, retriever, reranker
│       ├── gateways/               # Scoped API gateways for Inventory, GRID, Vault
│       ├── account/                # User-scoped authenticated account inquiries
│       └── admin/                  # Admin back office API routers (KB, Tuning, Analytics)
│
└── frontend/                       # Vue 3 Frontend Web Widget & Admin Surface
    ├── Dockerfile                  # Nginx/Vite production container definition
    ├── package.json                # Vue 3, Vite, Lucide icons, Pinia, Vue Router
    ├── index.html                  # HTML entry point with luxury styling tokens
    ├── vite.config.js              # Vite bundler configuration & backend proxy
    └── src/
        ├── App.vue                 # Master application wrapper
        ├── main.js                 # Frontend initialization
        ├── assets/css/             # Luxury design tokens, animations, WCAG contrast
        ├── components/
        │   ├── chat/               # Luxury Chat Widget, Message Feed, Tooltips, Mic
        │   ├── properties/         # Property Cards, Carousels, Shortlist actions
        │   ├── mortgage/           # Breakdown Cards, EMI Charts, Disclaimers
        │   └── shared/             # Buttons, Modals, Language Switcher, Audio Visualizer
        ├── views/
        │   ├── WidgetView.vue      # Embeddable chat widget view
        │   └── AdminView.vue       # 10-module comprehensive Admin Back Office
        └── composables/            # Voice recorder, chat streaming, language state
```

---

## 6. Development Phases & Current Status

Implementation is strictly governed by the sequential phase gate protocol:
`PLAN → IMPLEMENT → ENGINEERING TESTS → UPDATE CHECKLIST → REPORT → STOP → USER TESTS → USER APPROVES → NEXT PHASE`.

| Phase | Description | Status |
| :--- | :--- | :--- |
| **Phase 1** | Project Foundation, Core Architecture & Containerization | `READY FOR USER TESTING` |
| **Phase 2** | Conversational Core, Multilingual Engine & Voice Layer | `NOT STARTED` |
| **Phase 3** | Deterministic Mortgage Calculation Service & Financial Tools | `NOT STARTED` |
| **Phase 4** | Property Discovery, Live Inventory Boundary & Recommendation | `NOT STARTED` |
| **Phase 5** | Curated Knowledge Base & RAG Architecture | `NOT STARTED` |
| **Phase 6** | Account Awareness, CRM Integrations & Human Handoff | `NOT STARTED` |
| **Phase 7** | Admin Module & Back Office Control Center | `NOT STARTED` |
| **Phase 8** | E2E Integration, Security/Compliance Verification & Final Delivery | `NOT STARTED` |

**Current Status:** Phase 1 complete and ready for user testing and approval. Phase 2 queued.

---

## 7. Configuration & Environment Variables

Create a `.env` file in the project root:

```ini
# Server Configuration
ENVIRONMENT=development
PORT=8000
FRONTEND_PORT=3000
ALLOWED_ORIGINS=http://localhost:3000

# OpenAI API Configuration
OPENAI_API_KEY=your_openai_api_key_here
LLM_MODEL=gpt-5-mini
STT_MODEL=gpt-live-transcribe
TTS_MODEL=gpt-4o-mini-tts

# Data & Security Settings
JWT_SECRET=your_super_secret_jwt_key
ENCRYPTION_KEY=your_encryption_key_for_storage
COMPANY_RETENTION_POLICY_REF=XOTO-CORP-RETENTION-POL-2024-V3
```

---

## 8. Running the System with Docker Compose

Run the entire application in containerized mode with a single command:

```bash
# Build and start all services
docker-compose up --build

# Backend will be available at: http://localhost:8000
# Frontend will be available at: http://localhost:3000
# API Documentation (Swagger): http://localhost:8000/docs
```

To run tests within the backend container:

```bash
docker-compose run --rm backend pytest
```

---

## 9. Regulatory Scope & Compliance

- **Jurisdiction:** United Arab Emirates (UAE) / Dubai / DIFC.
- **Retention Standard:** Adheres strictly to the existing company data-retention policy (`XOTO-CORP-RETENTION-POL-2024-V3`); no bespoke retention duration is introduced.

---

## 10. Phase 5: Official Knowledge Base & RAG Architecture

The Knowledge Base engine grounds all factual UAE real estate, tenancy, mortgage, investment, Golden Visa, area guide, partner developer, and platform policy inquiries:

- **Source Document:** Official Xobia Knowledge Base (`Xobia_KB_v2_FINAL.md`).
- **Master Knowledge Store:** `backend/app/data/knowledge_base/xobia_kb_master.json` (48 concrete articles + 28 Domain 12 glossary terms).
- **Scope & Activation Boundaries:**
  - **Articles 1–8 (`ACTIVE`):** Property purchase process, DLD/Trustee fees, freehold vs leasehold, required documents, Ejari registration, tenant rights & eviction, rental costs, RERA rental index.
  - **Articles 9–12 (`PARTIALLY_ACTIVE`):** Educational mortgage guidelines, eligibility criteria, and fee structures. Conventional calculations and loan applications are strictly blocked (deferring to deterministic tools in Phase 3).
  - **Articles 13–24 (`ACTIVE`):** Investment yields, short vs long-term rentals, Golden Visa 2M AED threshold, capital appreciation drivers, off-plan buying journey, escrow account (Law 8/2007), Oqood registration, snagging/handover, delay remedies, and assignment.
  - **Articles 25–28 (`EXCLUDED`):** Explicitly excluded from Phase 5 scope. Preserved in master JSON with `status: EXCLUDED`; zero calculation logic or APIs exposed; strictly never retrieved.
  - **Articles 30–53 (`ACTIVE`):** Comprehensive Dubai area guides (Downtown, Marina, Palm Jumeirah, Business Bay, Dubai Hills, JVC, etc.), Xoto platform identity, services, partner developers (Emaar, Nakheel, Sobha, Damac, Meraas), and human escalation.
- **Strict PRD RAG Architecture Pipeline:**
  - `Knowledge Documents → Embeddings → Vector Database → Retriever → Reranker → Relevant Context → LLM`
  - **Embedding Model:** OpenAI `text-embedding-3-small` (1536-dimensional unit-normalized embeddings).
  - **Vector Database:** `VectorDatabase` (`backend/app/services/vector_store.py`) executing vector dot product cosine similarity with status exclusion filtering.
  - **Retriever:** Pure vector distance retrieval of top-k candidate document vectors.
  - **Reranker:** Scope boundary filtering (excludes 25–28, blocks 9–12 loan calculations), statutory disclaimer enforcement, and Domain 11.4 low-confidence fallback (< 0.40) offering human specialist handoff.
  - **Prompt Injection Defense:** Strips adversarial role-play and jailbreak prompt injection patterns prior to embedding.
- **PRD Function & Gateway API:**
  - Function: `retrieve_kb(query)`
  - Gateway Endpoint: `GET /api/gateways/kb?query=...`
- **Automated Test Suite:**
  ```bash
  python -m unittest backend/tests/test_phase5_kb_rag.py
  ```

