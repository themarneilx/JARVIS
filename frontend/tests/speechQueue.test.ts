import { expect, test, vi } from "vitest";
import { playSpeechPhrases } from "../src/services/speechQueue";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

test("starts playback before the next synthesis finishes and prefetches only one", async () => {
  const first = deferred<void>(), second = deferred<void>();
  const nextAudio = deferred<string>();
  const generate = vi.fn(async (text: string) => text === "two" ? nextAudio.promise : text);
  const play = vi.fn((audio: string) => audio === "one" ? first.promise : audio === "two" ? second.promise : Promise.resolve());
  const done = playSpeechPhrases(["one", "two", "three"], generate, play, new AbortController().signal);
  await vi.waitFor(() => expect(play).toHaveBeenCalledWith("one"));
  expect(generate.mock.calls.map(c => c[0])).toEqual(["one", "two"]);
  nextAudio.resolve("two");
  await Promise.resolve();
  expect(play).toHaveBeenCalledTimes(1);
  first.resolve();
  await vi.waitFor(() => expect(play).toHaveBeenCalledWith("two"));
  expect(generate).toHaveBeenCalledTimes(3);
  second.resolve();
  await done;
  expect(play.mock.calls.map(c => c[0])).toEqual(["one", "two", "three"]);
});

test("cancellation never plays a late prefetched result", async () => {
  const controller = new AbortController(), playing = deferred<void>();
  const generate = vi.fn(async (text: string) => text), play = vi.fn(() => playing.promise);
  const done = playSpeechPhrases(["one", "two", "three"], generate, play, controller.signal);
  const rejected = expect(done).rejects.toHaveProperty("name", "AbortError");
  await vi.waitFor(() => expect(play).toHaveBeenCalledTimes(1));
  controller.abort();
  playing.resolve();
  await rejected;
  expect(play).toHaveBeenCalledTimes(1);
  expect(generate).toHaveBeenCalledTimes(2);
});

test("a failed prefetch is reported after the playing phrase, without overlapping", async () => {
  const playing = deferred<void>();
  const play = vi.fn(() => playing.promise);
  const done = playSpeechPhrases(["one", "two"], async (text) => {
    if (text === "two") throw new Error("Voice unavailable");
    return text;
  }, play, new AbortController().signal);
  const rejected = expect(done).rejects.toThrow("Voice unavailable");
  await vi.waitFor(() => expect(play).toHaveBeenCalledTimes(1));
  playing.resolve();
  await rejected;
  expect(play).toHaveBeenCalledTimes(1);
});

test("an already cancelled request never starts synthesis", async () => {
  const controller = new AbortController(); controller.abort();
  const generate = vi.fn(), play = vi.fn();
  await expect(playSpeechPhrases(["one"], generate, play, controller.signal)).rejects.toHaveProperty("name", "AbortError");
  expect(generate).not.toHaveBeenCalled();
});
