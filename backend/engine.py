"""Deterministic, fictional dealership decision validation. No LLM calculations."""
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from uuid import uuid4

def now(): return datetime.now(timezone.utc).isoformat()
def dt(s): return datetime.fromisoformat(s.replace('Z','+00:00'))
def uid(prefix): return f'{prefix}-{uuid4().hex[:12]}'
PRIORITY={'critical':0,'high':1,'normal':2}

def evaluate(s,r):
    decisions={d['id']:d for d in s['decisions']}
    overrides={o['decisionId']:o for o in r['overrides']}
    selected=[{**decisions[i],**{k:v for k,v in overrides.get(i,{}).items() if k!='decisionId' and v is not None}} for i in r['selectedDecisionIds']]
    resources=s['resources']; equipment=s['id']=='SCN-003'; commitments=s['commitments']; constraints=r['constraints']
    def stock(branch): return next((x for x in resources if x['branchId']==branch and x['resourceType']=='part'),None)
    def free(x): return max(0,x.get('availableQuantity',0)-x['committedQuantity']) if x else 0
    def part_plan(actions):
        # Actions reserve physical units at a specific source, including split transfers.
        remaining={x['branchId']:free(x) for x in resources if x['resourceType']=='part'}
        fulfilled=defaultdict(int); demand=defaultdict(int); short_by=defaultdict(int); cost=0; late=set(); late_hours=0
        for a in sorted(actions,key=lambda a:(PRIORITY[a.get('priority',decisions[a['decisionId']]['priority'])],dt(a['requiredAt']),a['decisionId'],a['sourceBranchId'])):
            b=a['sourceBranchId']; q=a['quantity']; demand[b]+=q
            avail=remaining.get(b,0); alloc=min(avail,q); remaining[b]=avail-alloc; fulfilled[a['decisionId']]+=alloc; short_by[b]+=q-alloc
            if b!=decisions[a['decisionId']]['sourceBranchId']:
                cost+=q*24000
                arrival=dt(s['referenceTime'])+timedelta(hours=8)
                if arrival>dt(a['requiredAt']): late.add(a['decisionId']);late_hours=max(late_hours,(arrival-dt(a['requiredAt'])).total_seconds()/3600)
        conflicts=[]
        for b,q in demand.items():
            if short_by[b]:
                res=stock(b); conflicts.append(dict(id=f'RC-{b}',resourceId=res['id'] if res else 'UNKNOWN',resourceName=res['name'] if res else 'Unknown resource',branchId=b,availableQuantity=free(res),requiredQuantity=q,deficitQuantity=short_by[b],relatedDecisionIds=list(dict.fromkeys(a['decisionId'] for a in actions if a['sourceBranchId']==b)),severity='critical',explanation=f'{q} requested against {free(res)} unallocated units at {b}; {short_by[b]} short.'))
        impacts=[]; budget=fulfilled.copy()
        for c in sorted(commitments,key=lambda c:(dt(c['dueAt']),c['id'])):
            ids=[i for i in c['relatedDecisionIds'] if i in r['selectedDecisionIds']]; affected=False; unknown=not ids and s['id']!='SCN-001'
            if s['id']=='SCN-001':
                # Existing repairs are already reserved. A shortage means requested transfer cannot be fully fulfilled; never steal reservations.
                affected=False; unknown=False
            elif ids:
                i=ids[0]; q=c['requiredQuantity']; affected=budget[i]<q or i in late; budget[i]=max(0,budget[i]-q)
            status='unknown' if unknown else 'at risk' if affected else 'protected'
            impacts.append(dict(commitmentId=c['id'],baselineStatus=c['currentStatus'],simulatedStatus=status,estimatedDelayHours=None if unknown else 24 if affected else 0,revenueAtRiskMinor=c['revenueAtRiskMinor'] if affected else 0,reason='Insufficient allocated units or late supply.' if affected else 'Not included in this simulation.' if unknown else 'Required units protected.',evidenceIds=[f'EV-{c["id"]}']))
        # A deferred transfer can create an unfulfilled customer promise even with no stock conflict.
        return conflicts,impacts,cost,max(late_hours,24 if any(x['simulatedStatus']=='at risk' for x in impacts) else 0),list(late)
    def asset_plan(actions):
        assigned=defaultdict(list); invalid=set(); conflicts=[];cost=0
        for a in actions:
            d=decisions[a['decisionId']]; x=next((v for v in resources if v['id']==a['resourceId']),None)
            if not x or x.get('availableQuantity',0)<1 or x['committedQuantity'] or (a['resourceId']!='EQ-101' and (not x['attributes'].get('ready') or not x['attributes'].get('compatible'))): invalid.add(d['id'])
            if a['resourceId']!='EQ-101':
                cost+=87000
                if x and dt(s['referenceTime'])+timedelta(hours=x['attributes'].get('transferHours',0))>dt(a['requiredAt']): invalid.add(d['id'])
            for prev in assigned[a['resourceId']]:
                if dt(a['startAt'])<dt(prev['endAt']) and dt(prev['startAt'])<dt(a['endAt']): invalid.update([d['id'],prev['decisionId']])
            assigned[a['resourceId']].append(a)
            if d['actionType']!='maintenance' and a['resourceId']=='EQ-101' and not resources[0]['attributes']['ready']:
                repair=next((z for z in actions if decisions[z['decisionId']]['actionType']=='maintenance' and z['resourceId']=='EQ-101' and dt(z['endAt'])<=dt(a['startAt'])),None)
                if not repair: invalid.add(d['id'])
        if invalid: conflicts.append(dict(id='RC-EQ',resourceId='EQ-101',resourceName='Excavator 320 GC',branchId='BR-CENTRAL',availableQuantity=1,requiredQuantity=len(actions),deficitQuantity=1,relatedDecisionIds=sorted(invalid),severity='critical',explanation='Asset allocation overlaps or equipment readiness constraints are not satisfied.'))
        impacts=[]
        for c in commitments:
            relevant=set(c['relatedDecisionIds']) & set(r['selectedDecisionIds']);risk=bool(relevant & invalid)
            impacts.append(dict(commitmentId=c['id'],baselineStatus=c['currentStatus'],simulatedStatus='at risk' if risk else 'protected' if relevant else 'unknown',estimatedDelayHours=24 if risk else 0 if relevant else None,revenueAtRiskMinor=c['revenueAtRiskMinor'] if risk else 0,reason='Asset unavailable by commitment deadline.' if risk else 'Compatible asset available.' if relevant else 'Not included in simulation.',evidenceIds=[f'EV-{c["id"]}']))
        return conflicts,impacts,cost,24 if invalid else 0,[]
    base=[]
    for d in selected:
        a=dict(decisionId=d['id'],resourceId=d['resourceId'],sourceBranchId=d['sourceBranchId'],quantity=d.get('quantity',1),requiredAt=d['requiredAt'],priority=d['priority'])
        if not equipment and stock(d['sourceBranchId']):a['resourceId']=stock(d['sourceBranchId'])['id']
        if equipment:a.update(startAt=d['startAt'],endAt=d['endAt'])
        base.append(a)
    evalplan=asset_plan if equipment else part_plan
    plans=[]; computed={}
    def make(pid,title,actions,description):
        cs,imp,cost,delay,late=evalplan(actions)
        risk=[x for x in imp if x['simulatedStatus']=='at risk'];protected=[x['commitmentId'] for x in imp if x['simulatedStatus']=='protected']
        violations=[]
        if cs:violations.append('Resource availability/readiness constraint')
        if late:violations.append('Source delivery deadline')
        if risk and constraints.get('protectCustomerCommitments',True):violations.append('Customer commitment protection')
        if constraints.get('maxAdditionalCostMinor') is not None and cost>constraints['maxAdditionalCostMinor']:violations.append('Additional cost limit')
        if constraints.get('maxDelayHours') is not None and delay>constraints['maxDelayHours']:violations.append('Delay limit')
        if s['id']=='SCN-001' and pid=='PLAN-REDUCE':violations.append('Original transfer requirement not fully satisfied')
        summary=dict(riskLevel='critical' if cs else 'high' if violations or risk else 'low',affectedDepartments=sorted(set(d['department'] for d in selected)|{c['department'] for c in commitments if c['id'] in {i['commitmentId'] for i in risk}}),commitmentsAtRisk=len(risk),protectedCommitments=len(protected),revenueAtRiskMinor=sum(x['revenueAtRiskMinor'] for x in risk),additionalCostMinor=cost,estimatedDelayHours=delay,conflictCount=len(cs),currency='USD')
        p=dict(id=pid,title=title,description=description,feasible=not violations,actions=[f"{a['decisionId']}: {a['quantity']} × {a['resourceId']} from {a['sourceBranchId']}" for a in actions],impactSummary=summary,constraintsViolated=violations,recommendationReason='All modeled constraints satisfied.' if not violations else '; '.join(violations),protectedCommitmentIds=protected,allocations=actions)
        plans.append(p);computed[pid]=(cs,imp);return p
    original=make('PLAN-BASE','Original plan',base,'Execute proposed allocations without changes.')
    conflicts,impacts=computed['PLAN-BASE']
    if not equipment and conflicts:
        transfer=next((a for a in base if decisions[a['decisionId']]['actionType']=='transfer' and a['sourceBranchId']=='BR-NORTH'),None)
        if transfer:
            gap=sum(c['deficitQuantity'] for c in conflicts if c['branchId']=='BR-NORTH'); shift=min(gap,transfer['quantity'])
            if shift:
                reduced=[{**a,'quantity':a['quantity']-shift} if a is transfer else a.copy() for a in base]
                make('PLAN-REDUCE','Reduce or defer transfer',reduced,'Lower transfer demand; may miss the original customer commitment.')
                if stock('BR-WEST'):
                    split=reduced+[{**transfer,'sourceBranchId':'BR-WEST','resourceId':stock('BR-WEST')['id'],'quantity':shift}]
                    make('PLAN-WEST','Source missing units from West',split,'Preserve the original demand using a second branch.')
    if equipment and conflicts and any(decisions[a['decisionId']]['actionType']=='rental' for a in base):
        replacement=next((v for v in resources if v['id']=='EQ-102'),None)
        if replacement:make('PLAN-REPLACE','Use EQ-102 for rental',[{**a,'resourceId':'EQ-102','sourceBranchId':replacement['branchId']} if decisions[a['decisionId']]['actionType']=='rental' else a.copy() for a in base],'Keep the maintenance and sale schedule; allocate a compatible replacement.')
    feasible=[p for p in plans if p['feasible']]
    policy=r['priorityPolicy']; key=lambda p:(p['impactSummary']['revenueAtRiskMinor'],p['impactSummary']['additionalCostMinor'],p['impactSummary']['estimatedDelayHours'])
    if policy=='minimize_cost':key=lambda p:(p['impactSummary']['additionalCostMinor'],p['impactSummary']['revenueAtRiskMinor'],p['impactSummary']['estimatedDelayHours'])
    if policy=='minimize_delay':key=lambda p:(p['impactSummary']['estimatedDelayHours'],p['impactSummary']['revenueAtRiskMinor'],p['impactSummary']['additionalCostMinor'])
    recommended=min(feasible,key=key)['id'] if feasible else None
    evidence=[]
    def ev(id,source,record,kind,fields):evidence.append(dict(id=id,sourceSystem=source,recordId=record,recordType=kind,retrievedAt=now(),sourceDataVersion=s['sourceDataVersion'],relevantFields=fields,retrievalStatus='simulated'))
    for x in resources:ev('EV-'+x['id'],'Inventory MCP' if x['resourceType']=='part' else 'Rental MCP',x['id'],'Resource snapshot',{'physicalStock':x.get('availableQuantity',0),'reserved':x['committedQuantity'],'version':x['version']})
    for c in commitments:ev('EV-'+c['id'],c['department']+' data',c['id'],'Customer commitment',{'requiredQuantity':c['requiredQuantity'],'dueAt':c['dueAt'],'revenueAtRiskMinor':c['revenueAtRiskMinor']})
    for d in selected:ev('EV-'+d['id'],d['department']+' data',d['id'],'Pending decision',{'quantity':d.get('quantity',1),'requiredAt':d['requiredAt']})
    nodes=[];edges=[]
    def node(i,label,cat,dep,severity,description,evs):nodes.append(dict(id=i,entityId=i,label=label,category=cat,department=dep,severity=severity,description=description,evidenceIds=evs))
    def edge(a,b,rel,severity,evs):edges.append(dict(id=f'E-{len(edges)}',source=a,target=b,relationship=rel,severity=severity,evidenceIds=evs))
    for d in selected:
        node(d['id'],d['title'],'Decision',d['department'],'low',d['description'],['EV-'+d['id']])
    for x in resources:
        severity='critical' if any(c['resourceId']==x['id'] for c in conflicts) else 'low'
        node(x['id'],x['name'],'Resource','Inventory' if x['resourceType']=='part' else 'Rental',severity,x['branchId']+' · '+str(free(x))+' unallocated',['EV-'+x['id']])
    for a in base:
        rid=a['resourceId'] if equipment else (stock(a['sourceBranchId']) or {}).get('id',a['resourceId'])
        if any(n['id']==rid for n in nodes):edge(a['decisionId'],rid,'requires','high' if conflicts else 'low',['EV-'+a['decisionId'],'EV-'+rid])
    for c in commitments:
        i=next(x for x in impacts if x['commitmentId']==c['id'])
        sev='high' if i['simulatedStatus']=='at risk' else 'unknown' if i['simulatedStatus']=='unknown' else 'low';op='OP-'+c['id'];dep=c['department'];node(op,c['commitmentType'],'Operation',dep,sev,i['reason'],i['evidenceIds']);node(c['id'],c['customerName'],'Customer commitment','Customer',sev,i['reason'],i['evidenceIds']);
        for rid in c['resourceIds']:
            if any(n['id']==rid for n in nodes):edge(rid,op,'supports',sev,i['evidenceIds'])
        edge(op,c['id'],'fulfills',sev,i['evidenceIds'])
        if sev=='high':
            fin='FIN-'+c['id'];node(fin,f"${i['revenueAtRiskMinor']/100:,.0f} at risk",'Financial impact','Finance',sev,'Estimated exposure, not loss.',i['evidenceIds']);edge(c['id'],fin,'exposes',sev,i['evidenceIds'])
    individual=[]
    for a in base:
        if equipment:ok=not evalplan([a])[0];available=1
        else:available=free(stock(a['sourceBranchId']));ok=a['quantity']<=available
        individual.append(dict(decisionId=a['decisionId'],feasible=ok,available=available,required=a['quantity']))
    return dict(id=uid('SIM'),scenarioId=s['id'],scenarioRevision=s['revision'],sourceDataVersion=s['sourceDataVersion'],generatedAt=now(),completeness='complete',status='critical' if conflicts else 'warning' if not original['feasible'] else 'safe',individualEvaluations=individual,resourceConflicts=conflicts,impactSummary=original['impactSummary'],graph=dict(nodes=nodes,edges=edges),affectedCommitments=impacts,evidence=evidence,alternatives=plans,recommendedPlanId=recommended,warnings=['Synthetic records and estimated exposure; not actual losses.'])
