import assert from 'node:assert/strict';

export async function checkSpeechLatency(page, request, evidence) {
  const generated = [];
  const requests = new Map();
  page.on('request', (req) => {
    if (req.url().endsWith('/api/audio/synthesize'))
      requests.set(req, { requestedAt: Date.now(), characters: req.postDataJSON().text.length });
  });
  page.on('response', async (response) => {
    const request = requests.get(response.request());
    if (request && response.ok()) {
      const artifact = await response.json();
      generated.push({ ...request, readyAt: Date.now(), duration: artifact.duration, provider: artifact.provider, device: artifact.device });
    }
  });
  const instrument = () => {
    const active = new Set();
    window.__speechLatency = { plays: [], ended: [], maxOverlap: 0, maxRms: 0, maxFrequency: 0 };
    const observer = new MutationObserver(() => {
      if (document.querySelector('button[aria-label="Cancel generation"]')) window.__speechLatency.chatStarted = true;
      if (window.__speechLatency.chatStarted && !window.__speechLatency.textReadyAt && document.querySelector('button[aria-label="Send instruction"]')) window.__speechLatency.textReadyAt = Date.now();
    });
    observer.observe(document, { subtree: true, childList: true, attributes: true });
    const play = HTMLMediaElement.prototype.play, pause = HTMLMediaElement.prototype.pause;
    HTMLMediaElement.prototype.play = async function (...args) {
      await play.apply(this, args);
      active.add(this);
      window.__speechLatency.maxOverlap = Math.max(window.__speechLatency.maxOverlap, active.size);
      window.__speechLatency.plays.push(Date.now());
      this.addEventListener('ended', () => {
        active.delete(this);
        window.__speechLatency.ended.push(Date.now());
      }, { once: true });
    };
    HTMLMediaElement.prototype.pause = function (...args) {
      active.delete(this);
      return pause.apply(this, args);
    };
    const analyser = AnalyserNode.prototype.getByteTimeDomainData;
    AnalyserNode.prototype.getByteTimeDomainData = function (array) {
      analyser.call(this, array);
      let sum = 0;
      for (const n of array) sum += ((n - 128) / 128) ** 2;
      window.__speechLatency.maxRms = Math.max(window.__speechLatency.maxRms, Math.sqrt(sum / array.length));
    };
    const spectrum = AnalyserNode.prototype.getByteFrequencyData;
    AnalyserNode.prototype.getByteFrequencyData = function (array) {
      spectrum.call(this, array);
      window.__speechLatency.maxFrequency = Math.max(window.__speechLatency.maxFrequency, ...array);
    };
  };
  await page.addInitScript(instrument);
  await page.evaluate(instrument);
  await page.getByRole('button', { name: 'Settings', exact: true }).click();
  const warming = page.waitForResponse(r => r.url().endsWith('/api/audio/prepare') && r.ok(), { timeout: 90000 });
  const preparationStart = Date.now();
  await page.getByLabel('Enable voice output', { exact: true }).check();
  await page.getByLabel('Speak replies automatically', { exact: true }).check();
  await warming;
  evidence.preparationMs = Date.now() - preparationStart;
  assert.equal((await request('/audio/settings')).device, 'cpu');
  await page.getByLabel('Speech processing device', { exact: true }).selectOption('cuda');
  await page.getByRole('status').filter({ hasText: 'NVIDIA GPU · Voice ready' }).waitFor({ timeout: 90000 });
  assert.equal((await request('/audio/settings')).device, 'cuda');
  await page.reload();
  await page.getByTestId('core-stage').waitFor();
  await page.getByRole('button', { name: 'Settings', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('select[aria-label="Speech processing device"]')?.value === 'cuda');
  assert.equal(await page.getByLabel('Speech processing device', { exact: true }).inputValue(), 'cuda');
  evidence.deviceSelectionPersists = true;
  evidence.brain = (await request('/models')).selected_model;
  await page.getByRole('button', { name: 'Command center', exact: true }).click();
  const text = 'Good evening, sir. I can help you plan your work and discuss the details at a comfortable pace. Please tell me what you would like to work on, and I will keep the explanation clear and concise. We can go through a question one step at a time whenever you are ready.';
  await page.getByRole('textbox', { name: 'Your instruction', exact: true }).fill('Repeat the following text verbatim, without tools, introduction or additional text: ' + text);
  await page.getByRole('button', { name: 'Send instruction', exact: true }).click();
  await page.waitForFunction(() => window.__speechLatency.plays.length > 0, null, { timeout: 180000 });
  await page.waitForFunction(() => window.__speechLatency.ended.length > 0 && document.querySelector('.phase-code')?.textContent === 'IDLE', null, { timeout: 90000 });
  const chatPlayback = await page.evaluate(() => window.__speechLatency);
  assert(chatPlayback.textReadyAt && chatPlayback.plays[0] >= chatPlayback.textReadyAt, 'Only the final successful response may be spoken');
  evidence.automaticSpeech = true;
  evidence.firstAudioAfterTextMs = chatPlayback.plays[0] - chatPlayback.textReadyAt;
  evidence.firstAudioAfterSynthesisRequestMs = chatPlayback.plays[0] - generated[0].requestedAt;
  const chatCount = generated.length;
  await page.getByRole('button', { name: 'Settings', exact: true }).click();
  await page.getByRole('button', { name: 'Test voice', exact: true }).click();
  await page.getByRole('button', { name: 'Command center', exact: true }).click();
  await page.waitForFunction(count => window.__speechLatency.ended.length >= count + 2 && document.querySelector('.phase-code')?.textContent === 'IDLE', chatPlayback.ended.length, { timeout: 90000 });
  const playback = await page.evaluate(() => window.__speechLatency);
  const testAudio = generated.slice(chatCount);
  assert.equal(playback.maxOverlap, 1);
  assert(playback.maxRms > .005 && playback.maxFrequency > 0, 'Real playback must drive the analyser');
  assert(testAudio.length > 1, 'The voice test must use phrase playback');
  assert(generated.every(g => g.device === 'cuda'), 'All phrases must use the chosen GPU');
  assert(testAudio[1].requestedAt < playback.ended[chatPlayback.ended.length], 'Next phrase must be generated during playback');
  assert(testAudio[1].readyAt > playback.plays[chatPlayback.plays.length], 'First playback must precede completion of the next phrase');
  evidence.phraseSource = 'Settings Test voice sample; the real native chat reply is measured separately';
  evidence.playback = playback;
  evidence.generated = [...generated];
  const before = playback.plays.length;
  await page.getByRole('button', { name: 'Settings', exact: true }).click();
  await page.getByRole('button', { name: 'Test voice', exact: true }).click();
  await page.getByRole('button', { name: 'Command center', exact: true }).click();
  await page.waitForFunction(count => window.__speechLatency.plays.length > count, before, { timeout: 90000 });
  await page.getByRole('button', { name: 'Stop speaking', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('.phase-code')?.textContent === 'IDLE');
  const stoppedCount = await page.evaluate(() => window.__speechLatency.plays.length);
  await page.waitForTimeout(4500);
  assert.equal(await page.evaluate(() => window.__speechLatency.plays.length), stoppedCount);
  evidence.replayAndStop = true;
  evidence.latePlaybackAfterStop = false;
  await page.getByRole('button', { name: 'Settings', exact: true }).click();
  await page.getByLabel('Speech processing device', { exact: true }).selectOption('cpu');
  await page.getByRole('status').filter({ hasText: 'CPU · Voice ready' }).waitFor({ timeout: 90000 });
  assert.equal((await request('/audio/settings')).device, 'cpu');
  evidence.switchedBackToCPU = true;
  evidence.browserPlugin = 'Browser plugin not available; regular Playwright with an isolated QA backend and temporary loopback CDP';
  evidence.physicalSpeakersVerified = false;
  assert.match(await page.title(), /J\.A\.R\.V\.I\.S\./);
  await page.screenshot({ path: '/tmp/jarvis-speech-latency.png', fullPage: false });
}
