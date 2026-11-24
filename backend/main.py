"""ImpactIQ local demo API: real MCP transport, AG-UI SSE, SQLite transactions."""
import asyncio,json,os,time
from contextlib import asynccontextmanager
from typing import Literal,Any
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse,StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel,Field,ConfigDict,field_validator
try:
    from . import store
    from .engine import evaluate,now,uid,dt
    from .mcp_client import collect
    from .mcp_server import TOOLS
except (ImportError, ValueError):
    import store
    from engine import evaluate,now,uid,dt
    from mcp_client import collect
    from mcp_server import TOOLS

class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class Override(Strict):
    decisionId:str;quantity:int|None=Field(None,ge=0,le=10000,strict=True);sourceBranchId:str|None=None;requiredAt:str|None=None;priority:Literal['normal','high','critical']|None=None
    @field_validator('requiredAt')
    @classmethod
    def valid_date(cls,v):
        if v is not None and dt(v).tzinfo is None:raise ValueError('Timestamp must include timezone')
        return v
class Constraints(Strict):
    maxAdditionalCostMinor:int|None=Field(None,ge=0,strict=True);maxDelayHours:int|None=Field(None,ge=0,strict=True);protectCustomerCommitments:bool=True;currency:Literal['USD']='USD'
class SimRequest(Strict):
    scenarioId:str;scenarioRevision:int;sourceDataVersion:str;selectedDecisionIds:list[str]=Field(min_length=1,max_length=30);overrides:list[Override]=Field(default_factory=list);constraints:Constraints=Field(default_factory=Constraints);priorityPolicy:Literal['protect_commitments','minimize_cost','minimize_delay']='protect_commitments'
class Approval(Strict):
    scenarioId:str;simulationId:str;selectedPlanId:str;scenarioRevision:int;sourceDataVersion:str;action:Literal['approve','reject'];note:str=Field(min_length=1,max_length=2000)
    @field_validator('note')
    @classmethod
    def nonblank(cls,v):
        if not v.strip():raise ValueError('Review note required')
        return v.strip()
class Execution(Strict):certificateId:str;idempotencyKey:str=Field(min_length=8,max_length=200)
class Mutation(Strict):scenarioId:str
class AgentInput(BaseModel):
    threadId:str;runId:str;messages:list[dict]=Field(default_factory=list);state:dict=Field(default_factory=dict);tools:list[dict]=Field(default_factory=list);context:list[dict]=Field(default_factory=list);forwardedProps:dict=Field(default_factory=dict)

@asynccontextmanager
async def lifespan(app):
    store.init();yield
app=FastAPI(title='ImpactIQ Demo API',version='1.0.0',lifespan=lifespan)
default_origins = '*' if os.getenv('VERCEL') else 'http://localhost:3000,http://127.0.0.1:3000'
app.add_middleware(CORSMiddleware,allow_origins=os.getenv('IMPACTIQ_ALLOWED_ORIGINS',default_origins).split(','),allow_methods=['GET','POST','OPTIONS'],allow_headers=['Content-Type','Accept'],allow_credentials=False)
@app.exception_handler(store.DomainError)
async def domain_error(req,exc):return JSONResponse(status_code=exc.status,content={'code':exc.code,'message':exc.message,'requestId':uid('REQ')})
@app.exception_handler(RequestValidationError)
async def validation_error(req,exc):return JSONResponse(status_code=422,content={'code':'INVALID_INPUT','message':'Invalid request: '+str(exc.errors()[0]['msg']),'requestId':uid('REQ')})

def read(table,id):
    with store.connect() as c:return store.one(c,table,id)
