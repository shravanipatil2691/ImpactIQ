import { getBaseUrl } from '@/lib/api/http-adapter'
import type { RunAgentInput } from '@/lib/api/contracts'
export interface AgentEvent{type:string;[key:string]:unknown}
export const newId=()=>globalThis.crypto?.randomUUID?.()??`${Date.now()}-${Math.random().toString(36).slice(2)}`
/** Parse SSE frames incrementally; handles chunk boundaries, CRLF and multiline data. */
export class SSEParser {
 private buffer=''
 push(chunk:string):AgentEvent[]{
  this.buffer+=chunk;const output:AgentEvent[]=[];let match:RegExpExecArray|null
  while((match=/\r?\n\r?\n/.exec(this.buffer))!==null){const frame=this.buffer.slice(0,match.index);this.buffer=this.buffer.slice(match.index+match[0].length);const data=frame.split(/\r?\n/).filter(l=>l.startsWith('data:')).map(l=>l.slice(5).replace(/^ /,'')).join('\n');if(!data)continue;const event=JSON.parse(data) as AgentEvent;if(typeof event.type!=='string')throw new Error('Invalid AG-UI event');output.push(event)}
  return output
 }
}
export async function runAgent(input:RunAgentInput,onEvent:(event:AgentEvent)=>void,signal:AbortSignal){
 const response=await fetch(`${getBaseUrl()}/api/v1/agent/run`,{method:'POST',headers:{'Content-Type':'application/json',Accept:'text/event-stream'},body:JSON.stringify(input),signal})
 if(!response.ok||!response.body)throw new Error(`Agent connection failed (${response.status})`)
 const reader=response.body.getReader(),decoder=new TextDecoder(),parser=new SSEParser();let finished=false
 try{for(;;){const {value,done}=await reader.read();const chunk=done?decoder.decode():decoder.decode(value,{stream:true});for(const event of parser.push(chunk)){if(signal.aborted)throw new DOMException('Cancelled','AbortError');if(event.type==='RUN_STARTED'&&event.runId!==input.runId)throw new Error('Unexpected run ID');onEvent(event);if(event.type==='RUN_ERROR')throw new Error(String(event.message??'Agent run failed'));if(event.type==='RUN_FINISHED'){if(event.runId!==input.runId)throw new Error('Unexpected finished run ID');finished=true}}if(done)break}if(!finished)throw new Error('Agent stream ended without RUN_FINISHED')}
 finally{await reader.cancel().catch(()=>{});reader.releaseLock()}
}
