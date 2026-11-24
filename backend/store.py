"""Persistent SQLite sandbox, with transaction-scoped version checks."""
import json, os, sqlite3
from contextlib import contextmanager
from pathlib import Path
from .engine import now, uid

ROOT=Path(__file__).resolve().parent
DB_PATH=Path(os.environ.get('IMPACTIQ_DB',str(ROOT/'data'/'impactiq.sqlite3'))).resolve()
SEEDS=json.loads((ROOT/'fixtures.json').read_text(encoding='utf-8'))
class DomainError(Exception):
    def __init__(self,code,message,status=409): self.code=code;self.message=message;self.status=status;super().__init__(message)

def dumps(x):return json.dumps(x,ensure_ascii=False,separators=(',',':'))
@contextmanager
def connect(write=False):
    DB_PATH.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(DB_PATH,timeout=5);c.row_factory=sqlite3.Row
    try:
        if write:c.execute('BEGIN IMMEDIATE')
        yield c
        if write:c.commit()
    except BaseException:
        c.rollback();raise
    finally:c.close()

def init():
    with connect() as c:
        c.execute('PRAGMA journal_mode=WAL');c.executescript('''CREATE TABLE IF NOT EXISTS scenarios(id TEXT PRIMARY KEY, body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS simulations(id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL, body TEXT NOT NULL, request TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS certificates(id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL, body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS history(id TEXT PRIMARY KEY, body TEXT NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS executions(key TEXT PRIMARY KEY, certificate_id TEXT NOT NULL, body TEXT NOT NULL);''');c.commit()
    with connect(True) as c:
        for s in SEEDS:c.execute('INSERT OR IGNORE INTO scenarios VALUES (?,?)',(s['id'],dumps(s)))

def one(c,table,id):
    row=c.execute(f'SELECT body FROM {table} WHERE id=?',(id,)).fetchone()
    if not row:raise DomainError('NOT_FOUND',f'{table} record {id} not found',404)
    return json.loads(row['body'])
def scenarios(c):return [json.loads(x['body']) for x in c.execute('SELECT body FROM scenarios ORDER BY id')]
def put(c,table,obj):c.execute(f'UPDATE {table} SET body=? WHERE id=?',(dumps(obj),obj['id']))
def audit(c,event,scenario,description,simulation=None,certificate=None,metadata=None):
    a=dict(id=uid('AUD'),eventType=event,scenarioId=scenario,user='Alex Morgan (demo)',timestamp=now(),description=description,metadata=metadata or {})
    if simulation:a['simulationId']=simulation
    if certificate:a['certificateId']=certificate
    c.execute('INSERT INTO history VALUES (?,?,?)',(a['id'],dumps(a),a['timestamp']));return a

def current(c,r):
    s=one(c,'scenarios',r['scenarioId'])
    if r['sourceDataVersion']!=s['sourceDataVersion'] or r['scenarioRevision']!=s['revision']:raise DomainError('STALE_SOURCE','Source data changed. Refresh scenario and simulate again.')
    return s

def advance(c,s,reason,exclude=None):
    s['revision']+=1;s['sourceDataVersion']=f"ERP-{s['id']}-R{s['revision']}-{uid('V')}";put(c,'scenarios',s)
    for row in c.execute('SELECT body FROM certificates WHERE scenario_id=?',(s['id'],)).fetchall():
        cert=json.loads(row['body'])
        if cert['id']==exclude or cert['executionStatus']=='executed' or cert['stale']:continue
        cert['stale']=True;cert['executionStatus']='blocked';put(c,'certificates',cert);audit(c,'certificate_stale',s['id'],reason,cert['simulationId'],cert['id'])
    return s

def reset(sid):
    with connect(True) as c:
        old=one(c,'scenarios',sid);s=json.loads(dumps(next(v for v in SEEDS if v['id']==sid)));s['revision']=old['revision'];advance(c,s,'Scenario reset');audit(c,'scenario_reset',sid,'Fictional source scenario restored.');return s

def mutate(sid):
    with connect(True) as c:
        s=one(c,'scenarios',sid);x=s['resources'][0]
        if x['resourceType']=='part':x['availableQuantity']=max(x['committedQuantity'],x['availableQuantity']-1)
        else:
            # Reserve the spare asset so the former replacement plan is no longer feasible.
            x=next(v for v in s['resources'] if v['id']=='EQ-102');x['committedQuantity']=1
        x['version']=uid('SRC');advance(c,s,'Source stock or availability changed.');audit(c,'source_changed',sid,f"Updated fictional resource {x['id']}.");return s

def save_sim(r,result):
    with connect(True) as c:
        current(c,r);c.execute('INSERT INTO simulations VALUES (?,?,?,?)',(result['id'],r['scenarioId'],dumps(result),dumps(r)));audit(c,'simulation_completed',r['scenarioId'],'Deterministic simulation completed.',result['id'],metadata={'exposureMinor':result['impactSummary']['revenueAtRiskMinor'],'conflictCount':result['impactSummary']['conflictCount'],'sourceDataVersion':result['sourceDataVersion']});return result

