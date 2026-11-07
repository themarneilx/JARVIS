import { useEffect, useState } from 'react';

export function ListeningFrame({ mode, reduced, pulse }: { mode: 'listening' | 'attention' | null; reduced: boolean; pulse: number }) {
  const [visible, setVisible] = useState(!document.hidden);
  const [shown, setShown] = useState(mode);
  useEffect(() => {
    if (mode) { setShown(mode); return; }
    const timer = setTimeout(() => setShown(null), reduced ? 0 : 600);
    return () => clearTimeout(timer);
  }, [mode, reduced]);
  useEffect(() => {
    const update = () => setVisible(!document.hidden);
    document.addEventListener('visibilitychange', update);
    return () => document.removeEventListener('visibilitychange', update);
  }, []);
  return visible && shown ? <div key={shown === 'attention' ? pulse : 'capture'} className={`attention-frame ${shown} ${mode ? '' : 'fading'} ${reduced ? 'still' : ''}`} data-mode={mode ?? 'fading'} aria-hidden="true" /> : null;
}
