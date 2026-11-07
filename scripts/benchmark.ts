// Read-only model inspection and explicit, bounded inference probe. No service changes.
import { readFile,writeFile } from 'node:fs/promises'
import { performance } from 'node:perf_hooks'
import { execFileSync } from 'node:child_process'
const base='http://127.0.0.1:11434'
async function request(path:string,body?:unknown){
 const r=await fetch(base+path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(180000)})
 const data=await r.json();return {status:r.status,data}
}
const tags=await request('/api/tags')
let selected:string|undefined
try{selected=JSON.parse(await readFile('.runtime/model-selection.json','utf8')).model}catch(error){if((error as NodeJS.ErrnoException).code!=='ENOENT')throw error}
const model=process.env.JARVIS_BENCHMARK_MODEL||selected||'jarvis-qwen35-4b-64k:latest'
if(!tags.data.models?.some((entry:{name:string})=>entry.name===model))throw new Error('Select an installed local model in Settings before benchmarking')
const show=await request('/api/show',{model})
const before=await request('/api/ps')
const result:Record<string,unknown>={at:new Date().toISOString(),model,show:show.data,before:before.data,compatibility:'unverified'}
if(process.argv.includes('--tools')){
 const start=performance.now()
 const test=await request('/api/chat',{model,stream:false,think:false,keep_alive:'2m',options:{num_ctx:64000,num_predict:160,temperature:0},messages:[{role:'user',content:'Call both read_cpu and read_gpu. Do not guess the readings.'}],tools:['read_cpu','read_gpu'].map(name=>({type:'function',function:{name,description:'Read a live system measurement',parameters:{type:'object',properties:{},required:[]}}}))})
 result.tool_test={...test,elapsed_ms:performance.now()-start}
 result.after=(await request('/api/ps')).data
 try{result.placement_cli=execFileSync('ollama',['ps'],{encoding:'utf8',timeout:5000}).trim()}catch{result.placement_cli='unavailable'}
 result.compatibility=test.status===200&&test.data.message?.tool_calls?.length>=2?'model_tool_probe_passed_Hermes_still_unverified':'failed_model_tool_probe'
 if(test.status===200&&test.data.message?.tool_calls?.length>=2){
  const plugin=(await readFile('.runtime/plugin.token','utf8')).trim()
  const metrics=await (await fetch('http://127.0.0.1:8787/api/internal/telemetry',{headers:{Authorization:`Bearer ${plugin}`}})).json()
  const readings={cpu_percent:metrics.cpu_percent,gpu:metrics.gpu,sampled_at:metrics.sampled_at}
  const messages=[{role:'user',content:'Call both read_cpu and read_gpu. Do not guess the readings.'},test.data.message]
  for(const call of test.data.message.tool_calls){
   if(!['read_cpu','read_gpu'].includes(call.function.name)||Object.keys(call.function.arguments).length)throw new Error('Unexpected tool name or arguments')
   messages.push({role:'tool',tool_name:call.function.name,content:JSON.stringify(call.function.name==='read_cpu'?{cpu_percent:metrics.cpu_percent,sampled_at:metrics.sampled_at}:{gpu:metrics.gpu,sampled_at:metrics.sampled_at})})
  }
  const next=performance.now()
  const reply=await request('/api/chat',{model,stream:false,think:false,keep_alive:'2m',options:{num_ctx:64000,num_predict:160,temperature:0},messages})
  result.round_trip={readings,reply:reply.data,elapsed_ms:performance.now()-next,verified_tools:metrics.gpu!=null&&typeof metrics.cpu_percent==='number'}
 }
}
await writeFile('.runtime/ollama-benchmark.json',JSON.stringify(result,null,2),{mode:0o600})
console.log(JSON.stringify({model,capabilities:show.data.capabilities,tool_test:result.tool_test,round_trip:result.round_trip,placement:result.after??before.data,compatibility:result.compatibility},null,2))
