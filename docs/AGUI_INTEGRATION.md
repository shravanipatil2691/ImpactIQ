# AG-UI integration

POST `/api/v1/agent/run`, JSON body, `Accept: text/event-stream`. The connected UI uses fetch streaming and AbortController. The backend implements a subset of AG-UI event shapes, not independently certified full protocol conformance. See https://docs.ag-ui.com/.

Example body:
```json
{"threadId":"SCN-002","runId":"run-1","messages":[],"state":{},"tools":[],"context":[],"forwardedProps":{"simulationRequest":{"scenarioId":"SCN-002","scenarioRevision":1,"sourceDataVersion":"use current scenario version","selectedDecisionIds":["D-101","D-102","D-103"],"overrides":[],"constraints":{"protectCustomerCommitments":true,"currency":"USD"},"priorityPolicy":"protect_commitments"}}}
```
Use the revision and sourceDataVersion from GET /api/v1/scenarios/SCN-002, not the example placeholders. Explanation runs use `forwardedProps: {operation: "explain", simulationId: "...", question: "..."}`.

Events: RUN_STARTED, TOOL_CALL_START/ARGS/END/RESULT, STEP_STARTED/FINISHED, STATE_SNAPSHOT, STATE_DELTA, CUSTOM, TEXT_MESSAGE_START/CONTENT/END, RUN_FINISHED or RUN_ERROR. The state delta subset replaces `/status` and `/simulation` (the client also accepts `/activity`). The `impactiq.metrics` custom event contains measured elapsedMs and simulationId. Tool progress represents actual MCP retrieval; it does not reveal private reasoning. The full simulation arrives at completion, not as separately calculated partial business results. Approval and execution use REST, with authoritative server checks. No mock transport remains.
