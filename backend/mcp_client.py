"""Actual subprocess MCP negotiation, discovery and tool calls; no direct-call substitute."""
import asyncio,json,sys,os,time
from pathlib import Path
from . import store
from .mcp_server import PROTOCOL
ROOT=Path(__file__).resolve().parent.parent
class MCPClient:
    def __init__(self,kind):self.kind=kind;self.proc=None;self.counter=0;self.tools=[]
    async def __aenter__(self):
        try:
            self.proc=await asyncio.create_subprocess_exec(sys.executable,'-m','backend.mcp_server',self.kind,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,cwd=str(ROOT),env={**os.environ,'IMPACTIQ_DB':str(store.DB_PATH)},limit=1024*1024)
            result=await self.rpc('initialize',{'protocolVersion':PROTOCOL,'capabilities':{},'clientInfo':{'name':'ImpactIQ','version':'1.0.0'}})
            if result['protocolVersion']!=PROTOCOL:raise RuntimeError('Unsupported negotiated MCP version')
            await self.send({'jsonrpc':'2.0','method':'notifications/initialized'})
            self.tools=(await self.rpc('tools/list',{}))['tools'];return self
        except BaseException:
            await self.close();raise
    async def send(self,msg):
        self.proc.stdin.write((json.dumps(msg)+'\n').encode());await self.proc.stdin.drain()
    async def rpc(self,method,params):
        self.counter+=1;rid=self.counter;await self.send({'jsonrpc':'2.0','id':rid,'method':method,'params':params})
        line=await asyncio.wait_for(self.proc.stdout.readline(),timeout=5)
        if not line:raise RuntimeError(f'{self.kind} MCP process ended')
        res=json.loads(line)
        if res.get('id')!=rid or 'error' in res:raise RuntimeError(f'{self.kind} MCP request failed: {res.get("error","unexpected response")}')
        return res['result']
    async def call(self,name,sid):
        if name not in {x['name'] for x in self.tools}:raise RuntimeError('Tool not discovered')
        res=await self.rpc('tools/call',{'name':name,'arguments':{'scenarioId':sid}})
        if res.get('isError'):raise RuntimeError(res['content'][0]['text'])
        return json.loads(res['content'][0]['text'])
    async def close(self):
        if self.proc and self.proc.returncode is None:
            self.proc.stdin.close()
            try:await asyncio.wait_for(self.proc.wait(),1)
            except asyncio.TimeoutError:
                self.proc.kill();await self.proc.wait()
    async def __aexit__(self,*args):await self.close()

async def collect(kind,names,sid):
    start=time.perf_counter()
    async with MCPClient(kind) as m:
        records=[]
        for n in names:records.append((n,await m.call(n,sid)))
        return records,[x['name'] for x in m.tools],round((time.perf_counter()-start)*1000,1)
