import type { Scenario, SimulationRequest, SimulationResult, ProposedDecision, DecisionCertificate, AuditRecord, DependencyGraph, EvidenceRecord } from '@/types/domain'
export interface Collection<T>{items:T[]}
export interface ApiError{code:string;message:string;details?:unknown;requestId?:string}
export interface IntegrationStatus{id:string;name:string;description:string;status:string;mode:string;tools:string[];lastCheckedAt:string|null;lastLatencyMs:number|null}
export interface Overview{metrics:{pending:number;conflicts:number;commitments:number;exposure:number};decisions:ProposedDecision[];recentActivity:AuditRecord[];note:string}
export interface ApprovalRequest{scenarioId:string;simulationId:string;selectedPlanId:string;scenarioRevision:number;sourceDataVersion:string;action:'approve'|'reject';note:string}
export interface ExecutionResult{certificate:DecisionCertificate;scenario:Scenario}
export interface RunAgentInput{threadId:string;runId:string;messages:Array<{id:string;role:'user'|'assistant'|'system'|'tool';content?:string}>;state:Record<string,unknown>;tools:unknown[];context:unknown[];forwardedProps:Record<string,unknown>}
export interface ApiAdapter{
 scenarios():Promise<Collection<Scenario>>;scenario(id:string):Promise<Scenario>;overview():Promise<Overview>;decisions():Promise<Collection<ProposedDecision>>;history():Promise<Collection<AuditRecord>>;integrations():Promise<Collection<IntegrationStatus>>;testConnector(id:string):Promise<IntegrationStatus>;reset(id:string):Promise<Scenario>;mutate(id:string):Promise<Scenario>;simulate(request:SimulationRequest,signal?:AbortSignal):Promise<SimulationResult>;approve(body:ApprovalRequest):Promise<DecisionCertificate>;certificate(id:string):Promise<DecisionCertificate>;execute(certificateId:string,idempotencyKey:string):Promise<ExecutionResult>;dependencies(scenarioId:string,entityId:string):Promise<{graph:DependencyGraph;evidence:EvidenceRecord[]}>;
}
