import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from backend import store, main

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store,'DB_PATH',tmp_path/'test.sqlite3')
    with TestClient(main.app) as c: yield c

def payload(c,sid='SCN-002',**kw):
    s=c.get('/api/v1/scenarios/'+sid).json()
    return dict(scenarioId=sid,scenarioRevision=s['revision'],sourceDataVersion=s['sourceDataVersion'],selectedDecisionIds=[d['id'] for d in s['decisions'] if d['status']=='pending'],overrides=[],constraints={'protectCustomerCommitments':True,'currency':'USD'},priorityPolicy='protect_commitments')|kw

def sim(c,sid='SCN-002',**kw):
    r=c.post('/api/v1/simulations',json=payload(c,sid,**kw));assert r.status_code==200,r.text;return r.json()

def approve(c,s,plan=None,action='approve'):
    return c.post('/api/v1/approvals',json={k:s[k] for k in ['scenarioId','scenarioRevision','sourceDataVersion']}|{'simulationId':s['id'],'selectedPlanId':plan or s['recommendedPlanId'],'action':action,'note':'Verified in regression test'})

def execute(c,cert,key='test-key-123'):
    return c.post('/api/v1/executions',json={'certificateId':cert['id'],'idempotencyKey':key})

@pytest.mark.parametrize('sid,plan,deficit',[('SCN-001','PLAN-WEST',2),('SCN-002','PLAN-WEST',1),('SCN-003','PLAN-REPLACE',1)])
def test_scenarios(client,sid,plan,deficit):
    s=sim(client,sid);assert s['recommendedPlanId']==plan;assert s['resourceConflicts'][0]['deficitQuantity']==deficit
    assert sum(x['revenueAtRiskMinor'] for x in s['affectedCommitments'])==s['impactSummary']['revenueAtRiskMinor']
    cert=approve(client,s);assert cert.status_code==200,cert.text
    r=execute(client,cert.json());assert r.status_code==200,r.text
    assert all(x['status']=='executed' for x in r.json()['scenario']['decisions'])

def test_combined_individual(client):
    s=sim(client);assert all(x['feasible'] for x in s['individualEvaluations']);assert s['resourceConflicts'][0]['requiredQuantity']==11
    assert approve(client,s,'PLAN-BASE').status_code==409

def test_stale(client):
    s=sim(client);cert=approve(client,s).json();assert client.post('/api/v1/demo/mutate-source',json={'scenarioId':'SCN-002'}).status_code==200
    assert client.get('/api/v1/certificates/'+cert['id']).json()['stale'];assert execute(client,cert).status_code==409;assert approve(client,s).status_code==409
    fresh=sim(client);assert execute(client,approve(client,fresh).json()).status_code==200

def test_idempotency_concurrency(client):
    cert=approve(client,sim(client)).json()
    with ThreadPoolExecutor(2) as pool: responses=list(pool.map(lambda k:execute(client,cert,k),['unique-key-1','unique-key-2']))
    assert sorted(x.status_code for x in responses)==[200,409]
    winner=next(i for i,x in enumerate(responses) if x.status_code==200)
    assert execute(client,cert,['unique-key-1','unique-key-2'][winner]).json()==responses[winner].json()
    assert sum(x['eventType']=='executed' for x in client.get('/api/v1/history').json()['items'])==1

def test_rejected(client):
    cert=approve(client,sim(client),action='reject').json();assert execute(client,cert).status_code==409

def test_invalid(client):
    for change in [{'selectedDecisionIds':['D-101','D-101']},{'overrides':[{'decisionId':'D-101','quantity':-1}]},{'overrides':[{'decisionId':'D-101','sourceBranchId':'BR-CENTRAL'}]}]:
        assert client.post('/api/v1/simulations',json=payload(client,**change)).status_code==422

def test_cost_limit(client):
    s=sim(client,constraints={'maxAdditionalCostMinor':0,'protectCustomerCommitments':True});assert s['recommendedPlanId'] is None

def test_stream(client):
    r=client.post('/api/v1/agent/run',json={'threadId':'t','runId':'r','forwardedProps':{'simulationRequest':payload(client)}})
    events=[json.loads(x[6:]) for x in r.text.splitlines() if x.startswith('data: ')]
    assert events[0]['type']=='RUN_STARTED';assert events[-1]['type']=='RUN_FINISHED';assert sum(x['type']=='TOOL_CALL_RESULT' for x in events)==3
    result=next(x['delta'][1]['value'] for x in events if x['type']=='STATE_DELTA');assert result['recommendedPlanId']=='PLAN-WEST'
    assert client.get('/api/v1/simulations/'+result['id']).status_code==200

def test_mcp_failure(client,monkeypatch):
    async def fail(*args):raise RuntimeError('test outage')
    monkeypatch.setattr(main,'collect',fail)
    assert client.post('/api/v1/simulations',json=payload(client)).status_code==503
    r=client.post('/api/v1/agent/run',json={'threadId':'t','runId':'r','forwardedProps':{'simulationRequest':payload(client)}})
    assert 'RUN_ERROR' in r.text and 'RUN_FINISHED' not in r.text

def test_read_endpoints(client):
    for path in ['health','overview','scenarios','decisions','decisions/D-101','history','integrations','dependencies?entityId=PART-HP220&scenarioId=SCN-002']:
        assert client.get('/api/v1/'+path).status_code==200
    for kind in ['inventory','service','rental']:
        r=client.post('/api/v1/integrations/'+kind+'/test');assert r.status_code==200;assert r.json()['tools']

def test_reset(client):
    s=sim(client);cert=approve(client,s).json();assert client.post('/api/v1/scenarios/SCN-002/reset').status_code==200;assert execute(client,cert).status_code==409
