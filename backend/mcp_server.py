"""Minimal MCP 2025-06-18 stdio server, restricted to read-only demo tools.
Run independently: python -m backend.mcp_server inventory|service|rental
Messages are newline-delimited JSON-RPC 2.0 (stdout reserved for protocol).
"""
import sys,json
try:
    from . import store
except (ImportError, ValueError):
    import store
PROTOCOL='2025-06-18'
TOOLS={
 'inventory':{'get_inventory':'Read all part records','get_pending_transfers':'Read pending inventory decisions','find_alternative_stock':'Find free stock at each branch','validate_stock_allocation':'Read inventory availability constraints'},
 'service':{'get_work_orders':'Read service decisions','get_service_commitments':'Read service customer commitments','get_required_parts':'Read service demand'},
 'rental':{'get_rental_reservations':'Read rental decisions','get_asset_availability':'Read equipment records','get_rental_commitments':'Read rental commitments'} }

def call(kind,name,sid):
    if name not in TOOLS[kind]:raise ValueError('Unknown tool')
    with store.connect() as c:s=store.one(c,'scenarios',sid)
    dep={'inventory':'Inventory','service':'Service','rental':'Rental'}[kind]
    if name in ('get_inventory','find_alternative_stock','validate_stock_allocation'): records=[x for x in s['resources'] if x['resourceType']=='part']
    elif name=='get_asset_availability':records=[x for x in s['resources'] if x['resourceType']=='equipment']
    elif name.endswith('commitments'):records=[x for x in s['commitments'] if x['department']==dep]
    else:records=[x for x in s['decisions'] if x['department']==dep]
    return dict(scenarioId=sid,sourceDataVersion=s['sourceDataVersion'],revision=s['revision'],records=records)

def serve(kind):
    initialized=False;negotiated=False
    for line in sys.stdin:
        try:
            req=json.loads(line);method=req.get('method');params=req.get('params') or {};rid=req.get('id')
            if method=='notifications/initialized':initialized=negotiated;continue
            if 'id' not in req:continue
            if method=='initialize':
                negotiated=True;out={'protocolVersion':PROTOCOL,'capabilities':{'tools':{'listChanged':False}},'serverInfo':{'name':f'impactiq-{kind}','version':'1.0.0'}}
            elif method=='ping':out={}
            elif not initialized:raise ValueError('MCP initialization required')
            elif method=='tools/list':out={'tools':[{'name':n,'description':d,'inputSchema':{'type':'object','properties':{'scenarioId':{'type':'string'}},'required':['scenarioId'],'additionalProperties':False},'annotations':{'readOnlyHint':True}} for n,d in TOOLS[kind].items()]}
            elif method=='tools/call':
                try:
                    args=params['arguments'];assert set(args)=={'scenarioId'}
                    value=call(kind,params['name'],args['scenarioId']);out={'content':[{'type':'text','text':json.dumps(value)}],'isError':False}
                except Exception as exc:out={'content':[{'type':'text','text':str(exc)}],'isError':True}
            else:raise ValueError('Unsupported MCP method')
            reply={'jsonrpc':'2.0','id':rid,'result':out}
        except Exception as exc:reply={'jsonrpc':'2.0','id':locals().get('rid'),'error':{'code':-32602,'message':str(exc)}}
        print(json.dumps(reply),flush=True)
if __name__=='__main__':
    if len(sys.argv)!=2 or sys.argv[1] not in TOOLS:sys.exit('Expected inventory, service or rental')
    serve(sys.argv[1])
