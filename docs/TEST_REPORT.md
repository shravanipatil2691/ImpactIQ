# MVP verification report

## Executed checks

- `python -m pytest -q backend/tests`: 13 passed (12.96 seconds). Covers all three scenarios and sandbox execution, individually feasible/combined infeasible decisions, unsafe plan rejection, stale certificates and reanalysis, duplicate/concurrent execution, rejected approvals, invalid input, cost constraints, AG-UI event streaming and persistence, required MCP failure, read endpoints, real MCP connector discovery and scenario reset.
- Python compilation: passed.
- TypeScript syntax transpilation using installed compiler: 16 files, zero syntax errors. This is **not** a full semantic TypeScript check or Next.js build.
- Frontend dependency declarations matched the supplied pnpm lockfile.
- Local API latency sample: five sequential combined-decision POST simulations (including startup, discovery and retrieval from three real MCP subprocesses per request) took 1174, 862, 990, 891 and 986 ms; median 986 ms. This is an in-process HTTP test client measurement, not browser/network latency or a production benchmark. No LLM was called.

## Not verified in this environment

- Installing frontend packages, full TypeScript type checking, Next.js production build and actual browser interaction: npm registry DNS lookup failed (`EAI_AGAIN`). Run the commands in README after installation on a machine with internet access.
- External Gemini/OpenAI calls: optional API credentials and provider network access were not available.
- Full AG-UI/MCP SDK conformance certification, production ERP integration, authentication, load testing, cross-platform browser compatibility and production latency are outside the verified scope.

## Local browser acceptance checklist

After starting both services, open the six routes, check the responsive layout, select and edit decisions, stream an analysis, inspect graph/evidence/commitments, compare and approve plans, mutate source data to block stale execution, reanalyze and execute, check history and exports, and test all three MCP connector cards. Verify the optional analyst with and without a valid API key. Check browser console and run the production build. Report any discrepancies before using the project beyond a local demo.
