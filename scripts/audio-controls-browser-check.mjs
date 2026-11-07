import { chromium } from '../frontend/node_modules/playwright-core/index.mjs';
import { readFile, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';

// Synthetic capture and speech fixtures verify app controls, not audio hardware.
const browser = await chromium.connectOverCDP('http://127.0.0.1:9223');
const context = await browser.newContext();
const page = await context.newPage();
const errors = [], mutations = [];
let chats = 0, syntheses = 0, transcript = 'mute', releaseReply;
const delayedReply = new Promise(resolve => { releaseReply = resolve; });
page.on('pageerror', error => errors.push(error.message));
page.on('request', request => {
  if (request.method() === 'POST' && /\/api\/(actions|desktop|internal)\b/.test(request.url())) mutations.push(request.url());
});
await page.addInitScript(() => {
  if (!localStorage.getItem('jarvis.preferences.v3')) localStorage.setItem('jarvis.preferences.v3', JSON.stringify({ startupSound: false, processingSound: false, voice: true, autoSpeak: true, autoSubmit: false }));
  window.__streams = [];
  navigator.mediaDevices.getUserMedia = async () => {
    const audio = new AudioContext(); await audio.resume();
    const destination = audio.createMediaStreamDestination(), oscillator = audio.createOscillator(), gain = audio.createGain();
    gain.gain.value = .0001; oscillator.connect(gain).connect(destination); oscillator.start();
    window.__streams.push(destination.stream);
    return destination.stream;
  };
  const play = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function() { window.__player = this; return play.call(this); };
  const sample = AnalyserNode.prototype.getFloatTimeDomainData;
  AnalyserNode.prototype.getFloatTimeDomainData = function(values) {
    sample.call(this, values); if (window.__vadLevel) values.fill(window.__vadLevel);
  };
});
const json = (route, data) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) });
await page.route('**/api/reviews', route => json(route, []));
await page.route('**/api/audio/transcribe', route => json(route, { text: transcript }));
await page.route('**/api/audio/prepare', route => json(route, {}));
await page.route('**/api/audio/cancel', route => json(route, {}));
await page.route('**/api/audio/plan', route => json(route, { phrases: ['Speech fixture.'] }));
await page.route('**/api/audio/synthesize', route => { syntheses++; return json(route, { url: '/api/audio/qa-voice.wav' }); });
const wav = Buffer.alloc(44 + 24000 * 2 * 10);
wav.write('RIFF'); wav.writeUInt32LE(wav.length - 8, 4); wav.write('WAVEfmt ', 8); wav.writeUInt32LE(16, 16);
wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22); wav.writeUInt32LE(24000, 24); wav.writeUInt32LE(48000, 28);
wav.writeUInt16LE(2, 32); wav.writeUInt16LE(16, 34); wav.write('data', 36); wav.writeUInt32LE(wav.length - 44, 40);
for (let i = 0; i < 240000; i++) wav.writeInt16LE(Math.round(Math.sin(i * 2 * Math.PI * 220 / 24000) * 2000), 44 + i * 2);
await page.route('**/api/audio/qa-voice.wav', route => route.fulfill({ status: 200, contentType: 'audio/wav', body: wav }));
await page.route('**/api/chat', async route => {
  chats++;
  if (chats === 2) await delayedReply;
  await route.fulfill({ status: 200, contentType: 'text/event-stream', body: 'data: {"type":"delta","text":"Speech fixture."}\n\ndata: {"type":"done"}\n\n' }).catch(() => {});
});
const prefs = () => page.evaluate(() => JSON.parse(localStorage.getItem('jarvis.preferences.v3')));
const type = async text => { await page.getByLabel('Your instruction', { exact: true }).fill(text); await page.getByLabel('Your instruction', { exact: true }).press('Enter'); };
const muted = (key, value) => page.waitForFunction(({ key, value }) => JSON.parse(localStorage.getItem('jarvis.preferences.v3'))[key] === value, { key, value });
const streamsStopped = () => page.waitForFunction(() => window.__streams.every(stream => stream.getTracks().every(track => track.readyState === 'ended')));
try {
  await page.goto('http://127.0.0.1:8787');
  await page.getByLabel('Local pairing token').fill((await readFile('.runtime/login.token', 'utf8')).trim());
  await page.getByRole('button', { name: 'Connect local session' }).click(); await page.getByTestId('core-stage').waitFor();
  const initial = await prefs();
  const mic = page.getByRole('button', { name: 'Hold microphone to speak', exact: true });
  await mic.focus(); await page.keyboard.down('Space');
  await page.waitForFunction(() => document.querySelector('.phase-code')?.textContent === 'LISTENING');
  await page.waitForTimeout(400); await page.keyboard.up('Space');
  await muted('voice', false); assert.equal(chats, 0); // Local voice commands bypass edit-before-send mode and Hermes.
  await type('unmute'); await muted('voice', true);
  await page.getByRole('button', { name: 'Settings', exact: true }).click();
  await page.getByRole('checkbox', { name: 'Enable “Hey Jarvis” / “Jarvis” listening', exact: true }).check();
  await page.waitForFunction(() => window.__streams.some(stream => stream.getTracks().some(track => track.readyState === 'live')));
  await page.getByRole('checkbox', { name: 'Enable voice output', exact: true }).uncheck(); await muted('voice', false);
  assert(await page.evaluate(() => window.__streams.some(stream => stream.active)), 'Settings voice mute must preserve wake capture');
  await page.getByRole('checkbox', { name: 'Enable voice output', exact: true }).check(); await muted('voice', true);
  await page.getByRole('button', { name: 'Command center', exact: true }).click();
  transcript = 'mute mic';
  await page.evaluate(() => window.__vadLevel = .08); await page.waitForTimeout(700);
  await page.evaluate(() => window.__vadLevel = 0);
  await muted('microphoneMuted', true); await streamsStopped(); assert(await mic.isDisabled());
  assert.equal((await prefs()).voice, true);
  await page.reload(); await mic.waitFor(); assert(await mic.isDisabled());
  await page.getByRole('button', { name: 'Unmute Jarvis microphone', exact: true }).click(); await muted('microphoneMuted', false);
  await page.getByRole('button', { name: 'Settings', exact: true }).click();
  await page.getByRole('checkbox', { name: 'Enable “Hey Jarvis” / “Jarvis” listening', exact: true }).uncheck();
  await page.getByRole('button', { name: 'Command center', exact: true }).click(); await streamsStopped();
  await type('Speak a fixture reply'); await page.waitForFunction(() => window.__player && !window.__player.paused);
  await type('mute microphone'); await muted('microphoneMuted', true);
  assert(await page.evaluate(() => !window.__player.paused), 'Microphone mute must not stop reply playback');
  await type('mute'); await muted('voice', false); assert(await page.evaluate(() => window.__player.paused));
  await type('unmute voice'); await muted('voice', true);
  await type('Delayed fixture reply'); await page.getByRole('button', { name: 'Cancel generation', exact: true }).waitFor();
  await type('mute'); await muted('voice', false); const beforeReply = syntheses; releaseReply();
  await page.getByRole('button', { name: 'Send instruction', exact: true }).waitFor(); await page.waitForTimeout(400);
  assert.equal(syntheses, beforeReply, 'A response begun before mute must not start speech afterward');
  await page.getByRole('button', { name: 'Enter immersive mode', exact: true }).click();
  await streamsStopped(); await page.getByRole('button', { name: 'Enable immersive microphone', exact: true }).click();
  await muted('microphoneMuted', false); await page.waitForFunction(() => window.__streams.some(stream => stream.active));
  await page.getByRole('button', { name: 'Mute immersive microphone', exact: true }).click(); await streamsStopped();
  const final = await prefs();
  assert.equal(final.volume, initial.volume); assert.equal(final.mic, initial.mic); assert.equal(final.output, initial.output);
  assert.equal(mutations.length, 0); assert.equal(chats, 2); assert.equal(errors.length, 0);
  const result = { spokenMuteWithoutInference: true, wakeAudioCommandWithoutPrefix: true, microphoneMuteLeavesSpeechPlaying: true, captureReleased: true, mutePersists: true, onScreenUnmute: true, immersiveMute: true, delayedReplyHonorsMute: true, systemMutationRequests: mutations.length, errors, syntheticCaptureAndSpeech: true, hardwareVerified: false };
  await writeFile('.runtime/audio-controls-browser-check.json', JSON.stringify(result, null, 2)); console.log(JSON.stringify(result, null, 2));
} finally { releaseReply(); await context.close(); await browser.close(); }
