import {chromium} from '../frontend/node_modules/playwright-core/index.mjs'
import {readFile,writeFile} from 'node:fs/promises'
const browser=await chromium.connectOverCDP('http://127.0.0.1:9223')
const page=await browser.newPage()
try{
 await page.goto('http://127.0.0.1:8787')
 await page.getByLabel('Local pairing token',{exact:true}).fill((await readFile('.runtime/login.token','utf8')).trim())
 await page.getByRole('button',{name:'Connect local session'}).click()
 await page.getByTestId('core-stage').waitFor()
 const result=await page.evaluate(async()=>{
  const {csrf}=await (await fetch('/api/auth/session')).json()
  const start=performance.now()
  const response=await fetch('/api/audio/synthesize',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({text:'At your service, sir.'})})
  const result=await response.json()
  if(!response.ok)return {ok:false,status:response.status,result,elapsed_ms:performance.now()-start}
  const wav=await (await fetch(result.url)).arrayBuffer()
  return {ok:true,provider:result.provider,duration:result.duration,bytes:wav.byteLength,signature:new TextDecoder().decode(wav.slice(0,4)),elapsed_ms:performance.now()-start}
 })
 await writeFile('.runtime/speech-check.json',JSON.stringify(result,null,2));console.log(result)
}finally{await browser.close()}
