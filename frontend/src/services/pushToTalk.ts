export class HoldToTalk {
  private owner: string | null = null;
  constructor(private readonly callbacks: {
    start: () => void;
    finish: () => void;
    cancel: () => void;
  }) {}

  press(owner: string) {
    if (this.owner !== null) return false;
    this.owner = owner;
    this.callbacks.start();
    return true;
  }
  release(owner: string) {
    if (this.owner !== owner) return;
    this.owner = null;
    this.callbacks.finish();
  }
  captureEnded() {
    this.owner = null;
  }
  cancel(owner?: string) {
    if (this.owner === null || (owner !== undefined && this.owner !== owner)) return;
    this.owner = null;
    this.callbacks.cancel();
  }
}
