export type AudioCommand = 'voice_mute' | 'voice_unmute' | 'microphone_mute' | 'microphone_unmute';

export function parseAudioCommand(text: string): AudioCommand | null {
  const normalized = text.normalize('NFKC').trim()
    .replace(/^(?:hey[\s,]+)?jarvis[\s,:!.]+/i, '')
    .replace(/[.!?]+$/, '').trim();
  const match = normalized.match(/^(?:please\s+)?(mute|unmute)(?:\s+(?:(?:your|the)\s+)?(voice|speech|tts|mic|microphone))?(?:\s+please)?$/i);
  if (!match) return null;
  const device = /^(mic|microphone)$/i.test(match[2] ?? '') ? 'microphone' : 'voice';
  return `${device}_${match[1].toLowerCase()}` as AudioCommand;
}
