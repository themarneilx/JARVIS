import {chromium} from '../frontend/node_modules/playwright-core/index.mjs'
import {readFile,writeFile} from 'node:fs/promises'
const browser=await chromium.connectOverCDP('http://127.0.0.1:9223')
const page=await browser.newPage({viewport:{width:1512,height:982}})
const artifacts=[]
page.on('response',async response=>{
 if(response.url().endsWith('/api/audio/synthesize')&&response.ok())artifacts.push(await response.json())
})
try{
 await page.addInitScript(()=>{
  localStorage.setItem('jarvis.preferences.v3',JSON.stringify({startupSound:false,quality:'balanced',reducedMotion:false,voice:true,autoSpeak:true,volume:0.8,mic:'',output:'',autoSubmit:false}))
  window.__voiceQA={samples:0,maxRms:0,spectrumSamples:0,maxFrequency:0}
  const original=AnalyserNode.prototype.getByteTimeDomainData
  AnalyserNode.prototype.getByteTimeDomainData=function(array){
   original.call(this,array)
   window.__voiceQA.samples++
   let energy=0
   for(const value of array)energy+=((value-128)/128)**2
   window.__voiceQA.maxRms=Math.max(window.__voiceQA.maxRms,Math.sqrt(energy/array.length))
  }
  const frequency=AnalyserNode.prototype.getByteFrequencyData
  AnalyserNode.prototype.getByteFrequencyData=function(array){
   frequency.call(this,array)
   window.__voiceQA.spectrumSamples++
   window.__voiceQA.maxFrequency=Math.max(window.__voiceQA.maxFrequency,...array)
  }
 })
 await page.goto('http://127.0.0.1:8787')
 await page.getByLabel('Local pairing token',{exact:true}).fill((await readFile('.runtime/login.token','utf8')).trim())
 await page.getByRole('button',{name:'Connect local session'}).click()
 await page.getByTestId('core-stage').waitFor()
 await page.getByRole('textbox',{name:'Your instruction',exact:true}).fill('Jarvis, say exactly: At your service, sir. All systems await your instruction.')
 await page.getByRole('button',{name:'Send instruction'}).click()
 await page.getByRole('button',{name:'Cancel generation'}).waitFor()
 await page.getByRole('button',{name:'Send instruction'}).waitFor({timeout:180000})
 await page.waitForFunction(()=>window.__voiceQA.maxRms>0.005,null,{timeout:90000})
 const first=await page.evaluate(()=>({...window.__voiceQA}))
 const speaking=await page.locator('.phase-code').innerText()
 await page.screenshot({path:'/tmp/jarvis-speaking.png'})
 await page.getByRole('button',{name:'Stop speaking',exact:true}).click()
 await page.waitForFunction(()=>document.querySelector('.phase-code')?.textContent==='IDLE')
 await page.evaluate(()=>{window.__voiceQA.maxRms=0})
 await page.getByRole('button',{name:'Speak message',exact:true}).last().click()
 await page.waitForFunction(()=>window.__voiceQA.maxRms>0.005,null,{timeout:90000})
 const replay=await page.evaluate(()=>({...window.__voiceQA}))
 await page.getByRole('button',{name:'Stop speaking',exact:true}).click()
 const result={provider:'JarvisLuxTTS',mockedAudio:false,automaticSpeech:true,artifacts,firstPlayback:first,speakingState:speaking,replay,stopReturnedIdle:true,physicalSpeakersVerified:false}
 await writeFile('.runtime/voice-browser-check.json',JSON.stringify(result,null,2))
 console.log(JSON.stringify(result,null,2))
 if(speaking!=='SPEAKING'||!artifacts.length||!first.spectrumSamples||!first.maxFrequency)process.exitCode=1
 await page.getByRole('button',{name:'Lock session',exact:true}).click()
}finally{await page.close();await browser.close()}
