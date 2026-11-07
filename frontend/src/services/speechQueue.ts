type Result<T> = { ok: true; value: T } | { ok: false; error: unknown };

export async function playSpeechPhrases<T>(
  phrases: string[],
  generate: (text: string) => Promise<T>,
  play: (audio: T) => Promise<void>,
  signal: AbortSignal,
  waiting: () => void = () => {},
) {
  signal.throwIfAborted();
  if (!phrases.length) return;
  // Capture prefetch failures immediately, including while the preceding audio plays.
  const prepare = (text: string): Promise<Result<T>> =>
    Promise.resolve().then(() => {
      signal.throwIfAborted();
      return generate(text);
    }).then(value => ({ ok: true, value }), error => ({ ok: false, error }));
  let pending = prepare(phrases[0]);
  for (let index = 0; index < phrases.length; index++) {
    signal.throwIfAborted();
    waiting();
    const result = await pending;
    signal.throwIfAborted();
    if (!result.ok) throw result.error;
    const playing = play(result.value);
    if (index + 1 < phrases.length) pending = prepare(phrases[index + 1]);
    await playing;
  }
  signal.throwIfAborted();
}
