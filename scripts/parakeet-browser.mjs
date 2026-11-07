import assert from 'node:assert/strict';
import { holdMicrophone } from './hold-microphone.mjs';

export async function checkParakeet(page,request,useSyntheticSpeech,evidence,transcriptions) {
  const status=await request('/status');
  assert.equal(status.audio.stt_provider,'parakeet');
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  await page.getByText('NVIDIA Parakeet v3 · CPU / Q8',{exact:true}).waitFor();
  await page.getByLabel('Enable voice output',{exact:true}).check();
  await page.getByLabel('Speak replies automatically',{exact:true}).check();
  await page.getByRole('button',{name:'Command center',exact:true}).click();
  const fixture=await useSyntheticSpeech('Jarvis, are you there?');
  await holdMicrophone(page,page.getByRole('button',{name:'Hold microphone to speak',exact:true}),(fixture.duration+1)*1000,async()=>{
    await page.waitForFunction(()=>document.querySelector('.phase-code')?.textContent==='LISTENING');
  });
  await page.waitForFunction(()=>document.querySelector('.chat-panel textarea')?.value.toLowerCase().includes('are you there'),null,{timeout:20000});
  const input=page.getByRole('textbox',{name:'Your instruction',exact:true});
  evidence.editableTranscript=await input.inputValue();
  assert.match(evidence.editableTranscript,/jarvis.*are you there/i);
  const played=await page.evaluate(()=>window.__qaPlayed);
  await page.getByRole('button',{name:'Send instruction',exact:true}).click();
  await page.waitForFunction(before=>window.__qaPlayed>before,played,{timeout:180000});
  evidence.manualSttToHermesToTts=true;
  await Promise.all([
    page.waitForResponse(r=>r.url().endsWith('/api/audio/cancel')),
    page.getByRole('button',{name:'Stop speaking',exact:true}).click(),
  ]);
  const wake=await useSyntheticSpeech('Hey Jarvis, are you there?');
  const beforeWake=await page.evaluate(()=>window.__qaPlayed);
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  await page.getByText('Enable “Hey Jarvis” listening',{exact:true}).check();
  await page.getByRole('button',{name:'Command center',exact:true}).click();
  await page.waitForFunction(before=>window.__qaPlayed>before,beforeWake,{timeout:180000});
  evidence.wakeSttToHermesToTts=true;
  evidence.wakeFixtureSeconds=wake.duration;
  await page.getByRole('button',{name:'Stop speaking',exact:true}).click();
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  await page.getByText('Enable “Hey Jarvis” listening',{exact:true}).uncheck();
  const chatRequests=[];
  page.on('request',r=>{if(r.url().endsWith('/api/chat'))chatRequests.push(r.url());});
  await useSyntheticSpeech('Hey Jarvis.');
  const beforeAcknowledgement=await page.evaluate(()=>window.__qaPlayed);
  await page.getByText('Enable “Hey Jarvis” listening',{exact:true}).check();
  await page.getByRole('button',{name:'Command center',exact:true}).click();
  await page.getByRole('status').filter({hasText:'At your service, sir.'}).waitFor({timeout:30000});
  await page.waitForFunction(before=>window.__qaPlayed>before,beforeAcknowledgement,{timeout:60000});
  assert.equal(chatRequests.length,0,'A bare wake cue must not create a fabricated user prompt or model diagnostic reply');
  evidence.bareWakeAcknowledgement='At your service, sir.';
  evidence.bareWakeModelRequests=0;
  await page.getByRole('button',{name:'Stop speaking',exact:true}).click();
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  await page.getByText('Enable “Hey Jarvis” listening',{exact:true}).uncheck();
  assert(transcriptions.length>=2);
  assert(transcriptions.every(t=>t.provider==='parakeet'&&t.model==='nvidia/parakeet-tdt-0.6b-v3'&&t.device==='cpu'));
  evidence.provider='nvidia/parakeet-tdt-0.6b-v3';
  evidence.sttDevice='cpu';
  evidence.physicalMicrophoneVerified=false;
  await page.screenshot({path:'/tmp/jarvis-parakeet-settings.png'});
}
