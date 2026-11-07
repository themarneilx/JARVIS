import { chromium } from '../frontend/node_modules/playwright-core/index.mjs';
import { readFile, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';

// Transcripts, VAD and chat are fixtures; browser capture/rendering/layout are real.
const browser = await chromium.connectOverCDP('http://127.0.0.1:9223');
const context = await browser.newContext({ viewport: { width: 1512, height: 982 } });
const page = await context.newPage();
const errors = [], prompts = [];
let transcript = '', transcriptions = 0;
page.on('pageerror', error => errors.push(error.message));
await page.addInitScript(() => {
  if (!localStorage.getItem('jarvis.preferences.v3')) localStorage.setItem('jarvis.preferences.v3', JSON.stringify({ voice: false, startupSound: false, processingSound: false }));
  window.__streams = [];
  navigator.mediaDevices.getUserMedia = async () => {
    const audio = new AudioContext(); await audio.resume();
    const destination = audio.createMediaStreamDestination(), oscillator = audio.createOscillator(), gain = audio.createGain();
    gain.gain.value = .0001; oscillator.connect(gain).connect(destination); oscillator.start();
    window.__streams.push(destination.stream); return destination.stream;
  };
  const sample = AnalyserNode.prototype.getFloatTimeDomainData;
  AnalyserNode.prototype.getFloatTimeDomainData = function(values) { sample.call(this, values); if (window.__vad) values.fill(window.__vad); };
});
const json = (route, value) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(value) });
await page.route('**/api/reviews', route => json(route, []));
await page.route('**/api/audio/transcribe', route => { transcriptions++; return json(route, { text: transcript }); });
await page.route('**/api/chat', route => {
  prompts.push(route.request().postDataJSON().text);
  const text = Array.from({ length: 90 }, (_, i) => `Paragraph ${i + 1}. This fixture supplies a long conversation so scrolling and the composer can be verified independently of model output.`).join('\n\n');
  return route.fulfill({ status: 200, contentType: 'text/event-stream', body: `data: ${JSON.stringify({ type: 'delta', text })}\n\ndata: {"type":"done"}\n\n` });
});
const enter = async () => {
  await page.getByRole('button', { name: 'Enter immersive mode', exact: true }).click();
  await page.waitForFunction(() => window.__streams.some(stream => stream.active));
};
const say = async text => {
  transcript = text; const before = transcriptions;
  await page.evaluate(() => window.__vad = .08); await page.waitForTimeout(800); await page.evaluate(() => window.__vad = 0);
  await page.waitForFunction(() => document.querySelector('.immersive-caption small')?.textContent !== 'TRANSCRIBING LOCALLY');
  for (let i = 0; transcriptions <= before && i < 50; i++) await page.waitForTimeout(100);
  assert(transcriptions > before, `No fixture transcription for ${text}`);
  await page.waitForTimeout(250);
};
const standby = () => page.waitForFunction(() => document.querySelector('.immersive-caption small')?.textContent.includes('SAY') && !document.querySelector('.attention-frame'));
const alwaysReady = () => page.waitForFunction(() => document.querySelector('.immersive-caption small')?.textContent === 'LISTENING · SPEAK NATURALLY' && !document.querySelector('.attention-frame'));
const listening = () => page.waitForFunction(() => document.querySelector('.attention-frame')?.getAttribute('data-mode') === 'listening');
async function chatBounds() {
  return page.evaluate(() => {
    const box = selector => { const r = document.querySelector(selector).getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height, right: r.right, bottom: r.bottom }; };
    return { drawer: box('.conversation-drawer'), panel: box('.chat-panel'), log: box('.messages'), composer: box('.composer'), controls: box('.immersive-controls'), core: box('.core-column'), overflow: document.documentElement.scrollWidth > innerWidth, windowScroll: scrollY };
  });
}
function bounded(layout, wide = false) {
  assert(layout.drawer.y >= 60);
  assert(layout.panel.bottom <= layout.drawer.bottom + 1);
  assert(layout.composer.bottom <= layout.drawer.bottom + 1);
  assert(layout.drawer.bottom < layout.controls.y, 'Chat must reserve space above controls');
  assert(layout.log.height > 80 && !layout.overflow);
  if (wide) assert(layout.core.right < layout.drawer.x, 'Core and expanded chat must use separate columns');
}
try {
  await page.goto('http://127.0.0.1:8787');
  await page.getByLabel('Local pairing token').fill((await readFile('.runtime/login.token', 'utf8')).trim());
  await page.getByRole('button', { name: 'Connect local session' }).click(); await page.getByTestId('core-stage').waitFor();
  await page.evaluate(() => window.__coreCanvas = document.querySelector('[data-testid=core-stage] canvas'));
  await enter(); await alwaysReady();
  const mode = page.getByRole('switch', { name: 'Wake phrase only in immersive mode' });
  assert.equal(await mode.getAttribute('aria-checked'), 'false');
  await mode.click(); await standby();
  await say('This ordinary conversation should be ignored'); assert.equal(prompts.length, 0); await standby();
  await say('Hey Jarvis'); await listening(); assert.equal(prompts.length, 0);
  const lighting = await page.locator('.attention-frame').evaluate(node => {
    const style = getComputedStyle(node), rect = node.getBoundingClientRect();
    return { radius: parseFloat(style.borderRadius), filter: style.filter, x: rect.x, y: rect.y, width: rect.width, height: rect.height, viewportWidth: innerWidth, viewportHeight: innerHeight };
  });
  assert(lighting.radius <= 12 && lighting.filter === 'none');
  assert(lighting.x === 0 && lighting.y === 0 && lighting.width === lighting.viewportWidth && lighting.height === lighting.viewportHeight);
  await page.screenshot({ path: '/tmp/jarvis-rounded-listening-desktop.png' });
  await say('Summarize my request'); assert.equal(prompts.length, 1); await standby();
  await page.getByRole('button', { name: 'Chat', exact: true }).click();
  const desktop = await chatBounds(); bounded(desktop, true);
  const log = page.getByRole('log', { name: 'Conversation' });
  assert(await log.evaluate(node => node.scrollHeight > node.clientHeight * 3));
  await log.evaluate(node => { node.scrollTop = 0; node.dispatchEvent(new Event('scroll', { bubbles: true })); });
  await page.waitForTimeout(300); assert.equal(await log.evaluate(node => node.scrollTop), 0);
  await log.hover(); await page.mouse.wheel(0, 350); await page.waitForTimeout(300); assert(await log.evaluate(node => node.scrollTop > 0));
  assert.equal((await chatBounds()).drawer.y, desktop.drawer.y);
  await page.screenshot({ path: '/tmp/jarvis-immersive-chat-bounded.png' });
  await say('Jarvis'); await listening(); const armedAt = Date.now();
  await standby(); const silenceTimeoutMs = Date.now() - armedAt;
  assert(silenceTimeoutMs > 4000 && silenceTimeoutMs < 6500, 'Silent wake window must close after five seconds plus fade');
  await say('Jarvis'); await listening(); transcript = 'A longer request that starts within the wake window';
  const beforeLong = transcriptions;
  await page.evaluate(() => window.__vad = .08); await page.waitForTimeout(6500);
  assert.equal(await page.locator('.attention-frame').getAttribute('data-mode'), 'listening', 'Speech started in time must not be cut off at five seconds');
  await page.evaluate(() => window.__vad = 0);
  for (let i = 0; transcriptions <= beforeLong && i < 50; i++) await page.waitForTimeout(100);
  await standby(); assert.equal(prompts.length, 2);
  await say('Jarvis'); await listening(); await say(''); await standby(); assert.equal(prompts.length, 2);
  await say('Jarvis'); await listening(); await mode.click(); await alwaysReady();
  await say('An unprefixed request in always mode'); assert.equal(prompts.length, 3);
  await mode.click(); await standby();
  await page.getByRole('button', { name: 'Exit immersive mode', exact: true }).click();
  await page.reload(); await page.getByTestId('core-stage').waitFor(); await enter(); await standby();
  assert.equal(await mode.getAttribute('aria-checked'), 'true');
  await page.getByRole('button', { name: 'Chat', exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 }); await page.waitForTimeout(300);
  const mobile = await chatBounds(); bounded(mobile);
  await page.screenshot({ path: '/tmp/jarvis-rounded-listening-mobile.png' });
  await page.getByRole('button', { name: 'Mute immersive microphone', exact: true }).click();
  await page.waitForFunction(() => !document.querySelector('.attention-frame') && window.__streams.every(stream => !stream.active));
  await page.getByRole('button', { name: 'Enable immersive microphone', exact: true }).click(); await standby();
  await say('Jarvis'); await listening();
  await page.evaluate(() => { Object.defineProperty(document, 'hidden', { configurable: true, value: true }); document.dispatchEvent(new Event('visibilitychange')); });
  await page.waitForFunction(() => !document.querySelector('.attention-frame') && window.__streams.every(stream => !stream.active));
  await page.evaluate(() => { Object.defineProperty(document, 'hidden', { configurable: true, value: false }); document.dispatchEvent(new Event('visibilitychange')); }); await standby();
  await page.getByRole('button', { name: 'Exit immersive mode', exact: true }).click();
  await page.getByRole('button', { name: 'Settings', exact: true }).click(); await page.getByLabel('Reduce motion', { exact: true }).check();
  await enter(); await standby();
  await say('Jarvis'); await listening();
  assert.equal(await page.locator('.attention-frame').evaluate(node => getComputedStyle(node, '::after').animationName), 'none');
  assert.equal(errors.length, 0);
  const result = { ignoredUnprefixedSpeech: true, bothWakePhrases: true, wakeThenCommand: true, silenceTimeoutMs, longSpeechPreserved: true, emptyPhraseRearms: true, timeoutRearms: true, switchFromArmedToAlways: true, modePersisted: true, muteAndHiddenRelease: true, reducedMotion: true, lighting, desktop, mobile, errors, chatSttVadMocked: true, physicalMicrophoneVerified: false };
  await writeFile('.runtime/immersive-modes-browser-check.json', JSON.stringify(result, null, 2)); console.log(JSON.stringify(result, null, 2));
} finally { await context.close(); await browser.close(); }
