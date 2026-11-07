import { chromium } from '../frontend/node_modules/playwright-core/index.mjs';
import { readFile, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';

// UI/audio lifecycle fixtures, not an inference or speech-model compatibility test.
const browser = await chromium.connectOverCDP('http://127.0.0.1:9223');
const context = await browser.newContext();
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
await page.addInitScript(() => {
  localStorage.setItem('jarvis.preferences.v3', JSON.stringify({ startupSound: false, voice: true, autoSpeak: true, processingSound: true }));
  window.__cue = { sources: [], playbackChecks: [] };
  const start = AudioBufferSourceNode.prototype.start;
  const stop = AudioBufferSourceNode.prototype.stop;
  AudioBufferSourceNode.prototype.start = function(...args) {
    if (this.loop && Math.abs((this.buffer?.duration ?? 0) - .7) < .001) {
      this.__cueRecord = { stopped: false, peak: this.buffer.getChannelData(0).reduce((peak, sample) => Math.max(peak, Math.abs(sample)), 0) };
      window.__cue.sources.push(this.__cueRecord);
    }
    return start.apply(this, args);
  };
  AudioBufferSourceNode.prototype.stop = function(...args) {
    if (this.__cueRecord) this.__cueRecord.stopped = true;
    return stop.apply(this, args);
  };
  const play = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function() {
    window.__cue.playbackChecks.push(window.__cue.sources.every(source => source.stopped));
    return play.call(this);
  };
});
const wav = Buffer.alloc(44 + 24000 * 2);
wav.write('RIFF'); wav.writeUInt32LE(wav.length - 8, 4); wav.write('WAVEfmt ', 8);
wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22);
wav.writeUInt32LE(24000, 24); wav.writeUInt32LE(48000, 28); wav.writeUInt16LE(2, 32);
wav.writeUInt16LE(16, 34); wav.write('data', 36); wav.writeUInt32LE(wav.length - 44, 40);
for (let i = 0; i < 24000; i++) wav.writeInt16LE(Math.round(Math.sin(i * 2 * Math.PI * 220 / 24000) * 2000), 44 + i * 2);
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const json = (route, data) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) });
let releaseFirst;
const first = new Promise(resolve => { releaseFirst = resolve; });
let turns = 0;
await page.route('**/api/chat', async route => {
  if (++turns === 1) await first; else await delay(1000);
  await route.fulfill({ status: 200, contentType: 'text/event-stream', body: 'data: {"type":"delta","text":"The browser audio check is ready."}\n\ndata: {"type":"done"}\n\n' }).catch(() => {});
});
await page.route('**/api/audio/prepare', route => json(route, {}));
await page.route('**/api/audio/cancel', route => json(route, {}));
await page.route('**/api/audio/plan', async route => { await delay(300); await json(route, { phrases: ['The browser audio check is ready.'] }); });
await page.route('**/api/audio/synthesize', async route => { await delay(500); await json(route, { url: '/api/audio/qa-fixture.wav' }); });
await page.route('**/api/audio/qa-fixture.wav', route => route.fulfill({ status: 200, contentType: 'audio/wav', body: wav }));
const playing = () => page.waitForFunction(() => window.__cue.sources.some(source => !source.stopped));
const quiet = () => page.waitForFunction(() => window.__cue.sources.every(source => source.stopped));
try {
  await page.goto('http://127.0.0.1:8787');
  await page.getByLabel('Local pairing token').fill((await readFile('.runtime/login.token', 'utf8')).trim());
  await page.getByRole('button', { name: 'Connect local session' }).click();
  await page.getByTestId('core-stage').waitFor();
  await quiet();
  await page.getByRole('textbox', { name: 'Your instruction', exact: true }).fill('Processing cue cancellation check');
  await page.getByRole('button', { name: 'Send instruction' }).click();
  await playing();
  await page.getByRole('button', { name: 'Settings', exact: true }).click();
  await page.getByRole('checkbox', { name: 'Enable processing sound', exact: true }).uncheck();
  await quiet();
  await page.getByRole('checkbox', { name: 'Enable processing sound', exact: true }).check();
  await playing();
  await page.getByRole('button', { name: 'Command center', exact: true }).click();
  await page.getByRole('button', { name: 'Cancel generation', exact: true }).click();
  await quiet(); releaseFirst();
  await page.getByRole('textbox', { name: 'Your instruction', exact: true }).fill('Processing cue speech handoff check');
  await page.getByRole('button', { name: 'Send instruction' }).click();
  await playing();
  await page.waitForFunction(() => window.__cue.playbackChecks.length > 0);
  await quiet();
  const result = await page.evaluate(() => window.__cue);
  assert(result.sources.length >= 3);
  assert(result.sources.every(source => source.peak > .01 && source.stopped));
  assert(result.playbackChecks.every(Boolean), 'Processing cue must stop before HTML audio playback');
  assert.equal(errors.length, 0);
  const report = { ...result, toggleAndCancelStop: true, idleSilent: true, errors, processingAudioMocked: false, chatAndTtsMocked: true, physicalSpeakersVerified: false };
  await writeFile('.runtime/processing-browser-check.json', JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
} finally { releaseFirst(); await context.close(); await browser.close(); }
