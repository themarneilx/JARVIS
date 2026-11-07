export interface Telemetry {
  sampled_at: number;
  cpu_percent: number;
  cpu_temperature: number | null;
  cpu_temperature_source: string | null;
  ram: { used: number; total: number; percent: number };
  disk: { used: number; total: number; percent: number };
  uptime_seconds: number;
  battery: { percent: number; charging: boolean | null } | null;
  gpu: {
    name: string;
    utilization: number | null;
    temperature: number | null;
    vram_used_mb: number | null;
    vram_total_mb: number | null;
    power_w: number | null;
  } | null;
  network: { name: string; up: boolean; speed_mbps: number }[] | null;
  desktop: {
    available: boolean;
    clients: { class: string; title: string; workspace: number }[];
    focused: { class: string; title: string } | null;
    workspaces: { id: number; windows: number }[];
  };
  services:
    | { unit: string; active: string; sub: string; scope: string }[]
    | null;
  audio: { pipewire_reachable: boolean; volume: string | null };
  backend_rss: number;
  unavailable: string[];
}
export interface Place {
  id: number;
  name: string;
  country: string;
  country_code: string;
  latitude: number;
  longitude: number;
  timezone: string;
}
export interface OnlineSettings {
  version: 1;
  enabled: boolean;
  timezone: string;
  location: Place | null;
}
export interface Status {
  online?: OnlineSettings;
  agent: { connected: boolean; message?: string; safe_tools?: string[] };
  identity: { installed: boolean; matches_template: boolean };
  audio: {
    tts_checkout: boolean;
    tts_voice: string;
    stt_model: string;
    stt_provider?: "parakeet" | "faster-whisper";
    stt_device?: string;
    stt_ready?: boolean;
    device: string;
    tts_ready?: boolean;
  };
  memory_epoch: number;
  approved_services: string[];
}
export interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  at: number;
  failed?: boolean;
}
export interface Action {
  id: string;
  kind: string;
  target: string;
  effect: string;
  status: string;
  expires: number;
  result?: string;
}
export interface MemoryEntry {
  id: string;
  target: string;
  text: string;
  reason: string;
  pinned: boolean;
}
export interface MemoryProposal {
  id: string;
  action: string;
  target: string;
  content: string;
  old_text: string;
  reason: string;
}
export interface MemoryView {
  entries: MemoryEntry[];
  pending: MemoryProposal[];
  suggestions: boolean;
  limits: { user: number; memory: number };
  epoch: number;
  history: { action: string; fingerprint: string; at: number }[];
}
export interface Preferences {
  quality: "low" | "balanced" | "performance";
  reducedMotion: boolean;
  voice: boolean;
  autoSpeak: boolean;
  volume: number;
  mic: string;
  output: string;
  autoSubmit: boolean;
  wakeWord: boolean;
  backgroundWake: boolean;
  startupSound: boolean;
  processingSound: boolean;
  microphoneMuted: boolean;
  immersiveMicMode: 'always' | 'wake';
}
export interface MonitorConfig {
  enabled: boolean;
  gpu_temperature: number;
  cpu_percent: number;
  ram_percent: number;
  disk_percent: number;
  battery_percent: number;
  services: string[];
}
export interface MonitorView {
  settings: MonitorConfig;
  alerts: { id: string; at: number; message: string }[];
  routines: {
    id: string;
    name: string;
    interval: number;
    enabled: number;
    next: number;
  }[];
  reports: { id: string; at: number; payload: Record<string, unknown> }[];
}
export interface ShortcutSpec {
  name: string;
  trigger: "manual" | "once" | "daily" | "battery";
  time: string;
  date: string;
  timezone: string;
  weekdays: number[];
  threshold: number;
  message: string;
  weather: boolean;
  chime: boolean;
  delivery: "auto" | "browser" | "desktop";
}
export interface ShortcutView {
  id: string;
  revision: number;
  spec: ShortcutSpec;
  enabled: boolean;
  next_run: number | null;
  last_run: number | null;
  last_error: string;
  summary: string;
}
export interface ShortcutEvent {
  id: string;
  shortcut_id: string;
  revision: number;
  name: string;
  status: "pending" | "preparing" | "playing" | "delivered" | "cancelled" | "missed" | "failed" | "muted";
  due: number;
  created: number;
  delivery: ShortcutSpec["delivery"];
  text: string;
  sources: { title?: string; name?: string; url: string }[];
  error: string;
}
export interface ShortcutsView {
  shortcuts: ShortcutView[];
  events: ShortcutEvent[];
  capabilities: {
    desktop_audio_available: boolean;
    timezone: string;
    location_label: string;
    weather_available: boolean;
    scheduler_error?: string;
  };
  pending_count: number;
}