def validate(r):
    with store.connect() as c:s=store.current(c,r)
    ds={d['id']:d for d in s['decisions']};ids=r['selectedDecisionIds'];ov=r['overrides']
    if len(set(ids))!=len(ids) or any(i not in ds or ds[i]['status']!='pending' for i in ids):raise store.DomainError('INVALID_DECISIONS','Choose unique pending decisions in this scenario.',422)
    if len({x['decisionId'] for x in ov})!=len(ov) or any(x['decisionId'] not in ids for x in ov):raise store.DomainError('INVALID_OVERRIDE','Overrides must belong to selected decisions.',422)
    for o in ov:
        d=ds[o['decisionId']]
        if s['id']=='SCN-003' and any(o.get(k) is not None for k in ['quantity','sourceBranchId','requiredAt']):raise store.DomainError('UNSUPPORTED_OVERRIDE','Equipment intervals are fixed in this MVP.',422)
        if o.get('sourceBranchId') and (d['actionType']!='transfer' or o['sourceBranchId'] not in {x['branchId'] for x in s['resources'] if x['resourceType']=='part'} or o['sourceBranchId']==d.get('targetBranchId')):raise store.DomainError('INVALID_BRANCH','Unsupported source branch.',422)
        if o.get('requiredAt') and dt(o['requiredAt'])<dt(s['referenceTime']):raise store.DomainError('INVALID_DEADLINE','Deadline precedes scenario time.',422)
    return s

JOBS={'inventory':['get_inventory','get_pending_transfers'],'service':['get_work_orders','get_service_commitments'],'rental':['get_asset_availability','get_rental_reservations','get_rental_commitments']}
INTEGRATIONS={k:dict(id=k,name=k.title()+' MCP Server',description={'inventory':'Stock and transfer records','service':'Work orders and service commitments','rental':'Asset readiness and rental commitments'}[k],status='not_tested',mode='local_mcp_demo',tools=[],lastCheckedAt=None,lastLatencyMs=None) for k in JOBS}

def merge_sources(s,results):
    # Actual tool-returned records are the authoritative inputs for these departments.
    data={n:v for group in results for n,v in group[0]}
    for v in data.values():
        if v['sourceDataVersion']!=s['sourceDataVersion'] or v['revision']!=s['revision']:raise store.DomainError('STALE_SOURCE','Data changed during MCP retrieval. Analyze again.')
    s={**s,'resources':data['get_inventory']['records']+data['get_asset_availability']['records'],'decisions':data['get_pending_transfers']['records']+data['get_work_orders']['records']+data['get_rental_reservations']['records']+[d for d in s['decisions'] if d['department'] not in ('Inventory','Service','Rental')],'commitments':data['get_service_commitments']['records']+data['get_rental_commitments']['records']+[c for c in s['commitments'] if c['department'] not in ('Service','Rental')]}
    # Preserve source ordering so plans are reproducible when revalidated at execution.
    s['resources'].sort(key=lambda x:x['id']);s['decisions'].sort(key=lambda x:x['id']);s['commitments'].sort(key=lambda x:x['id'])
    return s

def record_status(k,result):
    INTEGRATIONS[k].update(status='connected',tools=result[1],lastCheckedAt=now(),lastLatencyMs=result[2])
async def gather_sources(s):
    out=await asyncio.gather(*(collect(k,n,s['id']) for k,n in JOBS.items()),return_exceptions=True)
    for k,v in zip(JOBS,out):
        if isinstance(v,BaseException):INTEGRATIONS[k].update(status='error',lastCheckedAt=now(),lastLatencyMs=None)
        else:record_status(k,v)
    if any(isinstance(v,BaseException) for v in out):raise store.DomainError('MCP_UNAVAILABLE','A required MCP connector failed; no safe result can be produced.',503)
    return out
@app.get('/api/v1/health')
def health():return {'status':'ok','version':'1.0.0','environment':'local_demo','mcpProtocol':'2025-06-18','llmConfigured':bool(os.getenv('OPENAI_API_KEY') or os.getenv('GEMINI_API_KEY'))}
@app.get('/api/v1/scenarios')
def get_scenarios():
    with store.connect() as c:return {'items':store.scenarios(c)}
