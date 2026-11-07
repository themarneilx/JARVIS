class AudioBus {
  context: AudioContext | null = null;
  analyser: AnalyserNode | null = null;
  data: Uint8Array<ArrayBuffer> | null = null;
  source: AudioNode | null = null;
  private frequencies: Uint8Array<ArrayBuffer> | null = null;
  private playbackListeners = new Set<() => void>();
  beforePlayback(listener: () => void) {
    this.playbackListeners.add(listener);
    return () => { this.playbackListeners.delete(listener); };
  }
  private ensure() {
    if (!this.context || this.context.state === "closed")
      this.context = new AudioContext();
    if (this.context.state === "suspended") void this.context.resume();
    this.analyser = this.context.createAnalyser();
    this.analyser.fftSize = 256;
    this.analyser.smoothingTimeConstant = 0.75;
    this.data = new Uint8Array(this.analyser.fftSize);
    this.frequencies = new Uint8Array(this.analyser.frequencyBinCount);
    return this.context;
  }
  microphone(stream: MediaStream) {
    this.detach();
    const ctx = this.ensure();
    this.source = ctx.createMediaStreamSource(stream);
    this.source.connect(this.analyser!);
  }
  playback(element: HTMLAudioElement) {
    for (const listener of this.playbackListeners) listener();
    this.detach();
    const ctx = this.ensure();
    this.source = ctx.createMediaElementSource(element);
    this.source.connect(this.analyser!);
    this.analyser!.connect(ctx.destination);
  }
  amplitude() {
    if (!this.analyser || !this.data) return 0;
    this.analyser.getByteTimeDomainData(this.data);
    let sum = 0;
    for (const v of this.data) {
      const n = (v - 128) / 128;
      sum += n * n;
    }
    return Math.min(1, Math.sqrt(sum / this.data.length) * 4);
  }
  waveform() {
    if (!this.analyser || !this.data) return null;
    this.analyser.getByteTimeDomainData(this.data);
    return this.data;
  }
  spectrum() {
    if (!this.analyser || !this.frequencies) return null;
    this.analyser.getByteFrequencyData(this.frequencies);
    return this.frequencies;
  }
  detach() {
    this.source?.disconnect();
    this.analyser?.disconnect();
    this.source = null;
    this.analyser = null;
    this.data = null;
    this.frequencies = null;
  }
}
export const audioBus = new AudioBus();
