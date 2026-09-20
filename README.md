<div align="center">

<img src="assets/banner.svg" alt="Orbit — See the signal before it becomes noise" width="100%">

<br>

![License](https://img.shields.io/badge/LICENSE-MIT-84cc16?style=for-the-badge)
![Python](https://img.shields.io/badge/PYTHON-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FASTAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/REACT-VITE-61DAFB?style=for-the-badge&logo=react&logoColor=black)
![Chain](https://img.shields.io/badge/CHAIN-ROBINHOOD_4663-00C805?style=for-the-badge)
![Execution](https://img.shields.io/badge/EXECUTION-PAPER_ONLY-f59e0b?style=for-the-badge)
![Agents](https://img.shields.io/badge/AGENTS-5_CORE_·_UP_TO_10-a855f7?style=for-the-badge)
![MCP](https://img.shields.io/badge/MCP-STDIO_+_HTTP-ec4899?style=for-the-badge)

**A live crew of AI agents that reads on-chain data, meme narrative and risk — then argues from evidence, not hype.**

</div>

---

## Why Orbit

Most "AI trading" demos hand a model a chart and ask for a vibe. Orbit is built around the opposite idea:

> **A model may propose. Only deterministic code may promote.**

Five agents with distinct working styles debate a token in a live, interruptible conversation. Every contribution is a structured signal with evidence you can click through. A protection gate written in plain code — not a prompt — decides whether an `ENTER` survives. Everything ends in an immutable receipt and a paper-only ledger, so you can measure whether the crew is actually any good.

**Orbit never places a real order. There is no execution engine, wallet or broker integration.**

<br>

<img src="docs/screenshots/home.webp" alt="Orbit Signal Room" width="100%">

## Feature map

<table>
<tr>
<td width="50%" valign="top">

### 🧠 The crew
Five default characters — **Captain, Tactician, Scout, Forge, Sentinel** — each with a role, objective, budget, professional memory and skill slot. Run up to ten agents per dialogue, edit the roster mid-run, redirect the goal, or interrupt with a targeted message.

</td>
<td width="50%" valign="top">

### ⛓️ Native chain tools
Direct **Robinhood Chain RPC** tools — no MCP required. Contract identity, holders, pools, proxy/admin storage, mint and pause surfaces. Optional Blockscout and Bitquery connectors import holder snapshots and DEX trades.

</td>
</tr>
<tr>
<td valign="top">

### 📜 Decision Contract v1
Every reply carries a hidden, versioned `AgentSignal`: stance, calibrated confidence, evidence, assumptions, unknowns, blocking risks and invalidation conditions. The chat stays concise; the full signal is kept as an auditable artifact.

</td>
<td valign="top">

### 🛡️ Protection gate
`ENTER` is reduced to `WATCH` or `SKIP` on failed tasks, blocking risks, low confidence, stale signals, paused execution or too little *independently checkable* evidence. Protections can only lower a verdict, never raise one.

</td>
</tr>
<tr>
<td valign="top">

### 🧾 Decision Record
Each finished turn produces an immutable JSON receipt: team, tasks, signals, tool calls, protection outcome and artifacts — rendered in the Dialogue Audit panel with the exact evidence references behind every claim.

</td>
<td valign="top">

### 🧪 Paper Lab
Capture executable DEX observations, open protection-approved **paper** positions, close them against later observations and keep fees, adverse slippage and P&L. Positions are long-only and always `real_funds: false`.

</td>
</tr>
<tr>
<td valign="top">

### 📈 Replay and scorecards
Verdicts are replayed only against observations *after* their timestamp — no look-ahead. Scorecards report directional hit-rate and Brier calibration per agent. Measurements are observational: they never silently change prompts, models or sizing.

</td>
<td valign="top">

### 🔎 Deep Research
One report across Web, YouTube, TikTok, Instagram and on-chain data, with query expansion, evidence IDs, per-source status and stated limitations.

</td>
</tr>
<tr>
<td valign="top">

### 🧬 Memory v2
Compact dialogue notes, shared workspace memory, hybrid lexical + vector retrieval with provenance, and agent lessons that stay *proposals* until a human approves them. One-click Markdown export.

</td>
<td valign="top">

### 🔌 Skills, MCP and connectors
A 21-skill marketplace with readable operating contracts. MCP catalog over stdio and Streamable HTTP with approval gates for risky actions. GitHub, Notion, Slack, Google Drive, Telegram, YouTube and X connectors.

</td>
</tr>
</table>

<br>

<p align="center"><img src="docs/screenshots/skills.webp" alt="Skill marketplace" width="49%"> <img src="docs/screenshots/research.webp" alt="Deep Research" width="49%"></p>

## How a verdict is made

<img src="assets/pipeline.svg" alt="Chain data → five-agent crew → decision contract → protection gate → verdict → audit trail and paper lab" width="100%">

For an `ENTER`, the default gate requires a valid structured contribution, confidence at or above the threshold, no declared blocking risk, and at least one unique evidence item with **both a source and a concrete reference** — a URL, transaction hash, block, document location or tool-call ID. Evidence without a reference stays visible in the audit but does not count as independently checkable. A workspace can raise `min_enter_confidence` or `min_enter_evidence_refs`; `execution_paused` is a hard stop.

## Bring your own model

Orbit never assumes what you pay or which model you use. Connect a key once and reuse it across agents.

| | |
|---|---|
| **Providers** | OpenAI-compatible endpoints, Anthropic native Messages API, Gemini, plus a catalogue of 20+ presets (Groq, DeepSeek, OpenRouter, Kimi, MiniMax, Ollama, LM Studio, vLLM and more) |
| **Setup** | Three-step wizard, live key verification, automatic model discovery, Custom API base-URL auto-detection |
| **Safety** | Provider credentials encrypted at rest (Fernet); retry with backoff and up to three fallback connections |
| **Cost** | Token counts come from provider responses; USD cost stays `0` unless you configure per-million prices |
| **Local** | A built-in `mock` provider runs the whole app with **no API keys** |

## Also included

- **Durable runtime** — database checkpoints, task attempts, pause/resume/cancel, crash recovery and multi-worker leases; live events over reconnectable SSE with replay.
- **Workflow nodes** — agent, review, condition, parallel, human input, approval, MCP tool, artifact, final output. Standard and Constructive (explicit objections) modes.
- **Accounts** — HttpOnly sessions, password recovery, workspaces with owner/admin/member/viewer roles, per-account daily quotas.
- **Materials** — TXT, Markdown, code, JSON, CSV, HTML, PDF and DOCX are checked, stored and extracted before a run starts.
- **Interface** — RU/EN, responsive down to phones, local fonts, accessible dialogs.
- **Ops** — Docker Compose + Caddy (automatic TLS), health endpoint, backup / restore / verify / off-site upload scripts.

## Quick start

No API keys needed; the local profile uses the mock provider.

```bash
git clone https://github.com/AtenovD/orbit-chain-intelligence.git
cd orbit-chain-intelligence
./scripts/start.sh          # macOS / Linux
# .\Start-Orbit.ps1         # Windows
```

Open <http://127.0.0.1:8000>. API docs live at `/docs`.

<details>
<summary><b>Manual development setup</b></summary>

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python scripts/bootstrap_db.py      # local SQLite schema
(cd frontend && npm install && npm run build)
uvicorn orchestrator.main:app --reload
```

For the Vite dev server run `npm run dev` inside `frontend/`.

</details>

<details>
<summary><b>Production deployment</b></summary>

Copy `.env.example` to `.env` and set at minimum:

```env
APP_ENV=production
AUTH_REQUIRED=true
DATABASE_URL=postgresql+asyncpg://orbit:<password>@postgres:5432/orbit
SECRET_ENCRYPTION_KEY=<fernet-key>
CORS_ORIGINS=https://your-domain.example
```

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
docker compose -f compose.yaml -f compose.production.yaml up --build -d
```

Migrations (`alembic upgrade head`) run before the server starts on PostgreSQL, and Caddy obtains TLS automatically. Configure `DOMAIN`, `PUBLIC_URL` and SMTP as described in `.env.example`. A Russian-language VPS runbook with backup notes is in [docs/DEPLOYMENT_RU.md](docs/DEPLOYMENT_RU.md).

</details>

## Architecture

```text
frontend/            React + Vite + TypeScript single-page app
src/orchestrator/    FastAPI application
  runtime.py         durable run engine, checkpoints, leases
  decision_contracts.py · protections.py · verdict.py
  paper_trading.py   paper ledger, replay, scorecards
  chain_tools.py     Robinhood Chain RPC tools
  providers.py       model connections and discovery
  memory.py · research.py · mcp.py · skill_catalog.py
migrations/          Alembic revisions (PostgreSQL)
scripts/             start, backup, restore, verify, health check
tests/               backend suite (pytest)
```

## Tests

```bash
python -m pytest -q
cd frontend && npm run test -- --run && npm run lint && npm run build
```

## Disclaimer

Orbit is research software. Its output is not financial advice, and the paper ledger is not a broker, exchange or execution engine. Tokens launched on any chain can be worthless. Do your own research.

## License

[MIT](LICENSE)
