import {chromium} from '../frontend/node_modules/playwright-core/index.mjs'
import { holdMicrophone } from './hold-microphone.mjs';
import {readFile,writeFile} from 'node:fs/promises'
const browser=await chromium.connectOverCDP('http://127.0.0.1:9223')
const page=await browser.newPage({viewport:{width:1512,height:982}})
const transcriptions=[],speech=[]
page.on('response',async response=>{
 try{
 if(response.ok()&&response.url().endsWith('/api/audio/transcribe'))transcriptions.push(await response.json())
 if(response.ok()&&response.url().endsWith('/api/audio/synthesize'))speech.push(await response.json())
 }catch{}
})
try{
 await page.addInitScript(()=>{
  localStorage.setItem('jarvis.preferences.v3',JSON.stringify({quality:'balanced',reducedMotion:false,voice:true,autoSpeak:true,volume:0.8,mic:'',output:'',autoSubmit:false}))
  window.__conversationQA={maxRms:0,ended:false,tools:[]}
  const nativeFetch=window.fetch
  window.fetch=async(...args)=>{
   const response=await nativeFetch(...args)
   if(String(args[0]).endsWith('/api/chat'))response.clone().text().then(text=>{
    for(const line of text.split('\n'))if(line.startsWith('data: ')){const event=JSON.parse(line.slice(6));if(event.type==='tool')window.__conversationQA.tools.push(event)}
   }).catch(()=>{})
   return response
  }
  const original=AnalyserNode.prototype.getByteTimeDomainData
  AnalyserNode.prototype.getByteTimeDomainData=function(array){original.call(this,array);let sum=0;for(const value of array)sum+=((value-128)/128)**2;window.__conversationQA.maxRms=Math.max(window.__conversationQA.maxRms,Math.sqrt(sum/array.length))}
 })
 await page.goto('http://127.0.0.1:8787')
 await page.getByLabel('Local pairing token',{exact:true}).fill((await readFile('.runtime/login.token','utf8')).trim())
 await page.getByRole('button',{name:'Connect local session'}).click()
 await page.getByTestId('core-stage').waitFor()
 const cpuTemperatureText=await page.getByText('CPU TEMP',{exact:true}).locator('..').innerText()
 const fixture=await page.evaluate(async()=>{
  const {csrf}=await(await fetch('/api/auth/session')).json()
  const response=await fetch('/api/audio/synthesize',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({text:'Jarvis, good evening. Give me a brief system status report.'})})
  const artifact=await response.json()
  if(!response.ok)throw new Error(artifact.detail)
  const buffer=await(await fetch(artifact.url)).arrayBuffer()
  navigator.mediaDevices.getUserMedia=async()=>{
   const context=new AudioContext()
   await context.resume()
   const source=context.createBufferSource(),destination=context.createMediaStreamDestination()
   source.buffer=await context.decodeAudioData(buffer.slice(0))
   source.connect(destination)
   source.onended=()=>{window.__conversationQA.ended=true}
   source.start(context.currentTime+0.3)
   window.__qaAudioContext=context
   return destination.stream
  }
  return {provider:artifact.provider,duration:artifact.duration,bytes:buffer.byteLength}
 })
 await holdMicrophone(page,page.getByRole('button',{name:'Hold microphone to speak',exact:true}),(fixture.duration+1)*1000)
 await page.waitForFunction(()=>document.querySelector('#instruction')?.value.trim().length>10,null,{timeout:60000})
 const transcript=await page.getByRole('textbox',{name:'Your instruction',exact:true}).inputValue()
 if(!/status|report/i.test(transcript))throw new Error('Transcription did not preserve the requested status report: '+transcript)
 await page.evaluate(()=>{window.__conversationQA.maxRms=0})
 await page.getByRole('button',{name:'Send instruction'}).click()
 await page.waitForFunction(()=>window.__conversationQA.maxRms>0.03||document.querySelector('[role="alert"]'),null,{timeout:180000})
 if(await page.getByRole('alert').count())throw new Error(await page.getByRole('alert').innerText())
 const speakingState=await page.locator('.phase-code').innerText()
 const answer=(await page.locator('.message.assistant').last().locator('p').allTextContents()).join('\n')
 const analyser=await page.evaluate(()=>window.__conversationQA.maxRms)
 const toolEvents=await page.evaluate(()=>window.__conversationQA.tools)
 await page.getByRole('button',{name:'Stop speaking',exact:true}).click()
 const result={mockedProviders:false,fixture,recording:'MediaRecorder WebM/Opus from real generated speech in a synthetic microphone stream',physicalMicrophoneVerified:false,transcript,transcriptions,answer,toolEvents,speakingState,playbackRms:analyser,automaticSpeech:speech.length>=2,voiceSpeed:speech.at(-1)?.speed,cpuTemperatureText}
 await writeFile('.runtime/conversation-check.json',JSON.stringify(result,null,2))
 console.log(JSON.stringify(result,null,2))
 if(speakingState!=='SPEAKING'||speech.length<2||!toolEvents.length||!/[0-9]/.test(answer))process.exitCode=1
 await page.getByRole('button',{name:'Lock session',exact:true}).click()
 await page.evaluate(()=>window.__qaAudioContext?.close())
}finally{await page.close();await browser.close()}
