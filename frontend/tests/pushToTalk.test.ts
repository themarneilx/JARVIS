import { expect, test, vi } from 'vitest';
import { HoldToTalk } from '../src/services/pushToTalk';

test('one press records and its release finishes exactly once', () => {
  const start=vi.fn(), finish=vi.fn(), cancel=vi.fn();
  const hold=new HoldToTalk({start,finish,cancel});
  hold.press('pointer:7');
  hold.press('pointer:7');
  hold.release('pointer:8');
  expect(start).toHaveBeenCalledTimes(1);
  expect(finish).not.toHaveBeenCalled();
  hold.release('pointer:7');
  hold.release('pointer:7');
  expect(finish).toHaveBeenCalledTimes(1);
  expect(cancel).not.toHaveBeenCalled();
});

test('an interrupted hold cancels without submitting, then another hold works', () => {
  const start=vi.fn(), finish=vi.fn(), cancel=vi.fn();
  const hold=new HoldToTalk({start,finish,cancel});
  hold.press('key:Space');
  hold.cancel();
  hold.release('key:Space');
  expect(cancel).toHaveBeenCalledTimes(1);
  expect(finish).not.toHaveBeenCalled();
  hold.press('key:Enter');
  hold.release('key:Enter');
  expect(start).toHaveBeenCalledTimes(2);
  expect(finish).toHaveBeenCalledTimes(1);
});

test('another pointer cannot cancel or replace an active hold', () => {
  const callbacks={start:vi.fn(),finish:vi.fn(),cancel:vi.fn()};
  const hold=new HoldToTalk(callbacks);
  hold.press('pointer:1');
  hold.press('pointer:2');
  hold.cancel('pointer:2');
  expect(callbacks.start).toHaveBeenCalledTimes(1);
  expect(callbacks.cancel).not.toHaveBeenCalled();
  hold.cancel('pointer:1');
  hold.cancel();
  expect(callbacks.cancel).toHaveBeenCalledTimes(1);
});

test('the recording cap releases the gesture without cancelling transcription',()=>{
  const callbacks={start:vi.fn(),finish:vi.fn(),cancel:vi.fn()};
  const hold=new HoldToTalk(callbacks);
  hold.press('key:Space');
  hold.captureEnded();
  hold.cancel();
  hold.release('key:Space');
  expect(callbacks.cancel).not.toHaveBeenCalled();
  expect(callbacks.finish).not.toHaveBeenCalled();
  expect(hold.press('key:Enter')).toBe(true);
});
