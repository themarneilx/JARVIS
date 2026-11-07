import { chromium } from "../frontend/node_modules/playwright-core/index.mjs";
import {
  readFile,
  writeFile,
  mkdtemp,
  copyFile,
  chmod,
  symlink,
  rm,
  mkdir,
} from "node:fs/promises";
import { spawn,execFileSync } from "node:child_process";
import { createServer } from "node:net";
import { resolve } from "node:path";
import assert from "node:assert/strict";
import { holdMicrophone } from './hold-microphone.mjs';
const browser = await chromium.connectOverCDP("http://127.0.0.1:9223");
const context = await browser.newContext({
  viewport: { width: 1512, height: 982 },
});
const page = await context.newPage();
let qaBackend, qaState;
let origin;
let qaMemoryHome;
let cleanupPromise;
function cleanup() {
  return (cleanupPromise ??= (async () => {
    try {
      await context.close();
      await browser.close();
    } finally {
      try {
        if (qaBackend && qaBackend.exitCode === null && qaBackend.signalCode === null) {
          const stopped = new Promise((done) => qaBackend.once("exit", done));
          try { process.kill(-qaBackend.pid, "SIGTERM"); } catch (error) { if (error.code !== "ESRCH") throw error; }
          await Promise.race([
            stopped,
            new Promise((done) => setTimeout(done, 5000)),
          ]);
          if (qaBackend.exitCode === null && qaBackend.signalCode === null) {
            try { process.kill(-qaBackend.pid, "SIGKILL"); } catch (error) { if (error.code !== "ESRCH") throw error; }
            await stopped;
          }
        }
      } finally {
        if (qaState) await rm(qaState, { recursive: true, force: true });
      }
    }
  })());
}
process.once("SIGINT", () => void cleanup().finally(() => process.exit(130)));
process.once("SIGTERM", () => void cleanup().finally(() => process.exit(143)));
const voiceTest = process.argv.includes("--voice");
const evidence = {
  mockedProviders: false,
  physicalMicrophoneVerified: false,
  voiceTest,
};
const errors = [];
const transcriptions = [];
page.on("response", async (response) => {
  if (response.ok() && response.url().endsWith("/api/audio/transcribe"))
    transcriptions.push(
      await response.json().catch(() => ({ error: "Invalid JSON" })),
    );
});
page.on("pageerror", (error) => errors.push(error.message));
async function deferReviews() {
  for (let i = 0; i < 5; i++) {
    await page.waitForTimeout(250);
    const close = page.locator(
      'dialog[open] button[aria-label="Review later"]',
    );
    if (await close.count()) await close.click();
  }
}
async function request(path, body) {
  return page.evaluate(
    async ({ path, body }) => {
      const { csrf } = await (await fetch("/api/auth/session")).json();
      const response = await fetch("/api" + path, {
        method: body === undefined ? "GET" : "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || response.status);
      return result;
    },
    { path, body },
  );
}
async function useSyntheticSpeech(text) {
  const artifact = await request("/audio/synthesize", { text });
  await page.evaluate(async (artifact) => {
    const buffer = await (await fetch(artifact.url)).arrayBuffer();
    navigator.mediaDevices.getUserMedia = async () => {
      const context = new AudioContext();
      await context.resume();
      const source = context.createBufferSource(),
        destination = context.createMediaStreamDestination();
      source.buffer = await context.decodeAudioData(buffer.slice(0));
      source.connect(destination);
      source.start(context.currentTime + 0.4);
      window.__qaStreams ??= [];
      window.__qaStreams.push(destination.stream);
      destination.stream
        .getTracks()
        .forEach((track) =>
          track.addEventListener("ended", () => void context.close()),
        );
      return destination.stream;
    };
  }, artifact);
  return { provider: artifact.provider, duration: artifact.duration };
}
try {
  qaState = await mkdtemp(resolve(".runtime/qa-interactions-"));
  await copyFile(".runtime/hermes.token", qaState + "/hermes.token");
  await chmod(qaState + "/hermes.token", 0o600);
  await copyFile(
    ".runtime/model-selection.json",
    qaState + "/model-selection.json",
  );
  await chmod(qaState + "/model-selection.json", 0o600);
  const runtime=JSON.parse(execFileSync('python3',['scripts/runtime.py'],{encoding:'utf8'}));
  if(process.argv.includes('--memory-ui')) {
    qaMemoryHome=qaState+'/native-memory';
    await mkdir(qaMemoryHome+'/memories',{recursive:true,mode:0o700});
    await copyFile('hermes/runtime/config.yaml',qaMemoryHome+'/config.yaml');
    await copyFile('hermes/SOUL.md',qaMemoryHome+'/SOUL.md');
    await chmod(qaMemoryHome+'/config.yaml',0o600);
    await chmod(qaMemoryHome+'/SOUL.md',0o600);
  }
  if(process.argv.includes('--information')) {
    await copyFile('.runtime/online-settings.json',qaState+'/online-settings.json');
    await chmod(qaState+'/online-settings.json',0o600);
  }
  await symlink(
    resolve(".runtime/speech-models"),
    qaState + "/speech-models",
    "dir",
  );
  const reservation = createServer();
  await new Promise((done, fail) => {
    reservation.once("error", fail);
    reservation.listen(0, "127.0.0.1", done);
  });
  const port = reservation.address().port;
  await new Promise((done) => reservation.close(done));
  origin = "http://127.0.0.1:" + port;
  qaBackend = spawn(
    resolve(".venv/bin/python"),
    [
      "-m",
      "uvicorn",
      "qa_application:create_app",
      "--factory",
      "--host",
      "127.0.0.1",
      "--port",
      String(port),
      "--no-access-log",
    ],
    {
      stdio: "ignore",
      detached: true,
      env: {
        ...process.env,
        PYTHONPATH: resolve("backend") + ":" + resolve("scripts"),
        JARVIS_STATE_DIR: qaState,
        JARVIS_PORT: String(port),
        JARVIS_ORIGINS: origin,
        HERMES_HOME: qaMemoryHome??resolve("hermes/runtime"),
        HERMES_PYTHON:runtime.python,
        HERMES_SOURCE:runtime.source,
        API_SERVER_KEY: "",
      },
    },
  );
  let ready = false;
  for (let i = 0; i < 80; i++) {
    if (qaBackend.exitCode !== null)
      throw new Error("Isolated QA backend exited before startup");
    try {
      ready = (await fetch(origin + "/api/health")).ok;
    } catch {}
    if (ready) break;
    await new Promise((done) => setTimeout(done, 200));
  }
  if (!ready) throw new Error("Isolated QA backend startup timed out");
  evidence.isolatedReviewBackend = true;
  evidence.desktopMutations="blocked by isolated QA executor";
  await page.addInitScript((autoSubmit) => {
    if (!localStorage.getItem("jarvis.preferences.v3")) localStorage.setItem(
      "jarvis.preferences.v3",
      JSON.stringify({
        voice: false,
        autoSpeak: false,
        reducedMotion: false,
        wakeWord: false,
        autoSubmit,
      }),
    );
    window.__qaPlayed = 0;
    const play = HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play = async function (...args) {
      const result = await play.apply(this, args);
      window.__qaPlayed++;
      return result;
    };
  }, process.argv.includes("--voice-controls"));
  await page.goto(origin);
  await page
    .getByLabel("Local pairing token")
    .fill((await readFile(qaState + "/login.token", "utf8")).trim());
  await page.getByRole("button", { name: "Connect local session" }).click();
  await page.getByTestId("core-stage").waitFor();
  await deferReviews();
  if (process.argv.includes('--terminal')) {
    const { checkTerminal }=await import('./terminal-browser.mjs');
    await checkTerminal(page,request,evidence);
  } else if (process.argv.includes('--memory-ui')||process.argv.includes('--home-access')||process.argv.includes('--background-wake')) {
    const { checkAccess }=await import('./access-browser.mjs');
    await checkAccess(page,request,useSyntheticSpeech,evidence,qaMemoryHome);
  } else if (process.argv.includes('--information')) {
    const { checkInformation }=await import('./information-browser.mjs');
    await checkInformation(page,request,evidence);
  } else if (process.argv.includes("--greetings")) {
    const replies=[];
    for (const [prompt,expected] of [['Hello Jarvis.','Hello, sir.'],["What's your name?",'My name is Jarvis, sir.'],['Hello Jarvis.','Hello, sir.']]) {
      await page.getByRole('textbox',{name:'Your instruction',exact:true}).fill(prompt);
      await page.getByRole('button',{name:'Send instruction',exact:true}).click();
      await page.getByRole('button',{name:'Cancel generation',exact:true}).waitFor();
      await page.getByRole('button',{name:'Send instruction',exact:true}).waitFor({timeout:120000});
      assert.equal(await page.getByRole('alert').count(),0);
      const answer=await page.locator('.message.assistant').last().locator('p').textContent();
      assert.equal(answer?.trim(),expected);
      replies.push({prompt,answer});
    }
    await page.reload();
    await page.locator('.message.assistant').last().waitFor();
    assert.equal((await page.locator('.message.assistant').last().locator('p').textContent())?.trim(),'Hello, sir.');
    evidence.greetings=replies;
    evidence.historyKeepsBriefGreeting=true;
  } else if (process.argv.includes("--voice-controls")) {
    const { checkVoiceControls } = await import("./voice-controls-browser.mjs");
    await checkVoiceControls(page,request,useSyntheticSpeech,evidence,transcriptions);
  } else if (process.argv.includes("--parakeet")) {
    const { checkParakeet } = await import("./parakeet-browser.mjs");
    await checkParakeet(page, request, useSyntheticSpeech, evidence, transcriptions);
  } else if (process.argv.includes("--speech-latency")) {
    const { checkSpeechLatency } = await import("./speech-latency-browser.mjs");
    await checkSpeechLatency(page, request, evidence);
  } else {
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  const model =
    "hf.co/HauhauCS/Gemma-4-E4B-Uncensored-HauhauCS-Aggressive:Q4_K_M";
  const catalog = await request("/models");
  if (!catalog.selected_model?.includes("gemma")) {
    await page.getByLabel("AI brain model").selectOption(model);
    await page
      .getByRole("button", { name: "Prepare 64K tag and use model" })
      .click();
    await page.waitForFunction(
      () =>
        [...document.querySelectorAll(".model-panel p code")].some((element) =>
          element.textContent.toLowerCase().includes("gemma"),
        ),
      { timeout: 120000 },
    );
  }
  evidence.brain = await request("/models");
  assert.match(evidence.brain.selected_model, /gemma/);
  assert.equal(
    evidence.brain.models.find((model) => model.selected).context_default,
    64000,
  );
  const proposal = await request("/actions", {
    kind: "volume",
    target: "30",
    effect: "QA proposal: set output volume to 30%; reject without executing.",
  });
  await page
    .getByRole("dialog")
    .filter({ hasText: proposal.effect })
    .waitFor({ timeout: 10000 });
  const review = (await request("/reviews")).find(
    (ticket) => ticket.proposal_id === proposal.id,
  );
  await page.screenshot({
    path: "/tmp/jarvis-permission-popup.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  const dialogBounds = await page.getByRole("dialog").boundingBox();
  assert.ok(dialogBounds.x >= 0 && dialogBounds.x + dialogBounds.width <= 390);
  await page.screenshot({
    path: "/tmp/jarvis-permission-mobile.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 1512, height: 982 });
  await page.getByLabel("Confirmation command").fill("reject " + review.code);
  await page
    .getByRole("button", { name: "Send confirmation", exact: true })
    .click();
  await page.getByRole("dialog").waitFor({ state: "hidden" });
  evidence.typedRejection = (await request("/actions")).find(
    (action) => action.id === proposal.id,
  ).status;
  assert.equal(evidence.typedRejection, "rejected");
  await page.screenshot({
    path: "/tmp/jarvis-model-settings.png",
    fullPage: true,
  });
  if (voiceTest) {
    const captureProposal = await request("/actions", {
      kind: "volume",
      target: "32",
      effect: "QA capture lifecycle: reject without executing.",
    });
    await page
      .getByRole("dialog")
      .filter({ hasText: captureProposal.effect })
      .waitFor({ timeout: 10000 });
    await page.evaluate(() => {
      navigator.mediaDevices.getUserMedia = async () => {
        const context = new AudioContext();
        const stream = context.createMediaStreamDestination().stream;
        window.__manualCapture = stream;
        stream
          .getTracks()
          .forEach((track) =>
            track.addEventListener("ended", () => void context.close()),
          );
        return stream;
      };
    });
    await page.getByRole('button',{name:'Hold microphone for confirmation',exact:true}).focus();
    await page.keyboard.down('Space');
    await page.waitForFunction(()=>document.querySelector('button[aria-label="Hold microphone for confirmation"]')?.getAttribute('aria-pressed')==='true');
    assert.equal(
      await page
        .getByRole("button", { name: "Read request aloud", exact: true })
        .isDisabled(),
      true,
    );
    await page.getByRole("button", { name: "Reject", exact: true }).click();
    await page.keyboard.up('Space');
    await page.getByRole("dialog").waitFor({ state: "hidden" });
    evidence.handRejectionStopsCapture = await page.evaluate(() =>
      window.__manualCapture
        .getTracks()
        .every((track) => track.readyState === "ended"),
    );
    assert.equal(evidence.handRejectionStopsCapture, true);
    await page.getByLabel("Enable voice output", { exact: true }).check();
    await page
      .getByLabel("Speak replies automatically", { exact: true })
      .check();
    const playedBeforeRequest = await page.evaluate(() => window.__qaPlayed);
    const proposal = await request("/actions", {
      kind: "volume",
      target: "35",
      effect: "QA voice proposal: reject this change without executing.",
    });
    await page
      .getByRole("dialog")
      .filter({ hasText: proposal.effect })
      .waitFor({ timeout: 10000 });
    await page.waitForFunction(
      (before) => window.__qaPlayed > before,
      playedBeforeRequest,
      { timeout: 60000 },
    );
    evidence.permissionAskedAloud = true;
    await Promise.all([
      page.waitForResponse((response) =>
        response.url().endsWith("/api/audio/cancel"),
      ),
      page.getByRole("button", { name: "Stop voice", exact: true }).click(),
    ]);
    const review = (await request("/reviews")).find(
      (ticket) => ticket.proposal_id === proposal.id,
    );
    evidence.voiceFixture = await useSyntheticSpeech(
      "Reject " + review.code.split("").join(" ") + ".",
    );
    const playedBeforeConfirmation = await page.evaluate(
      () => window.__qaPlayed,
    );
    await holdMicrophone(page,page.getByRole('button',{name:'Hold microphone for confirmation',exact:true}),(evidence.voiceFixture.duration+1)*1000);
    await page.getByRole("dialog").waitFor({ state: "hidden", timeout: 60000 });
    evidence.voiceRejection = (await request("/actions")).find(
      (action) => action.id === proposal.id,
    ).status;
    assert.equal(evidence.voiceRejection, "rejected");
    await page.waitForFunction(
      (before) => window.__qaPlayed > before,
      playedBeforeConfirmation,
      { timeout: 60000 },
    );
    await page
      .getByRole("button", { name: "Command center", exact: true })
      .click();
    await Promise.all([
      page.waitForResponse((response) =>
        response.url().endsWith("/api/audio/cancel"),
      ),
      page.getByRole("button", { name: "Stop speaking", exact: true }).click(),
    ]);
    evidence.wakeFixture = await useSyntheticSpeech(
      "Hey Jarvis, are you there?",
    );
    const playedBeforeWake = await page.evaluate(() => window.__qaPlayed);
    await page.getByRole("button", { name: "Settings", exact: true }).click();
    await page
      .getByText("Enable “Hey Jarvis” listening", { exact: true })
      .check();
    await page
      .getByRole("button", { name: "Command center", exact: true })
      .click();
    await page.waitForFunction(
      (before) => window.__qaPlayed > before,
      playedBeforeWake,
      { timeout: 240000 },
    );
    evidence.wakeReply = await page
      .locator(".message.assistant")
      .last()
      .innerText();
    evidence.wakeInput = await page.locator(".message.user").last().innerText();
    assert.match(evidence.wakeInput, /are you there/i);
    await page
      .getByRole("button", { name: "Stop speaking", exact: true })
      .click();
    await page.getByRole("button", { name: "Settings", exact: true }).click();
    await page
      .getByText("Enable “Hey Jarvis” listening", { exact: true })
      .uncheck();
    evidence.captureStopped = await page.evaluate(() =>
      window.__qaStreams.every((stream) =>
        stream.getTracks().every((track) => track.readyState === "ended"),
      ),
    );
    assert.equal(evidence.captureStopped, true);
  }
  }
  evidence.errors = errors;
  evidence.transcriptions = transcriptions;
  assert.deepEqual(errors, []);
  await writeFile(
    ".runtime/interaction-check.json",
    JSON.stringify(evidence, null, 2),
  );
  console.log(JSON.stringify(evidence, null, 2));
} catch (error) {
  await writeFile(
    ".runtime/interaction-check-failure.json",
    JSON.stringify(
      {
        evidence,
        transcriptions,
        error: String(error),
        dialog: await page
          .locator("dialog[open]")
          .innerText()
          .catch(() => null),
      },
      null,
      2,
    ),
  );
  throw error;
} finally {
  await cleanup();
}
