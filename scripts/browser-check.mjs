import { chromium } from '../frontend/node_modules/playwright-core/index.mjs'
import { readFile,writeFile } from 'node:fs/promises'
const attached=process.argv.includes('--cdp')
const browser=attached?await chromium.connectOverCDP('http://127.0.0.1:9223'):await chromium.launch({executablePath:'/usr/bin/google-chrome-stable',headless:true,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']})
const page=await browser.newPage({viewport:{width:1512,height:982}})
const pendingReview=page.locator('dialog[open] button[aria-label="Review later"]')
await page.addLocatorHandler(pendingReview,async()=>{
 // The next pending review can replace this dialog without a hidden frame.
 for(let i=0;i<32&&await pendingReview.isVisible();i++){await pendingReview.click();await page.waitForTimeout(50)}
},{noWaitAfter:true})
const errors=[]
const consoleMessages=[]
async function deferReviews(target){if(target===page)return;for(let i=0;i<32;i++){await target.waitForTimeout(100);const close=target.locator('dialog[open] button[aria-label="Review later"]');if(await close.count())await close.click();else break}}
page.on('pageerror',e=>errors.push(e.message))
page.on('console',message=>{
 if(!['warning','error'].includes(message.type()))return
 const entry={level:message.type(),text:message.text(),url:message.location().url}
 consoleMessages.push(entry)
 if(entry.level==='error'&&!/\/api\/(auth\/session|chat)$/.test(entry.url))errors.push(entry.text)
})
try{
 await page.addInitScript(()=>localStorage.setItem('jarvis.preferences.v3',JSON.stringify({autoSpeak:false,voice:true,startupSound:false})))
 await page.goto('http://127.0.0.1:8787')
 await page.getByLabel('Local pairing token').fill((await readFile('.runtime/login.token','utf8')).trim())
 await page.getByRole('button',{name:'Connect local session'}).click()
 await page.getByTestId('core-stage').waitFor()
 await deferReviews(page)
 await page.waitForTimeout(2500)
 const canvas=await page.locator('canvas').count()
 const coreNameVisible=await page.locator('.core-center').isVisible()
 const resourceSample=await page.evaluate(async()=>{const data=await (await fetch('/api/telemetry')).json();return {backend_rss:data.backend_rss,unavailable:data.unavailable,sampled_at:data.sampled_at,cpu_temperature:data.cpu_temperature,cpu_temperature_source:data.cpu_temperature_source}})
 const cpuTemperatureText=await page.getByText('CPU TEMP',{exact:true}).locator('..').innerText()
 await page.screenshot({path:'/tmp/jarvis-desktop.png',fullPage:true})
 const fallback=await browser.newPage()
 await fallback.addInitScript(()=>{const original=HTMLCanvasElement.prototype.getContext;HTMLCanvasElement.prototype.getContext=function(name,...args){return name==='webgl2'?null:original.call(this,name,...args)}})
 await fallback.goto('http://127.0.0.1:8787')
 await fallback.getByLabel('Local pairing token',{exact:true}).fill((await readFile('.runtime/login.token','utf8')).trim())
 await fallback.getByRole('button',{name:'Connect local session'}).click()
 await fallback.locator('.core-fallback').waitFor()
 await deferReviews(fallback)
 const simulatedWebGLFallback=await fallback.locator('.core-fallback').isVisible()
 await fallback.close()
 const liveAgent=!process.argv.includes('--expect-agent-error')
 const states=[]
 page.on('response',async response=>{if(response.url().endsWith('/api/chat')){try{const body=await response.text();for(const line of body.split('\n'))if(line.startsWith('data: ')){const event=JSON.parse(line.slice(6));if(['state','tool','done','error'].includes(event.type))states.push(event)}}catch{}}})
 await page.getByRole('textbox',{name:'Your instruction',exact:true}).fill(liveAgent?'Jarvis, good evening. Use your telemetry tool and give me a brief CPU, GPU temperature and battery report.':'Jarvis, are you there?')
 await page.getByRole('button',{name:'Send instruction'}).click()
 let failure=null,agentAnswer=null,historyRestored=false
 if(liveAgent){
  await page.getByRole('button',{name:'Cancel generation'}).waitFor()
  await page.getByRole('button',{name:'Send instruction'}).waitFor({timeout:180000})
  agentAnswer=await page.locator('.message.assistant').last().innerText()
  if(await page.getByRole('alert').count())throw new Error(await page.getByRole('alert').innerText())
  await page.reload()
  await deferReviews(page)
  await page.locator('.message.assistant').last().waitFor()
  historyRestored=(await page.locator('.message.assistant').last().innerText()).includes(agentAnswer.split('\n').find(line=>line.includes('CPU'))||'J.A.R.V.I.S.')
 }else{
  await page.getByRole('alert').waitFor()
  failure=await page.getByRole('alert').innerText()
 }
 await page.getByRole('button',{name:'System',exact:true}).click()
 await page.getByRole('heading',{name:'System & operations'}).waitFor()
 const system=await page.getByText('BACKEND MEMORY',{exact:true}).isVisible()
 await page.getByRole('button',{name:'Settings',exact:true}).click()
 await page.getByText('Reduce motion',{exact:true}).check()
 await page.getByRole('button',{name:'Command center',exact:true}).click()
 await page.getByText('REDUCED MOTION',{exact:false}).waitFor()
 await page.setViewportSize({width:390,height:844})
 await page.screenshot({path:'/tmp/jarvis-mobile.png',fullPage:true})
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)
 await page.setViewportSize({width:1512,height:982})
 // Simulated permission failure and a synthetic MediaStream test lifecycle only, not hardware STT.
 await page.evaluate(()=>{navigator.mediaDevices.getUserMedia=async()=>{throw new DOMException('Microphone denied for lifecycle test','NotAllowedError')}})
 await page.getByRole('button',{name:'Hold microphone to speak',exact:true}).focus()
 await page.keyboard.down('Space')
 await page.getByRole('alert').filter({hasText:'Microphone denied'}).waitFor()
 await page.keyboard.up('Space')
 const textUsableAfterDenied=await page.getByRole('textbox',{name:'Your instruction',exact:true}).isEnabled()
 await page.getByRole('button',{name:'Dismiss message'}).click()
 await page.evaluate(()=>{navigator.mediaDevices.getUserMedia=async()=>{const context=new AudioContext();const stream=context.createMediaStreamDestination().stream;window.__qaStream=stream;return stream}})
 await page.getByRole('button',{name:'Hold microphone to speak',exact:true}).focus()
 await page.keyboard.down('Space')
 await page.waitForFunction(()=>document.querySelector('.phase-code')?.textContent==='LISTENING')
 await page.getByRole('button',{name:'Lock session',exact:true}).click()
 await page.keyboard.up('Space')
 await page.getByLabel('Local pairing token',{exact:true}).waitFor()
 const captureStopped=await page.evaluate(()=>window.__qaStream.getTracks().every(track=>track.readyState==='ended'))
 const result={title:await page.title(),canvas,coreNameVisible,simulatedWebGLFallback,systemPanel:system,agentFailure:failure,agentAnswer,historyRestored,states,consoleErrors:errors,consoleMessages,mobileOverflow:overflow,resourceSample,cpuTemperatureText,renderingEnvironment:'Headless Chrome; physical RTX frame rate not measured',simulatedMicrophone:{textUsableAfterDenied,captureStoppedOnLock:captureStopped,hardwareVerified:false},screenshots:['/tmp/jarvis-desktop.png','/tmp/jarvis-mobile.png']}
 await writeFile('.runtime/browser-check.json',JSON.stringify(result,null,2))
 console.log(JSON.stringify(result,null,2))
 if(errors.length||overflow||!canvas||!coreNameVisible||!simulatedWebGLFallback||!captureStopped||!textUsableAfterDenied)process.exitCode=1
}finally{await browser.close()}
