import {spawn} from 'node:child_process'
import {readFile,writeFile} from 'node:fs/promises'

const binary=process.argv.includes('--zen')?'/var/lib/flatpak/app/app.zen_browser.zen/x86_64/stable/active/files/zen/zen':process.env.JARVIS_BROWSER_BINARY||'/usr/bin/firefox'
const reducedMotion=!process.argv.includes('--motion')
const skipWire=process.argv.includes('--skip-wire')
const voices=process.argv.includes('--voice-on-only')?[true]:[false,true]
const driver=spawn('/usr/bin/geckodriver',['--host','127.0.0.1','--port','9224'],{stdio:'ignore'})
const base='http://127.0.0.1:9224'
let session
async function call(path,body){
 const response=await fetch(base+path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)})
 const result=await response.json()
 if(!response.ok)throw new Error(JSON.stringify(result.value))
 return result.value
}
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms))
try{
 for(let i=0;i<40;i++){try{await call('/status');break}catch{await delay(100)}}
 const created=await call('/session',{capabilities:{alwaysMatch:{browserName:'firefox','moz:firefoxOptions':{binary,args:['-headless']}}}})
 session=created.sessionId
 const path='/session/'+session
 await call(path+'/timeouts',{script:180000,pageLoad:30000})
 await call(path+'/url',{url:'http://127.0.0.1:8787'})
 const evaluate=(script,args=[])=>call(path+'/execute/sync',{script,args})
 const deferReviews=async()=>{for(let i=0;i<5;i++){await delay(250);await evaluate(`document.querySelector('dialog[open] button[aria-label="Review later"]')?.click()`);}}
 await evaluate(`localStorage.setItem('jarvis.preferences.v3',JSON.stringify({autoSpeak:false,voice:false,reducedMotion:arguments[0]})); location.reload();`,[reducedMotion])
 await delay(1000)
 const token=(await readFile('.runtime/login.token','utf8')).trim()
 await evaluate(`const element=document.querySelector('input');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(element,arguments[0]);element.dispatchEvent(new Event('input',{bubbles:true}));`,[token])
 await evaluate(`document.querySelector('form').requestSubmit();`)
 for(let i=0;i<60;i++){if(await evaluate(`return !!document.querySelector('#instruction')`))break;await delay(150)}
 const paired=await evaluate(`return !!document.querySelector('#instruction')`)
 if(!paired)throw new Error('Firefox pairing did not complete')
 await deferReviews()
 const result=skipWire?null:await call(path+'/execute/async',{script:`const done=arguments[arguments.length-1];(async()=>{
  const {csrf}=await(await fetch('/api/auth/session')).json();
  const chunks=[];const start=performance.now();
  try{
   const response=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({text:'Hello'})});
   const headers=Object.fromEntries(response.headers);const reader=response.body.getReader();
   try{while(true){const {value,done}=await reader.read();if(done)break;chunks.push(new TextDecoder().decode(value))}}
   catch(error){return done({ok:false,stage:'stream',error:String(error),headers,chunks,elapsed:performance.now()-start})}
   done({ok:true,status:response.status,headers,chunks,elapsed:performance.now()-start})
  }catch(error){done({ok:false,stage:'fetch',error:String(error),chunks,elapsed:performance.now()-start})}
 })().catch(error=>done({error:String(error)}));`,args:[]})
 const checks={binary,capabilities:created.capabilities,reducedMotion,wire:result,ui:[]}
 for(const voice of voices){
  await evaluate(`localStorage.setItem('jarvis.preferences.v3',JSON.stringify({autoSpeak:arguments[0],voice:arguments[0],reducedMotion:arguments[1]}));sessionStorage.removeItem('jarvis.session');`,[voice,reducedMotion])
  await call(path+'/url',{url:'http://127.0.0.1:8787/'})
  for(let i=0;i<60;i++){if(await evaluate(`return !!document.querySelector('#instruction')`))break;await delay(150)}
  await deferReviews()
  await evaluate(`window.__networkQA=[];window.__chatQA={events:[],body:'',ended:false};const nativeFetch=window.fetch;window.fetch=async(...args)=>{const path=String(args[0]);try{const response=await nativeFetch(...args);window.__networkQA.push({path,status:response.status});if(path==='/api/chat'){const getReader=response.body.getReader.bind(response.body);response.body.getReader=(...options)=>{const reader=getReader(...options),read=reader.read.bind(reader),decoder=new TextDecoder();reader.read=async(...options)=>{try{const chunk=await read(...options);if(chunk.done)window.__chatQA.ended=true;else{window.__chatQA.body+=decoder.decode(chunk.value,{stream:true});window.__chatQA.events=window.__chatQA.body.split('\\n').filter(line=>line.startsWith('data: ')).flatMap(line=>{try{return [JSON.parse(line.slice(6))]}catch{return []}})}return chunk}catch(error){window.__networkQA.push({stage:'reader',error:String(error)});throw error}};return reader}}return response}catch(error){window.__networkQA.push({path,error:String(error)});throw error}};window.__audioQA={played:false,playing:false};const play=HTMLMediaElement.prototype.play;HTMLMediaElement.prototype.play=async function(...args){const result=await play.apply(this,args);window.__audioQA.played=true;window.__audioQA.playing=!this.paused;return result};`)
  const input=await call(path+'/element',{using:'css selector',value:'#instruction'})
  await call(path+'/element/'+input['element-6066-11e4-a52e-4f735466cecf']+'/value',{text:'Hello'})
  const button=await call(path+'/element',{using:'css selector',value:'button[aria-label="Send instruction"]'})
  await call(path+'/element/'+button['element-6066-11e4-a52e-4f735466cecf']+'/click',{})
  const started=Date.now()
  let state
  for(let i=0;i<180;i++){
   state=await evaluate(`const message=[...document.querySelectorAll('.message.assistant')].at(-1);return {error:document.querySelector('[role="alert"]')?.textContent||null,answer:message?[...message.children].filter(child=>!child.classList.contains('message-meta')&&!child.classList.contains('message-actions')).map(child=>child.textContent).join('\\n'):null,failed:message?.classList.contains('failed'),busy:!!document.querySelector('[aria-label="Cancel generation"]'),phase:document.querySelector('.phase-code')?.textContent,network:window.__networkQA,stream:window.__chatQA,audio:window.__audioQA,canvas:!!document.querySelector('canvas'),fallback:!!document.querySelector('.core-fallback'),coreLabel:document.querySelector('.core-bottom')?.textContent}`)
   if(state.error||(!state.busy&&state.answer?.trim()&&state.stream.ended&&state.stream.events.some(event=>event.type==='done')&&(!voice||state.audio.played)))break
   await delay(500)
  }
  checks.ui.push({voice,...state,elapsed:Date.now()-started})
 }
 await writeFile('.runtime/firefox-chat-check.json',JSON.stringify(checks,null,2))
 console.log(JSON.stringify({...checks,wire:result?{...result,chunks:result.chunks?.length}:null,ui:checks.ui.map(state=>({...state,answer:state.answer?.length,stream:{ended:state.stream?.ended,events:state.stream?.events.map(event=>event.type)}}))},null,2))
 if((result&&(!result.ok||result.status!==200||!result.chunks?.join('').includes('"type": "done"')))||checks.ui.some(state=>state.error||state.failed||state.busy||!state.answer?.trim()||!state.stream.ended||!state.stream.events.some(event=>event.type==='done')||state.stream.events.some(event=>event.type==='error')||(state.voice&&!state.audio.played)))process.exitCode=1
}finally{
 if(session)await fetch(base+'/session/'+session,{method:'DELETE'}).catch(()=>{})
 driver.kill('SIGTERM')
}
