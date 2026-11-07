import { expect, test, vi } from 'vitest';
import { handleWakeCommand } from '../src/services/wakeWord';

test('a bare wake phrase acknowledges attention without submitting a model prompt', () => {
  const acknowledge=vi.fn(), submit=vi.fn();
  handleWakeCommand('',acknowledge,submit);
  expect(acknowledge).toHaveBeenCalledExactlyOnceWith('At your service, sir.');
  expect(submit).not.toHaveBeenCalled();
});

test('a real wake command and a spoken confirmation follow normal submission', () => {
  const acknowledge=vi.fn(), submit=vi.fn();
  handleWakeCommand('Check the GPU.',acknowledge,submit);
  handleWakeCommand('approve 7246',acknowledge,submit);
  expect(acknowledge).not.toHaveBeenCalled();
  expect(submit.mock.calls).toEqual([['Check the GPU.'],['approve 7246']]);
});
