import type { AgentEvent } from './transport'
import type { SimulationResult } from '@/types/domain'
export type AgentState={status:string;simulation:SimulationResult|null;activity:unknown[]}
export const initialAgentState=():AgentState=>({status:'idle',simulation:null,activity:[]})
/** Handle snapshots and the documented root-property JSON Patch subset emitted by this backend. */
export function reduceAgentState(previous:AgentState,event:AgentEvent):AgentState{
 if(event.type==='STATE_SNAPSHOT'){const snapshot=event.snapshot as AgentState;if(!snapshot||typeof snapshot.status!=='string')throw new Error('Invalid agent state');return snapshot}
 if(event.type==='STATE_DELTA'){
  const next={...previous};if(!Array.isArray(event.delta))throw new Error('Invalid state patch');for(const op of event.delta as {op:string;path:string;value:unknown}[]){if(op.op!=='replace'&&op.op!=='add')throw new Error('Unsupported state patch operation');switch(op.path){case '/status':next.status=String(op.value);break;case '/simulation':next.simulation=op.value as SimulationResult|null;break;case '/activity':next.activity=op.value as unknown[];break;default:throw new Error('Unsupported state patch path')}}return next
 }
 return previous
}
