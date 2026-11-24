# ImpactIQ API contract

The browser calls only the FastAPI service at `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`). The connected backend is the only data mode. API errors are surfaced and are never converted into demo responses. JSON uses camelCase, UTC ISO-8601 timestamps, USD integer minor units, and collection envelopes `{ "items": [] }`.

## Routes

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/health` | Service readiness and data mode |
| GET | `/api/v1/overview` | Derived overview metrics and priority decisions |
| GET | `/api/v1/scenarios` | `{items: Scenario[]}` |
| GET | `/api/v1/scenarios/{scenarioId}` | Scenario details |
| POST | `/api/v1/scenarios/{scenarioId}/reset` | Restore demo/source snapshot |
| GET | `/api/v1/decisions` | `{items: ProposedDecision[]}` |
| GET | `/api/v1/decisions/{decisionId}` | Decision and relationships |
| GET | `/api/v1/dependencies?scenarioId={scenarioId}&entityId={entityId}` | Dependency graph |
| POST | `/api/v1/simulations` | SimulationRequest → SimulationResult (fallback only) |
| GET | `/api/v1/simulations/{simulationId}` | Retrieve immutable result |
| POST | `/api/v1/approvals` | ApprovalRequest → DecisionCertificate |
| GET | `/api/v1/certificates/{certificateId}` | Certificate |
| POST | `/api/v1/executions` | ExecutionRequest → execution result |
| GET | `/api/v1/history` | `{items: AuditRecord[]}` |
| GET | `/api/v1/integrations` | `{items: IntegrationStatus[]}` |
| POST | `/api/v1/integrations/{integrationId}/test` | Test a connector |
| POST | `/api/v1/demo/mutate-source` | Mutate fictional source data and advance version |
| POST | `/api/v1/agent/run` | `RunAgentInput` → AG-UI SSE response |

### Example simulation

Request: `{ "scenarioId":"SCN-002", "scenarioRevision":1, "sourceDataVersion":"MEG-DEMO-2025.04", "selectedDecisionIds":["D-101","D-102","D-103"], "overrides":[], "constraints":{"protectCustomerCommitments":true,"currency":"USD"}, "priorityPolicy":"protect_commitments" }`.

Response shape: `{ "id":"SIM-...", "scenarioId":"SCN-002", "scenarioRevision":1, "sourceDataVersion":"MEG-DEMO-2025.04", "generatedAt":"2025-04-14T14:00:00Z", "completeness":"complete", "status":"critical", "resourceConflicts":[], "impactSummary":{}, "graph":{"nodes":[],"edges":[]}, "affectedCommitments":[], "evidence":[], "alternatives":[], "recommendedPlanId":"PLAN-...", "warnings":[] }`.

Errors use `{ "code":"STALE_SOURCE", "message":"Source data changed.", "details":{}, "requestId":"req_..." }`. Clients distinguish validation, connectivity, stale-data and unexpected errors. Approval/execution writes are not automatically retried; Server-side feasibility, version and idempotency checks are implemented; production identity and authorization are outside this local MVP.
