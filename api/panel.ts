import { GET as sandboxGET, POST as sandboxPOST } from "./sandbox-control";

function html(): string {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover" />
<title>Job Agent Control</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#0b0d10;color:#f5f7fa;font:16px system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{max-width:560px;margin:0 auto;padding:24px 18px 40px}h1{font-size:28px;margin:8px 0 4px}.sub{color:#9aa3ad;margin:0 0 24px}.card{background:#15191f;border:1px solid #2a3038;border-radius:18px;padding:18px;margin:14px 0}label{display:block;color:#b7c0ca;font-size:14px;margin:14px 0 7px}input,select{width:100%;padding:14px;border-radius:12px;border:1px solid #39414c;background:#0f1216;color:#fff;font-size:16px}button{width:100%;padding:15px;border:0;border-radius:12px;font-weight:700;font-size:16px;margin-top:10px;cursor:pointer}#start{background:#fff;color:#111}#stop{background:#2a3038;color:#fff}.status{display:flex;align-items:center;gap:10px;font-weight:700}.dot{width:11px;height:11px;border-radius:50%;background:#8b949e}.running{background:#2ea043}.error{background:#f85149}.log{white-space:pre-wrap;word-break:break-word;color:#aeb7c2;font-size:13px;margin-top:12px}.small{font-size:12px;color:#7f8995;margin-top:10px}.danger{color:#ff7b72}.row{display:grid;grid-template-columns:1fr 1fr;gap:10px}@media(max-width:380px){.row{grid-template-columns:1fr}}
</style></head>
<body><main>
<h1>🤖 Job Agent</h1><p class="sub">Mobile control panel — test with 1 application first.</p>
<div class="card"><div class="status"><span id="dot" class="dot"></span><span id="status">Checking…</span></div><div id="details" class="small"></div></div>
<div class="card">
<label for="password">Control password</label>
<input id="password" type="password" autocomplete="current-password" placeholder="MCP_AUTH_TOKEN" />
<div class="row"><div><label for="max">Applications</label><input id="max" type="number" min="1" max="20" value="1" /></div><div><label for="mode">Mode</label><select id="mode"><option value="fully_automated">Fully automated</option><option value="semi_automated">Semi automated</option></select></div></div>
<button id="start">Start agent</button><button id="stop">Stop agent</button>
<div id="message" class="log"></div><div class="small">For the first real test, keep Applications = 1.</div>
</div>
<script>
const $=id=>document.getElementById(id);
const saved=localStorage.getItem('job_agent_control_token'); if(saved) $('password').value=saved;
function headers(){return {'content-type':'application/json','authorization':'Bearer '+$('password').value.trim()}}
async function call(method,body){
  const token=$('password').value.trim(); if(!token){$('message').textContent='Enter the control password first.';return null}
  localStorage.setItem('job_agent_control_token',token);
  const r=await fetch('/api/sandbox-control',{method,headers:headers(),body:body?JSON.stringify(body):undefined});
  const text=await r.text(); let data; try{data=JSON.parse(text)}catch{data={error:text}}
  if(!r.ok) throw new Error(data.error||('HTTP '+r.status)); return data;
}
function show(data){
  const s=data?.status||'unknown'; $('status').textContent=s.replaceAll('_',' '); $('dot').className='dot '+(s.includes('running')||s==='started'||s==='already_running'?'running':s==='error'?'error':'');
  $('details').textContent=[data?.sandbox_id&&('Sandbox: '+data.sandbox_id),data?.run_id&&('Run: '+data.run_id)].filter(Boolean).join(' · ');
  if(data?.error) $('message').textContent=data.error;
}
async function status(){try{show(await call('GET'))}catch(e){$('status').textContent='Not connected';$('dot').className='dot error';$('message').textContent=e.message}}
$('start').onclick=async()=>{ $('message').textContent='Starting…'; try{show(await call('POST',{action:'start',max_applications:Number($('max').value||1),automation_mode:$('mode').value}))}catch(e){$('message').textContent=e.message;$('dot').className='dot error'} };
$('stop').onclick=async()=>{ $('message').textContent='Stopping…'; try{show(await call('POST',{action:'stop'}))}catch(e){$('message').textContent=e.message;$('dot').className='dot error'} };
status(); setInterval(status,10000);
</script></main></body></html>`;
}

export async function GET(): Promise<Response> {
  return new Response(html(), { headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } });
}

export async function POST(request: Request): Promise<Response> {
  const password = request.headers.get("x-control-password");
  if (!password) return new Response(JSON.stringify({ error: "Control password required" }), { status: 401, headers: { "content-type": "application/json" } });
  const body = await request.text();
  const proxy = new Request(request.url, { method: "POST", headers: { "authorization": `Bearer ${password}`, "content-type": "application/json" }, body });
  return sandboxPOST(proxy);
}
