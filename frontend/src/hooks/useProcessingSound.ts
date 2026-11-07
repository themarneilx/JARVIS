import { useEffect, useRef } from 'react';
import { audioBus } from '../services/audioBus';

export function useProcessingSound(active: boolean, enabled: boolean, volume: number, output: string) {
  const context = useRef<AudioContext | null>(null);
  const buffer = useRef<AudioBuffer | null>(null);
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let source: AudioBufferSourceNode | null = null;
    let gain: GainNode | null = null;
    let starting = false;
    let playbackStarting = false;
    const request = new AbortController();
    const stop = (immediate = false) => {
      if (!source || !gain || !context.current) return;
      const oldSource = source, oldGain = gain, now = context.current.currentTime;
      source = null; gain = null;
      if (immediate) {
        oldGain.disconnect(); oldSource.stop(); oldSource.disconnect();
        return;
      }
      oldGain.gain.cancelScheduledValues(now);
      oldGain.gain.setTargetAtTime(0, now, .008);
      oldSource.stop(now + .035);
      oldSource.onended = () => { oldSource.disconnect(); oldGain.disconnect(); };
    };
    const start = async () => {
      if (cancelled || playbackStarting || document.hidden || starting || source) return;
      starting = true;
      try {
        const audio = context.current ??= new AudioContext();
        // A click also unlocks future voice-triggered requests in autoplay-restricted browsers.
        await audio.resume();
        if (cancelled || playbackStarting || !active || document.hidden) return;
        const routed = audio as AudioContext & { setSinkId?: (id: string) => Promise<void> };
        if (routed.setSinkId) await routed.setSinkId(output || '').catch(() => {});
        if (cancelled || playbackStarting || document.hidden) return;
        if (!buffer.current) {
          const response = await fetch('/api/audio/processing?clip=1-1.7', { credentials: 'same-origin', signal: request.signal });
          if (!response.ok) return;
          const decoded = await audio.decodeAudioData(await response.arrayBuffer());
          if (cancelled || playbackStarting || document.hidden) return;
          buffer.current = decoded;
        }
        source = audio.createBufferSource();
        source.buffer = buffer.current;
        source.loop = true;
        source.loopEnd = buffer.current.duration;
        gain = audio.createGain();
        gain.gain.setValueAtTime(0, audio.currentTime);
        gain.gain.linearRampToValueAtTime(Math.max(0, Math.min(1, volume)) * .32, audio.currentTime + .04);
        source.connect(gain).connect(audio.destination);
        source.start();
      } catch { /* Autoplay or unavailable output must not interrupt text interaction. */ }
      finally { starting = false; }
    };
    const visibility = () => { if (document.hidden) stop(); else if (active) void start(); };
    const unsubscribe = audioBus.beforePlayback(() => { playbackStarting = true; stop(true); });
    const gesture = () => { void start(); };
    window.addEventListener('pointerdown', gesture);
    window.addEventListener('keydown', gesture);
    document.addEventListener('visibilitychange', visibility);
    if (active) void start();
    return () => {
      cancelled = true;
      request.abort();
      stop();
      unsubscribe();
      window.removeEventListener('pointerdown', gesture);
      window.removeEventListener('keydown', gesture);
      document.removeEventListener('visibilitychange', visibility);
    };
  }, [active, enabled, volume, output]);
  useEffect(() => () => { void context.current?.close().catch(() => {}); context.current = null; buffer.current = null; }, []);
}