@app.get('/api/v1/scenarios/{sid}')
def get_scenario(sid:str):return read('scenarios',sid)
@app.post('/api/v1/scenarios/{sid}/reset')
def reset(sid:str):return store.reset(sid)
@app.get('/api/v1/decisions')
def decisions():return {'items':[d for s in get_scenarios()['items'] for d in s['decisions']]}
@app.get('/api/v1/decisions/{did}')
def decision(did:str):
    for d in decisions()['items']:
        if d['id']==did:return d
    raise store.DomainError('NOT_FOUND','Decision not found.',404)
@app.get('/api/v1/history')
def history():
    with store.connect() as c:return {'items':[json.loads(x['body']) for x in c.execute('SELECT body FROM history ORDER BY created DESC')]}
@app.get('/api/v1/overview')
def overview():
    ss=get_scenarios()['items'];ds=decisions()['items'];results=[]
    for s in ss:
        ids=[d['id'] for d in s['decisions'] if d['status']=='pending']
        if ids:results.append(evaluate(s,{'selectedDecisionIds':ids,'overrides':[],'constraints':{'protectCustomerCommitments':True},'priorityPolicy':'protect_commitments'}))
    return {'metrics':{'pending':sum(d['status']=='pending' for d in ds),'conflicts':sum(x['impactSummary']['conflictCount'] for x in results),'commitments':sum(x['impactSummary']['commitmentsAtRisk'] for x in results),'exposure':sum(x['impactSummary']['revenueAtRiskMinor'] for x in results)},'decisions':ds,'recentActivity':history()['items'][:5],'note':'Independent fictional scenarios; totals are demonstration metrics.'}
@app.get('/api/v1/dependencies')
def dependencies(entityId:str,scenarioId:str='SCN-002'):
    s=read('scenarios',scenarioId);ids=[d['id'] for d in s['decisions'] if d['status']=='pending'];r=evaluate(s,{'selectedDecisionIds':ids,'overrides':[],'constraints':{'protectCustomerCommitments':True},'priorityPolicy':'protect_commitments'});return {'entityId':entityId,'graph':r['graph'],'evidence':r['evidence']}
@app.post('/api/v1/simulations')
async def simulate(body:SimRequest):
    r=body.model_dump(exclude_none=True);s=validate(r);s=merge_sources(s,await gather_sources(s));return store.save_sim(r,evaluate(s,r))
@app.get('/api/v1/simulations/{sid}')
def get_sim(sid:str):return read('simulations',sid)
@app.post('/api/v1/approvals')
def approve(body:Approval):return store.approval(body.model_dump())
@app.get('/api/v1/certificates/{cid}')
def certificate(cid:str):return read('certificates',cid)
@app.post('/api/v1/executions')
def execution(body:Execution):return store.execute(body.model_dump())
@app.post('/api/v1/demo/mutate-source')
def mutate(body:Mutation):return store.mutate(body.scenarioId)
@app.get('/api/v1/integrations')
def integrations():return {'items':list(INTEGRATIONS.values())+[{'id':'finance','name':'Sales / Finance adapter','description':'Read-only synthetic records from SQLite','status':'local','mode':'sqlite_demo','tools':[],'lastCheckedAt':None,'lastLatencyMs':None}]}
@app.post('/api/v1/integrations/{kind}/test')
async def test_connector(kind:str):
    if kind not in JOBS:raise store.DomainError('NOT_FOUND','MCP connector not found.',404)
    try:result=await collect(kind,JOBS[kind], 'SCN-002');record_status(kind,result);return INTEGRATIONS[kind]
    except Exception:INTEGRATIONS[kind].update(status='error',lastCheckedAt=now(),lastLatencyMs=None);raise store.DomainError('MCP_UNAVAILABLE','Connector test failed.',503)

