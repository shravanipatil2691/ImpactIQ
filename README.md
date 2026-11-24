# VitalEdge ImpactIQ — Connected MVP

A proposed VitalityAI extension for pre-transaction decision validation. All records belong to the fictional Meridian Equipment Group. This is not an official VitalEdge product or a production ERP integration.

## Quick start (Windows PowerShell)

Install Python 3.11–3.13 and Node.js 22 or later. Internet access is needed for dependency installation. Extract the ZIP and open a terminal in the `ImpactIQ` folder (the folder containing `package.json`).

Terminal 1 — backend:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
Copy-Item backend/.env.example backend/.env
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --env-file backend/.env
```

Terminal 2 — frontend, in the same folder:

```powershell
Copy-Item .env.example .env.local
corepack enable
corepack pnpm install --frozen-lockfile
corepack pnpm dev
```

If Corepack is not available, install the package manager version specified in `package.json`, or use `npm install` and `npm run dev` (npm may resolve different versions). Open http://localhost:3000. API docs: http://127.0.0.1:8000/docs.

On macOS/Linux use `.venv/bin/python` instead of `.\.venv\Scripts\python.exe`, and `cp` instead of `Copy-Item`. Run both processes from the project root. Do not use multiple backend workers for this local demo.

## Environment variables

No AI key is required for business simulation. The frontend `.env.local` uses `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000`. Optional `GEMINI_API_KEY` or `OPENAI_API_KEY` and model names go in `backend/.env` only; Gemini is preferred if both are set. Optional provider failures fall back to a labeled deterministic explanation. The backend must be started with `--env-file backend/.env` to load these settings. Never put keys in NEXT_PUBLIC variables. Keep the application local; it uses a fictional fixed operator and does not implement production authentication or authorization.

## Demonstration

1. Open Decision Workspace, select Combined Pending Decisions, select all three pending decisions and Analyze Impact.
2. Inspect the 11-unit demand against 10 available units, actual MCP tool activity, dependency graph and commitments.
3. Compare alternatives. The West Branch alternative is feasible under default constraints.
4. Approve a feasible plan with a note; inspect the certificate. Approval is separate from execution.
5. Simulate Source Data Change. The backend invalidates the certificate and blocks execution. Reanalyze and approve the new result.
6. Execute in Demo Sandbox. Inspect history and connector statuses. Reset the scenario to repeat (audit records remain).
7. Try Single Parts Transfer and Equipment Allocation Conflict, or set a zero additional-cost limit to demonstrate no feasible alternative.

## Architecture

Next.js UI → FastAPI HTTP + AG-UI-style standard SSE event subset → deterministic Python engine → SQLite. The backend starts three actual independent stdio MCP JSON-RPC subprocesses, negotiates MCP 2025-06-18, discovers tools and retrieves source records. Connections are parallel across departments. The backend verifies source versions and uses atomic SQLite transactions for approval and execution. Optional LLM explanations are separate from calculations. No external database or message broker required.

The original browser-only mock mode was replaced with a single connected fictional backend to avoid competing calculation logic. Data persists in `backend/data/impactiq.sqlite3` (automatically created). Use scenario reset for demonstrations. To erase all local history, stop backend and delete its database files. Do not do this to any production database.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q backend/tests
corepack pnpm typecheck
corepack pnpm build
```

See `docs/TEST_REPORT.md` for checks actually performed and outstanding checks. Frontend package installation/build and browser tests require a working npm registry connection. Optional model calls require a valid key and internet. This is a limited MVP, not an audited production system. The simulation models three seeded scenarios and a small set of alternatives, not arbitrary ERP transactions; no live VitalEdge data is accessed. AG-UI uses a documented subset and MCP uses a minimal stdio implementation, not an official conformance-certified SDK integration.
