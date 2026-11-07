import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { HoldToTalk } from "../services/pushToTalk";

export function PushToTalkButton({ start, finish, cancel, disabled=false, recording, label, className="", children }: {
  start: () => void;
  finish: () => void;
  cancel: () => void;
  disabled?: boolean;
  recording: boolean;
  label: string;
  className?: string;
  children: ReactNode;
}) {
  const callbacks=useRef({start,finish,cancel});
  callbacks.current={start,finish,cancel};
  const [hold]=useState(()=>new HoldToTalk({
    start:()=>callbacks.current.start(),
    finish:()=>callbacks.current.finish(),
    cancel:()=>callbacks.current.cancel(),
  }));
  useEffect(()=>{
    const cancel=()=>hold.cancel();
    const hidden=()=>{if(document.hidden)cancel();};
    window.addEventListener("blur",cancel);
    window.addEventListener("pagehide",cancel);
    document.addEventListener("visibilitychange",hidden);
    return ()=>{
      window.removeEventListener("blur",cancel);
      window.removeEventListener("pagehide",cancel);
      document.removeEventListener("visibilitychange",hidden);
      hold.cancel();
    };
  },[hold]);
  const wasRecording=useRef(recording);
  useEffect(()=>{
    if(wasRecording.current&&!recording)hold.captureEnded();
    wasRecording.current=recording;
  },[recording,hold]);
  useEffect(()=>{if(disabled)hold.cancel();},[disabled,hold]);
  return <button
    type="button"
    className={`push-to-talk ${className}`}
    disabled={disabled}
    aria-label={label}
    aria-pressed={recording}
    title="Hold to speak; release to transcribe. Space or Enter works while focused."
    onPointerDown={e=>{
      if(e.button!==0||!e.isPrimary||disabled)return;
      e.preventDefault();
      e.currentTarget.focus({preventScroll:true});
      if(hold.press(`pointer:${e.pointerId}`))e.currentTarget.setPointerCapture(e.pointerId);
    }}
    onPointerUp={e=>{
      e.preventDefault();
      hold.release(`pointer:${e.pointerId}`);
      if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);
    }}
    onPointerCancel={e=>hold.cancel(`pointer:${e.pointerId}`)}
    onLostPointerCapture={e=>hold.cancel(`pointer:${e.pointerId}`)}
    onKeyDown={e=>{
      if(e.code!=="Space"&&e.code!=="Enter")return;
      e.preventDefault();
      if(!e.repeat&&!disabled)hold.press(`key:${e.code}`);
    }}
    onKeyUp={e=>{
      if(e.code!=="Space"&&e.code!=="Enter")return;
      e.preventDefault();
      hold.release(`key:${e.code}`);
    }}
    onBlur={()=>hold.cancel()}
    onContextMenu={e=>e.preventDefault()}
    onClick={e=>e.preventDefault()}
  >{children}</button>;
}