async def explain(result,question):
    """Optional LLM for explanation only, never authorizing or calculating a plan."""
    import httpx
    fallback=f"{result['status'].title()} analysis: {result['impactSummary']['conflictCount']} resource conflict(s), {result['impactSummary']['commitmentsAtRisk']} commitment(s) at risk. Recommended plan: {result['recommendedPlanId'] or 'none'}. "+' '.join(x['explanation'] for x in result['resourceConflicts'])
    prompt='Explain this fictional simulation briefly using only provided results. Do not invent facts, change figures, or authorize actions. Question: '+question[:1000]+'\nResult: '+json.dumps({'summary':result['impactSummary'],'plans':result['alternatives'],'conflicts':result['resourceConflicts'],'commitments':result['affectedCommitments']})
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            if os.getenv('GEMINI_API_KEY'):
                model=os.getenv('GEMINI_MODEL','gemini-2.5-flash');resp=await client.post(f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',headers={'x-goog-api-key':os.environ['GEMINI_API_KEY']},json={'contents':[{'parts':[{'text':prompt}]}]});resp.raise_for_status();return resp.json()['candidates'][0]['content']['parts'][0]['text'],'Gemini'
            if os.getenv('OPENAI_API_KEY'):
                resp=await client.post('https://api.openai.com/v1/chat/completions',headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY']},json={'model':os.getenv('OPENAI_MODEL','gpt-4o-mini'),'messages':[{'role':'user','content':prompt}]});resp.raise_for_status();return resp.json()['choices'][0]['message']['content'],'OpenAI'
    except Exception:return fallback,'Deterministic fallback (LLM unavailable)'
    return fallback,'Deterministic explanation (no LLM key)'

@app.post('/api/v1/agent/run')
async def agent(body:AgentInput,request:Request):
    def event(t,**kwargs):return 'data: '+json.dumps({'type':t,**kwargs},separators=(',',':'))+'\n\n'
    async def stream():
        start=time.perf_counter();yield event('RUN_STARTED',threadId=body.threadId,runId=body.runId)
        try:
            if body.forwardedProps.get('operation')=='explain':
                result=read('simulations',body.forwardedProps['simulationId']);message_id=uid('MSG');text,provider=await explain(result,str(body.forwardedProps.get('question','Explain this result')))
                yield event('TEXT_MESSAGE_START',messageId=message_id,role='assistant');yield event('TEXT_MESSAGE_CONTENT',messageId=message_id,delta=f'[{provider}] {text}');yield event('TEXT_MESSAGE_END',messageId=message_id)
            else:
                r=SimRequest.model_validate(body.forwardedProps.get('simulationRequest')).model_dump(exclude_none=True);s=validate(r)
                yield event('STATE_SNAPSHOT',snapshot={'status':'analyzing','simulation':None,'activity':[]})
                ids={k:uid('TOOL') for k in JOBS}
                for k in JOBS:
                    yield event('TOOL_CALL_START',toolCallId=ids[k],toolCallName='retrieve_'+k);yield event('TOOL_CALL_ARGS',toolCallId=ids[k],delta=json.dumps({'scenarioId':s['id']}));yield event('TOOL_CALL_END',toolCallId=ids[k])
                results=await gather_sources(s)
                for k,v in zip(JOBS,results):
                    yield event('TOOL_CALL_RESULT',messageId=uid('MSG'),toolCallId=ids[k],content=json.dumps({'connector':k,'toolCalls':[n for n,_ in v[0]],'latencyMs':v[2],'records':sum(len(x['records']) for _,x in v[0])}),role='tool')
                if await request.is_disconnected():return
                yield event('STEP_STARTED',stepName='Evaluate business constraints')
                result=store.save_sim(r,evaluate(merge_sources(s,results),r))
                yield event('STEP_FINISHED',stepName='Evaluate business constraints')
                yield event('STATE_DELTA',delta=[{'op':'replace','path':'/status','value':'analyzed'},{'op':'replace','path':'/simulation','value':result}])
                yield event('CUSTOM',name='impactiq.metrics',value={'elapsedMs':round((time.perf_counter()-start)*1000,1),'simulationId':result['id']})
            yield event('RUN_FINISHED',threadId=body.threadId,runId=body.runId)
        except asyncio.CancelledError:raise
        except Exception as exc:yield event('RUN_ERROR',message=exc.message if isinstance(exc,store.DomainError) else 'Agent run failed: '+str(exc)[:300],code=exc.code if isinstance(exc,store.DomainError) else 'RUN_FAILED')
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache, no-transform','X-Accel-Buffering':'no'})