def approval(body):
    with connect(True) as c:
        current(c,body);sim=one(c,'simulations',body['simulationId'])
        if any(sim[k]!=body[k] for k in ('scenarioId','scenarioRevision','sourceDataVersion')):raise DomainError('SIMULATION_MISMATCH','Simulation does not match current source revision.')
        plan=next((p for p in sim['alternatives'] if p['id']==body['selectedPlanId']),None)
        if not plan:raise DomainError('PLAN_NOT_FOUND','Plan does not belong to simulation.',404)
        if body['action']=='approve' and (not plan['feasible'] or sim['completeness']!='complete'):raise DomainError('UNSAFE_PLAN','Only complete, feasible plans may be approved.')
        # Supersede older active certificates for the scenario.
        for row in c.execute('SELECT body FROM certificates WHERE scenario_id=?',(body['scenarioId'],)).fetchall():
            old=json.loads(row['body'])
            if not old['stale'] and old['executionStatus']=='not_executed':
                old['stale']=True;old['executionStatus']='blocked';put(c,'certificates',old);audit(c,'certificate_stale',body['scenarioId'],'Superseded by a new review.',old['simulationId'],old['id'])
        cert=dict(id=uid('CERT'),scenarioId=body['scenarioId'],simulationId=sim['id'],selectedPlanId=plan['id'],scenarioRevision=sim['scenarioRevision'],sourceDataVersion=sim['sourceDataVersion'],approver='Alex Morgan (demo)',approvalNote=body['note'],approvedAt=now(),approvalStatus='approved' if body['action']=='approve' else 'rejected',executionStatus='not_executed',stale=False,planTitle=plan['title'],risks=plan['constraintsViolated'],protectedCommitmentIds=plan['protectedCommitmentIds'],exposureBeforeMinor=sim['impactSummary']['revenueAtRiskMinor'],exposureAfterMinor=plan['impactSummary']['revenueAtRiskMinor'])
        c.execute('INSERT INTO certificates VALUES (?,?,?)',(cert['id'],cert['scenarioId'],dumps(cert)));audit(c,'approved' if body['action']=='approve' else 'rejected',cert['scenarioId'],f"{plan['title']} reviewed.",sim['id'],cert['id'],{'exposureBeforeMinor':cert['exposureBeforeMinor'],'exposureAfterMinor':cert['exposureAfterMinor'],'sourceDataVersion':cert['sourceDataVersion']});return cert

def execute(body):
    from .engine import evaluate
    with connect(True) as c:
        duplicate=c.execute('SELECT certificate_id,body FROM executions WHERE key=?',(body['idempotencyKey'],)).fetchone()
        if duplicate:
            if duplicate['certificate_id']!=body['certificateId']:raise DomainError('IDEMPOTENCY_CONFLICT','Execution key already belongs to another certificate.')
            return json.loads(duplicate['body'])
        cert=one(c,'certificates',body['certificateId'])
        if cert['executionStatus']=='executed':raise DomainError('ALREADY_EXECUTED','This certificate has already been executed.')
        if cert['stale'] or cert['approvalStatus']!='approved':raise DomainError('APPROVAL_REQUIRED','Current approved certificate required.')
        s=current(c,cert);row=c.execute('SELECT request FROM simulations WHERE id=?',(cert['simulationId'],)).fetchone();r=json.loads(row['request']);new=evaluate(s,r);p=next((p for p in new['alternatives'] if p['id']==cert['selectedPlanId']),None)
        if not p or not p['feasible']:raise DomainError('UNSAFE_PLAN','Plan no longer feasible.')
        # Verify the approved allocation is identical to the recomputed plan.
        old=one(c,'simulations',cert['simulationId']);old_plan=next(x for x in old['alternatives'] if x['id']==p['id'])
        if p['allocations']!=old_plan['allocations']:raise DomainError('STALE_PLAN','Recomputed allocations differ from approval.')
        decisions={d['id']:d for d in s['decisions']}
        for a in p['allocations']:
            d=decisions[a['decisionId']];res=next(x for x in s['resources'] if x['id']==a['resourceId'] and x['branchId']==a['sourceBranchId'])
            if d['status']!='pending':raise DomainError('ALREADY_COMMITTED','Decision has already been committed.')
            q=a['quantity']
            if res['resourceType']=='part':
                if d['actionType']=='transfer':
                    res['availableQuantity']-=q
                    target=next((x for x in s['resources'] if x['branchId']==d['targetBranchId'] and x['resourceType']=='part'),None)
                    if not target:
                        target={**res,'id':f"PART-HP220-{d['targetBranchId']}",'branchId':d['targetBranchId'],'availableQuantity':0,'committedQuantity':0};s['resources'].append(target)
                    target['availableQuantity']+=q;target['version']=uid('SRC')
                else:res['committedQuantity']+=q
            else:
                # Equipment decisions are future schedule commitments, not completed physical actions.
                res['attributes'].setdefault('scheduledActions','')
                res['attributes']['scheduledActions']+=f"{d['actionType']}:{a['startAt']}–{a['endAt']};"
                if d['actionType'] in ('sale_hold','rental'):res['committedQuantity']=1
            res['version']=uid('SRC')
        for d in s['decisions']:
            if d['id'] in r['selectedDecisionIds']:d['status']='executed'
        cert['executionStatus']='executed';cert['executedAt']=now();put(c,'certificates',cert);advance(c,s,'Another approved decision changed source data.',exclude=cert['id']);audit(c,'executed',s['id'],'Approved allocations committed atomically to fictional SQLite sandbox.',cert['simulationId'],cert['id'],{'sourceDataVersion':s['sourceDataVersion'],'exposureBeforeMinor':cert['exposureBeforeMinor'],'exposureAfterMinor':cert['exposureAfterMinor']});result={'certificate':cert,'scenario':s};c.execute('INSERT INTO executions VALUES (?,?,?)',(body['idempotencyKey'],cert['id'],dumps(result)));return result
