import type { ApiAdapter } from './contracts'
export const base=(process.env.NEXT_PUBLIC_API_BASE_URL??'http://localhost:8000').replace(/\/$/,'')
export async function request<T>(path:string,init?:RequestInit):Promise<T>{
 const response=await fetch(`${base}${path}`,{...init,cache:'no-store',headers:{'Content-Type':'application/json',...init?.headers}})
 if(!response.ok){let msg=`Request failed (${response.status})`;try{const body=await response.json();msg=body.message??msg}catch{}throw new Error(msg)}
 return response.json() as Promise<T>
}
const post=<T,>(path:string,body:unknown,signal?:AbortSignal)=>request<T>(path,{method:'POST',body:JSON.stringify(body),signal})
const p='/api/v1'; const enc=encodeURIComponent
export const httpAdapter:ApiAdapter={
 scenarios:()=>request(`${p}/scenarios`),scenario:id=>request(`${p}/scenarios/${enc(id)}`),overview:()=>request(`${p}/overview`),decisions:()=>request(`${p}/decisions`),history:()=>request(`${p}/history`),integrations:()=>request(`${p}/integrations`),testConnector:id=>post(`${p}/integrations/${enc(id)}/test`,{}),reset:id=>post(`${p}/scenarios/${enc(id)}/reset`,{}),mutate:scenarioId=>post(`${p}/demo/mutate-source`,{scenarioId}),simulate:(body,signal)=>post(`${p}/simulations`,body,signal),approve:body=>post(`${p}/approvals`,body),certificate:id=>request(`${p}/certificates/${enc(id)}`),execute:(certificateId,idempotencyKey)=>post(`${p}/executions`,{certificateId,idempotencyKey}),dependencies:(scenarioId,entityId)=>request(`${p}/dependencies?scenarioId=${enc(scenarioId)}&entityId=${enc(entityId)}`)
}
