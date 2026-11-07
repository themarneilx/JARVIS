import { expect, test } from 'vitest';
import { parseAudioCommand } from '../src/services/audioCommands';

test.each([
  ['mute', 'voice_mute'], ['Jarvis, mute.', 'voice_mute'], ['Hey Jarvis, mute your voice please.', 'voice_mute'],
  ['unmute', 'voice_unmute'], ['please unmute your voice', 'voice_unmute'],
  ['mute mic', 'microphone_mute'], ['Jarvis, mute microphone!', 'microphone_mute'],
  ['please mute the microphone', 'microphone_mute'], ['unmute microphone', 'microphone_unmute'],
])('recognizes the local audio control %s', (text, command) => expect(parseAudioCommand(text)).toBe(command));

test.each(['mute system sounds', 'mute my speakers', 'mute the volume', 'do not mute', 'what does mute mean?', 'he said mute', 'mute and open Kitty', 'approve 1234', '"mute"'])('%s is not a standalone Jarvis audio control', text => {
  expect(parseAudioCommand(text)).toBeNull();
});
