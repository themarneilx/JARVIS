import assert from 'node:assert/strict';
import { holdMicrophone } from './hold-microphone.mjs';

export async function checkVoiceControls(page,request,useSyntheticSpeech,evidence,transcriptions) {
  const chats=[];
  page.on('request',r=>{if(r.url().endsWith('/api/chat'))chats.push(r);});
  const microphone=page.getByRole('button',{name:'Hold microphone to speak',exact:true});
  await page.evaluate(()=>{
    navigator.mediaDevices.getUserMedia=()=>new Promise(resolve=>{window.__resolvePermission=resolve;});
  });
  await holdMicrophone(page,microphone,100,async()=>{
    await page.waitForFunction(()=>typeof window.__resolvePermission==='function');
  });
  await page.evaluate(()=>{
    const context=new AudioContext(),destination=context.createMediaStreamDestination();
    window.__latePermissionStream=destination.stream;
    destination.stream.getTracks().forEach(t=>t.addEventListener('ended',()=>void context.close()));
    window.__resolvePermission(destination.stream);
  });
  await page.waitForFunction(()=>window.__latePermissionStream.getTracks().every(t=>t.readyState==='ended'));
  assert.equal(transcriptions.length,0);
  evidence.releaseBeforePermissionStopsLateCapture=true;

  const fixture=await useSyntheticSpeech('Jarvis, are you there?');
  await holdMicrophone(page,microphone,(fixture.duration+1)*1000,async()=>{
    await page.waitForFunction(()=>document.querySelector('.phase-code')?.textContent==='LISTENING');
    assert.equal(transcriptions.length,0,'Speech must not upload while the button is held');
  });
  await page.waitForFunction(()=>document.querySelector('.message.user')?.textContent.toLowerCase().includes('are you there'),null,{timeout:30000});
  await page.getByRole('button',{name:'Send instruction',exact:true}).waitFor({timeout:120000});
  assert.equal(chats.length,1);
  evidence.releaseTranscribesAndSends=true;

  const before=transcriptions.length;
  await holdMicrophone(page,microphone,250,async()=>{
    await page.waitForFunction(()=>document.querySelector('.phase-code')?.textContent==='LISTENING');
    await page.evaluate(()=>window.dispatchEvent(new Event('blur')));
  });
  await page.waitForTimeout(300);
  assert.equal(transcriptions.length,before);
  evidence.blurCancelsWithoutUpload=true;

  const proposal=await request('/actions',{kind:'volume',target:'35',effect:'QA microphone gesture test only. Reject this request.'});
  await page.getByRole('dialog').filter({hasText:proposal.effect}).waitFor({timeout:10000});
  const confirmation=page.getByRole('button',{name:'Hold microphone for confirmation',exact:true});
  await confirmation.focus();
  await page.keyboard.down('Space');
  await page.waitForFunction(()=>document.querySelector('button[aria-label="Hold microphone for confirmation"]')?.getAttribute('aria-pressed')==='true');
  await page.getByRole('dialog').getByRole('button',{name:'Reject',exact:true}).click();
  await page.keyboard.up('Space');
  await page.getByRole('dialog').waitFor({state:'hidden'});
  assert.equal(transcriptions.length,before,'Hand rejection must discard an in-progress confirmation');
  assert.equal((await request('/actions')).find(a=>a.id===proposal.id).status,'rejected');
  evidence.confirmationHoldAndHandRejectionStopCapture=true;

  const second=await request('/actions',{kind:'volume',target:'35',effect:'QA release-to-transcribe confirmation test. Leave unapproved.'});
  await page.getByRole('dialog').filter({hasText:second.effect}).waitFor({timeout:10000});
  await holdMicrophone(page,confirmation,(fixture.duration+1)*1000);
  await page.getByRole('status').filter({hasText:/Heard:/}).waitFor({timeout:20000});
  assert.equal((await request('/actions')).find(a=>a.id===second.id).status,'pending');
  assert.equal(chats.length,1,'Unrecognized approval speech must stay in the review popup');
  evidence.confirmationReleaseTranscribes=true;
  evidence.unrecognizedConfirmationRemainsPending=true;
  await page.getByRole('dialog').getByRole('button',{name:'Reject',exact:true}).click();
  await page.clock.install();
  const beforeCap=transcriptions.length;
  await holdMicrophone(page,microphone,(fixture.duration+1)*1000,async()=>{
    await page.waitForFunction(()=>document.querySelector('.phase-code')?.textContent==='LISTENING');
    await page.waitForTimeout((fixture.duration+0.5)*1000);
    await page.clock.fastForward(60000);
    await page.waitForFunction(()=>document.querySelector('.phase-code')?.textContent!=='LISTENING');
    await page.waitForResponse(r=>r.url().endsWith('/api/audio/transcribe')&&r.ok(),{timeout:30000});
  });
  await page.getByRole('button',{name:'Send instruction',exact:true}).waitFor({timeout:120000});
  assert.equal(transcriptions.length,beforeCap+1,'The recording cap must submit once even while the gesture is held');
  evidence.recordingCapSubmitsOnceWhileHeld='60-second timer advanced by Playwright clock; real MediaRecorder/STT';
  evidence.desktopMutations='blocked by isolated QA executor';
  assert(transcriptions.every(t=>t.provider==='parakeet'));
  await page.setViewportSize({width:412,height:915});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.screenshot({path:'/tmp/jarvis-hold-to-talk-mobile.png'});
}
