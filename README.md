<div align="center">

# Veridra

**Research deeply. Write clearly. Publish responsibly.**

An open-source, multi-agent AI editorial studio that turns any topic into source-grounded, fact-checked, social-ready posts for **LinkedIn**, **X (Twitter)**, and **Instagram** — with live step-by-step streaming and 1-click publishing.

[![FastAPI + LangGraph](https://img.shields.io/badge/Backend-FastAPI%20%7C%20LangGraph%20%7C%20Python%203.11%2B-4f46e5?style=flat-square)](#tech-stack)
[![React + TypeScript](https://img.shields.io/badge/Frontend-React%20%7C%20TypeScript%20%7C%20Tailwind%20v4-ec4899?style=flat-square)](#tech-stack)
[![Verification](https://img.shields.io/badge/Verified-pytest%20%7C%20vitest%20%7C%20mypy%20%7C%20ruff-14b8a6?style=flat-square)](#testing--verification)

</div>

---

## Why Veridra?

Most AI writing tools generate a post from a single opaque prompt — often inventing statistics, dumping unformatted Markdown (`**bold**`, `## headings`) that breaks on social platforms, and offering zero visibility into where claims came from.

**Veridra** replaces single-prompt guesswork with a deterministic **LangGraph** editorial workflow:
1. **Researches the live web first** using Tavily Search and an SSRF-safe public page fetcher.
2. **Writes platform-native drafts** with **bold** takeaways, *italics*, scannable bullet points, and inline embedded `[Source](url)` links.
3. **Critiques & polishes** against a 7-dimension editorial rubric before passing to verification.
4. **Fact-checks every material claim** against collected evidence, stripping hallucinated citations and flagging uncertain points before you copy or publish.
5. **Formats & publishes in 1 click** to LinkedIn, X, and Instagram.

---

## How the Multi-Agent Pipeline Works

```mermaid
flowchart LR
    UI["React + Vite Studio"] <-->|"REST + SSE (/events)"| API["FastAPI Backend"]
    API --> Graph["LangGraph StateGraph"]
    Graph --> R["1. Researcher<br/>(Tavily + Safe Fetch)"]
    R --> Gate{"Evidence Gate"}
    Gate -->|"Sufficient"| W["2. Writer<br/>(Formatted Draft + Inline Links)"]
    Gate -->|"Retry (<= 1)"| R
    W --> E["3. Editor<br/>(7-Part Rubric)"]
    E -->|"Revise (<= 3)"| W
    E -->|"Approve"| FC["4. Fact Checker<br/>(Claim Audit)"]
    FC -->|"Remediate (<= 2)"| W
    FC -->|"Pass / Warn"| Fin["5. Finalizer<br/>(Artifact + Clean Sources)"]
    Fin --> Pub["Post Studio & 1-Click Publish"]
```

### The Four Specialized Agents
| Agent | Responsibility | Key Output |
|---|---|---|
| **Researcher** | Plans focused search queries, retrieves Tavily results, fetches public pages safely, and builds an evidence package. | Structured `ResearchBrief` with source IDs, URLs, publishers, and excerpts. |
| **Writer** | Drafts a post tailored to platform, audience, tone, and depth with bold lead-ins, italics, bullet points, and inline links. | `WriterDraftOutput` with `factual_claims` linked to `evidence_ids`. |
| **Editor** | Evaluates `clarity`, `depth`, `audience`, `structure`, `platform_fit`, `specificity`, and `tone` (0–100). | `EditorResult` (`approve`, `revise`, or `blocked`) with actionable feedback. |
| **Fact Checker** | Audits every factual claim against retrieved evidence, strips invalid `evidence_ids`, and flags unsupported claims. | `FactCheckResult` (`pass`, `needs_revision`, `blocked`) + claim-level statuses. |

---

## Webapp Features & Sections

### Home Dashboard (`/`)
- **At-a-glance creator metrics**: Total runs, completion rate, average editorial score, evidence coverage, median latency, and token/cost summaries.
- **Recent drafts feed**: Jump directly into any live run or finished draft in Post Studio.

### Create Post (`/create`)
- **Brief Builder**: Enter your topic, target platform (**LinkedIn**, **X Thread**, or **Instagram Caption**), depth (`concise`, `standard`, `deep`), audience, goal, tone, and optional user-supplied reference URLs.
- **AI Assistant Selector**: Choose from configured providers (**OpenRouter**, **Groq**, **Google Gemini**, **ChatGPT/OpenAI**) directly in the UI.
- **Demo Mode**: Try the complete pipeline end-to-end with deterministic sample data without using any API credits.

### Live Step-by-Step Progress (`/runs/:runId`)
- Streams real-time progress over **Server-Sent Events (SSE)** (`Researching` → `Writing` → `Polishing` → `Fact-Checking` → `Finalizing`).
- Displays retrieved source count, editorial revision count, fact-check pass count, detailed event log, and cooperative **Cancel** support.

### Post Studio (`/runs/:runId/studio`)
- **Side-by-Side Editor & Channel Preview**:
  - **Styled View**: Renders headings, **bold**, *italics*, bullet/numbered lists, and clickable embedded links.
  - **Social Text View**: Shows the exact Unicode-formatted text (`𝗯𝗼𝗹𝗱`, `𝑖𝑡𝑎𝑙𝑖𝑐`, `•` bullets) ready for LinkedIn, X, and Instagram.
- **1-Click Social Publishing**:
  - **Works out of the box**: Copies formatted post-ready text to the clipboard and opens **LinkedIn** or **X** with your post pre-filled in their composer (or copies the formatted caption and launches **Instagram**).
  - **Optional Direct API Posting**: Add `LINKEDIN_ACCESS_TOKEN` + `LINKEDIN_PERSON_URN` or `X_ACCESS_TOKEN` in `backend/.env` to publish directly in the background via `/api/v1/artifacts/{id}/publish`.
- **Safe Versioning & Export**: Save manual edits as new artifact versions while preserving the AI original, or export as `.md` or `.txt`.
- **Sources & Fact Checks Tabs**: Inspect every retrieved source and audit each claim (`supported`, `partially_supported`, `uncertain`, `unsupported`, `contradicted`) with one-click navigation from a claim to its backing source.

### Projects (`/projects`)
- Group related posts under shared campaign defaults (default platform, audience, tone, and source preferences).

### Benchmarks (`/benchmarks`)
- Run paired **Single-Agent Baseline vs. Multi-Agent Veridra** comparisons across the built-in 30-topic evaluation dataset (`veridra-eval-v1`), measuring editorial score, evidence coverage, unsupported claims, latency, and token usage.

### Settings (`/settings`)
- **Theme Switcher**: Apple-inspired Aurora Liquid Glass UI in **Light editorial**, **Midnight dark**, or **System match**.
- **Default AI Assistant**: Set your preferred default model across runs.
- **Integrations & Connected Social Accounts**: Live configuration status for AI providers, Tavily Search, and LinkedIn / X / Instagram publishing readiness.

---

## Multi-Provider AI & Automatic Failover

Veridra supports multiple LLM providers out of the box and wraps live execution in **`ResilientLLMProvider`**:
- **Supported Providers**: OpenRouter (`openai/gpt-4o-mini`), Groq (`openai/gpt-oss-120b`, `qwen/qwen3.8-27b`), Google Gemini (`gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3.5-flash-lite`), and OpenAI (`gpt-4o-mini`, `gpt-4o`).
- **Automatic Failover**: If a provider returns `429` (rate limit), `503` (heavy traffic), or times out mid-run, Veridra automatically fails over to your next configured provider so multi-step runs finish reliably.
- **Truthful Provenance**: Every step records the exact `provider` and `model` that fulfilled it in `node_metrics`.

---

## Security, Trust & Guardrails

- **Deterministic Loop Ceilings**: Python routing code (`backend/app/graph/routing.py`) strictly enforces `MAX_EDITOR_REVISIONS=3`, `MAX_FACT_REMEDIATIONS=2`, `MAX_RESEARCH_RETRIES=1`, `MAX_GRAPH_STEPS=24`, and `RUN_TIMEOUT_SECONDS=600`.
- **SSRF Protection**: `backend/app/core/security.py` restricts fetching to `http`/`https`, resolves DNS before connecting, and blocks loopback, private, link-local, and cloud metadata IP ranges across redirects.
- **Prompt-Injection Isolation**: Retrieved web snippets and user-supplied page contents are wrapped inside `<untrusted_source_data>` tags and never elevated to system instructions.
- **No Fabricated Metrics or Costs**: If a provider omits token counts, or a model has no entry in `backend/app/core/pricing.py`, or a run uses Demo Mode, telemetry reports `Not reported` / `Unavailable` honestly.
- **Secret Redaction**: API keys and social tokens are masked in all application logs (`secret_values()`).

---

## Tech Stack

| Layer | Technologies |
|---|---|
| **Frontend** | React 18, TypeScript, Vite, Tailwind CSS v4, TanStack Query, React Router, Lucide Icons |
| **Backend** | FastAPI, Python 3.11+, LangGraph, Pydantic v2, SQLAlchemy 2, Alembic, HTTPX |
| **AI & Search** | OpenRouter, Groq, Google Gemini (`google-genai`), OpenAI, Tavily Search |
| **Database** | SQLite (WAL mode locally) / PostgreSQL 16+ (production) |
| **Testing & Quality** | `pytest`, `ruff`, `mypy`, `vitest`, Testing Library, `tsc`, `eslint` |

---

## Quick Start (Local Development)

### Prerequisites
- **Python 3.11+** (tested on Python 3.13)
- **Node.js 20+** and **npm**

### 1. Backend Setup
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # Add at least one AI key + TAVILY_API_KEY (or set DEMO_MODE=true)
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```
- Health check: `http://127.0.0.1:8000/health`
- API docs (development only): `http://127.0.0.1:8000/docs`

### 2. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
Open **`http://localhost:5173`** in your browser. Vite automatically proxies `/api` and `/health` requests to `http://127.0.0.1:8000`.

---

## Docker & Production Deployment

### Docker Compose
```bash
cp .env.example .env
# Add your API keys or set DEMO_MODE=true in .env
docker compose up --build
```
- **Frontend UI**: `http://localhost:8080`
- **Backend API**: `http://localhost:8000`
- **With PostgreSQL**: `docker compose --profile postgres up --build`

### Production PostgreSQL Checklist
1. Set `DATABASE_URL=postgresql+psycopg://user:password@host:5432/veridra`.
2. Run `alembic upgrade head` against PostgreSQL before starting workers.
3. Set `APP_ENV=production` (disables `/docs` and `/openapi.json`) and configure `CORS_ORIGINS`.

---

## Environment Variables

Copy `.env.example` to `backend/.env` (or `.env` for Docker):

| Variable | Purpose | Default |
|---|---|---|
| `APP_ENV` | `development`, `test`, or `production` | `development` |
| `LLM_PROVIDER` | Default LLM provider (`openai`, `groq`, `openrouter`, `gemini`) | `gemini` |
| `OPENAI_API_KEY` | OpenAI API key (`gpt-4o-mini`, `gpt-4o`) | empty |
| `GROQ_API_KEY` | Groq API key (`openai/gpt-oss-120b`, `qwen/qwen3.8-27b`) | empty |
| `OPENROUTER_API_KEY` | OpenRouter API key (`openai/gpt-4o-mini`) | empty |
| `GEMINI_API_KEY` | Google Gemini API key | empty |
| `GEMINI_MODEL` | Target Gemini model ID | `gemini-3.6-flash` |
| `TAVILY_API_KEY` | Tavily web research API key | empty |
| `DEMO_MODE` | Run deterministically without live API keys | `false` |
| `LINKEDIN_ACCESS_TOKEN` | *(Optional)* Direct LinkedIn publishing token | empty |
| `LINKEDIN_PERSON_URN` | *(Optional)* LinkedIn author URN (`urn:li:person:...`) | empty |
| `X_ACCESS_TOKEN` | *(Optional)* Direct X API v2 user token | empty |
| `DATABASE_URL` | SQLite locally or PostgreSQL URI in production | `sqlite:///./veridra.db` |
| `EDITOR_APPROVAL_THRESHOLD` | Minimum editorial score (0–100) for approval | `75` |
| `MAX_EDITOR_REVISIONS` | Maximum writer ↔ editor revision passes | `3` |
| `MAX_FACT_REMEDIATIONS` | Maximum fact-checker → writer remediation passes | `2` |

---

## API Overview

| Method & Endpoint | Description |
|---|---|
| `GET /health` | Service health check |
| `GET /api/v1/settings/integrations` | Configured AI models, search status, and social connection status |
| `GET /api/v1/dashboard/summary` | Aggregate metrics across runs |
| `POST /api/v1/projects` / `GET /api/v1/projects` | Create and list content projects |
| `POST /api/v1/runs` | Start a new multi-agent or single-agent post generation run |
| `GET /api/v1/runs/{id}` | Full run detail (drafts, sources, claims, metrics, events) |
| `GET /api/v1/runs/{id}/events` | Server-Sent Events (SSE) stream for live progress |
| `POST /api/v1/runs/{id}/cancel` / `POST /api/v1/runs/{id}/retry` | Cancel or re-run a workflow |
| `PUT /api/v1/artifacts/{id}` | Save a user-edited draft as a new version |
| `GET /api/v1/artifacts/{id}/export?format=md\|txt` | Export draft as Markdown or plain text |
| `POST /api/v1/artifacts/{id}/publish` | Publish via connected social API or return pre-filled composer URL |
| `POST /api/v1/benchmarks` / `GET /api/v1/benchmarks/{id}` | Run and inspect single-agent vs. multi-agent benchmarks |

---

## Project Structure

```text
Veridra/
├── backend/
│   ├── app/
│   │   ├── agents/          # Researcher, Writer, Editor, FactChecker, SingleAgent
│   │   ├── api/v1/          # FastAPI REST, SSE & publishing routes
│   │   ├── core/            # Settings, pricing rate card, SSRF security, log redaction
│   │   ├── db/              # SQLAlchemy models & session setup
│   │   ├── evaluation/      # 30-topic evaluation dataset & benchmark runner
│   │   ├── graph/           # LangGraph workflow, nodes, state & routing
│   │   ├── prompts/         # Versioned SHA-256-hashed prompt templates
│   │   ├── providers/       # Gemini, OpenAI-compatible, Resilient failover, Tavily, Mock
│   │   └── services/        # Persistence, export, social publishing
│   ├── alembic/             # Database migrations
│   └── tests/               # Pytest unit & integration suite
├── frontend/
│   └── src/
│       ├── components/      # Aurora glass cards, ModelSelector, FormattedPostPreview
│       ├── features/        # Dashboard, CreateRun, LiveRun, ContentStudio, Projects, Benchmarks, Settings
│       └── lib/             # API client, SSE hook, social Unicode formatter
├── scripts/verify.sh        # Unified lint, typecheck, test & build script
└── docker-compose.yml
```

---

## Testing & Verification

Run all backend and frontend checks in a single command:
```bash
./scripts/verify.sh
```
This executes:
- **Backend**: `ruff check app tests`, `mypy app`, `pytest -v`
- **Frontend**: `vitest run`, `tsc -b --noEmit`, `eslint .`, `vite build`
