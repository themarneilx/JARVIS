import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {relative,resolve} from 'node:path';
import {homedir} from 'node:os';

export async function checkAccess(page,request,useSyntheticSpeech,evidence,memoryHome) {
  if(process.argv.includes('--memory-ui')) {
    await page.getByRole('button',{name:'Memory',exact:true}).click();
    const text="User's name is Alex. Address the user formally as sir.";
    await page.getByLabel('Why keep this?',{exact:true}).fill('Disposable browser fixture; never a live user preference');
    await page.getByLabel('Memory content',{exact:true}).fill(text);
    await page.getByRole('button',{name:'Propose memory',exact:true}).click();
    const dialog=page.getByRole('dialog').filter({hasText:text});
    await dialog.waitFor({timeout:15000});
    assert.equal((await request('/memory')).entries.length,0);
    await dialog.getByRole('button',{name:'Approve once',exact:true}).click();
    await page.getByRole('status').filter({hasText:'The preference was saved to USER.md.'}).waitFor({timeout:30000});
    await page.getByRole('heading',{name:'Saved knowledge',exact:true}).locator('..').locator('..').getByText(text,{exact:true}).waitFor();
    assert.equal((await request('/memory')).entries[0].text,text);
    assert((await readFile(memoryHome+'/memories/USER.md','utf8')).includes(text));
    await page.reload();
    await page.getByRole('button',{name:'Memory',exact:true}).click();
    await page.getByRole('heading',{name:'Saved knowledge',exact:true}).locator('..').locator('..').getByText(text,{exact:true}).waitFor();
    evidence.memory={isolatedNativeProfile:true,unapprovedWrite:false,approvedNativeWrite:true,savedPanelRefresh:true,freshProcessAndPageRetrieval:true};
    return;
  }
  if(process.argv.includes('--home-access')) {
    await page.getByRole('button',{name:'System',exact:true}).click();
    await page.getByRole('heading',{name:'Installed applications',exact:true}).waitFor();
    const catalog=await request('/applications');assert(catalog.available&&catalog.applications.length);
    const app=catalog.applications[0];
    await page.getByRole('button',{name:'Request launch of '+app.name,exact:true}).click();
    const dialog=page.getByRole('dialog').filter({hasText:app.effect});await dialog.waitFor({timeout:10000});
    const action=(await request('/actions')).find(a=>a.kind==='launch');assert.equal(action.status,'pending');
    await dialog.getByRole('button',{name:'Reject',exact:true}).click();
    assert.equal((await request('/actions')).find(a=>a.id===action.id).status,'rejected');
    const path=relative(homedir(),resolve('README.md'));
    const result=await request('/home/lookup',{kind:'read',path});assert.match(result.text,/J\.A\.R\.V\.I\.S/);
    const rootPath=path.split('/').slice(0,-1).join('/');
    await page.getByLabel('Folder relative to home',{exact:true}).fill(rootPath);
    await page.getByRole('button',{name:'Browse folder',exact:true}).click();
    await page.getByRole('button',{name:'Preview text from '+path,exact:true}).click();
    await page.locator('pre').filter({hasText:/J\.A\.R\.V\.I\.S/}).waitFor();
    const forbidden=await page.evaluate(async()=>{const{csrf}=await(await fetch('/api/auth/session')).json();return(await fetch('/api/home/lookup',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({kind:'read',path:'/etc/passwd'})})).status;});
    assert.equal(forbidden,400);
    await page.setViewportSize({width:412,height:915});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    await page.screenshot({path:'/tmp/jarvis-home-access.png',fullPage:true});
    evidence.homeAccess={actualCatalog:true,launchProposalRejectedWithoutExecution:true,homeFilePreview:true,outsideHomeRefused:true,mobileOverflow:false};
    return;
  }
  const chats=[];page.on('request',r=>{if(r.url().endsWith('/api/chat'))chats.push(r);});
  await useSyntheticSpeech('Hey Jarvis.');
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  await page.getByText('Enable “Hey Jarvis” listening',{exact:true}).check();
  await page.waitForFunction(()=>window.__qaStreams?.length>0);
  await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));});
  await page.waitForFunction(()=>window.__qaStreams.every(stream=>stream.getTracks().every(track=>track.readyState==='ended')));
  await page.getByText('Keep listening when this browser is in the background',{exact:true}).check();
  await page.getByRole('status').filter({hasText:'At your service, sir.'}).waitFor({timeout:45000});
  assert.equal(chats.length,0);
  await page.getByRole('button',{name:'Stop wake listening',exact:true}).click();
  await page.waitForFunction(()=>window.__qaStreams.every(stream=>stream.getTracks().every(track=>track.readyState==='ended')));
  const prefs=await page.evaluate(()=>JSON.parse(localStorage.getItem('jarvis.preferences.v3')));
  assert.equal(prefs.backgroundWake,false);
  await page.evaluate(()=>{delete document.hidden;document.dispatchEvent(new Event('visibilitychange'));});
  evidence.backgroundWake={explicitOptIn:true,foregroundOnlyStopsWhenHidden:true,hiddenOptInRecognizesRealSpeech:true,bareWakeModelRequests:chats.length,stopReleasesCapture:true,simulatedVisibility:true,physicalMicrophoneVerified:false};
}
