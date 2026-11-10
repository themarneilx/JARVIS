from dataclasses import dataclass, field
from pathlib import Path
import os
import secrets
from urllib.parse import urlparse

from .lan import normalize_private_ipv4

ROOT = Path(__file__).resolve().parents[2]


def private_secret(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.is_symlink() or path.stat().st_mode & 0o077:
            raise ValueError(f'Unsafe permissions on {path.name}; use chmod 600')
        return path.read_text().strip()
    with os.fdopen(fd, 'w') as file:
        token = secrets.token_urlsafe(36)
        file.write(token)
    return token


def loopback_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1') or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Only loopback HTTP endpoints are permitted')
    return value.rstrip('/')


@dataclass
class Settings:
    state_dir: Path = field(default_factory=lambda: Path(os.getenv('JARVIS_STATE_DIR', ROOT / '.runtime')))
    hermes_url: str = field(default_factory=lambda: os.getenv('HERMES_API_URL', 'http://127.0.0.1:8642'))
    hermes_key: str = field(default_factory=lambda: os.getenv('API_SERVER_KEY', ''))
    hermes_home: Path = field(default_factory=lambda: Path(os.getenv('HERMES_HOME', ROOT / 'hermes/runtime')))
    hermes_python: str = field(default_factory=lambda: os.getenv('HERMES_PYTHON', ''))
    hermes_source: str = field(default_factory=lambda: os.getenv('HERMES_SOURCE', ''))
    ollama_url: str = field(default_factory=lambda: os.getenv('OLLAMA_URL', 'http://127.0.0.1:11434'))
    login_token: str = ''
    plugin_token: str = ''
    origins: tuple[str, ...] = field(default_factory=lambda: tuple(os.getenv('JARVIS_ORIGINS', 'http://127.0.0.1:3000,http://localhost:3000,http://127.0.0.1:8787,http://localhost:8787').split(',')))
    services: tuple[str, ...] = field(default_factory=lambda: tuple(x for x in os.getenv('JARVIS_APPROVED_USER_SERVICES','').split(',') if x))
    tts_repo: Path = field(default_factory=lambda: Path(os.getenv('JARVIS_TTS_REPO', str(ROOT.parent / 'JarvisLuxTTS'))).expanduser())
    tts_python: str = field(default_factory=lambda: os.getenv('JARVIS_TTS_PYTHON', str(ROOT.parent / 'JarvisLuxTTS/.venv/bin/python')))
    tts_speed: float = field(default_factory=lambda: float(os.getenv('JARVIS_TTS_SPEED','0.73')))
    tts_device: str = field(default_factory=lambda: os.getenv('JARVIS_TTS_DEVICE','cpu'))
    stt_provider: str = field(default_factory=lambda: os.getenv('JARVIS_STT_PROVIDER','parakeet'))
    stt_model: str = field(default_factory=lambda: os.getenv('JARVIS_STT_MODEL',''))
    stt_library: str = field(default_factory=lambda: os.getenv('JARVIS_STT_LIBRARY',str(ROOT / '.runtime/stt/nemo-speech-0.3.0-cpu/lib/libnemo_speech_asr_c.so')))
    port: int = field(default_factory=lambda: int(os.getenv('JARVIS_PORT','8787')))
    lan_mode: bool = field(default_factory=lambda: os.getenv('JARVIS_LAN_MODE') == '1')
    lan_host: str = field(default_factory=lambda: os.getenv('JARVIS_LAN_HOST', ''))
    lan_ca_cert: Path | None = field(default_factory=lambda: Path(os.environ['JARVIS_LAN_CA_CERT']) if os.getenv('JARVIS_LAN_CA_CERT') else None)
    lan_certfile: Path | None = field(default_factory=lambda: Path(os.environ['JARVIS_LAN_CERT']) if os.getenv('JARVIS_LAN_CERT') else None)
    lan_keyfile: Path | None = field(default_factory=lambda: Path(os.environ['JARVIS_LAN_KEY']) if os.getenv('JARVIS_LAN_KEY') else None)

    def __post_init__(self):
        if self.stt_provider not in ('parakeet','faster-whisper'):
            raise ValueError('JARVIS_STT_PROVIDER must be parakeet or faster-whisper')
        if not self.stt_model:
            self.stt_model=str(ROOT / ('.runtime/models/parakeet-tdt-0.6b-v3/parakeet-tdt-0.6b-v3.q8_0.gguf' if self.stt_provider=='parakeet' else '.runtime/models/faster-whisper-tiny.en'))
        if self.tts_device not in ('cpu','cuda'):
            raise ValueError('JARVIS_TTS_DEVICE must be cpu or cuda')
        if not 0.4<=self.tts_speed<=1.2:
            raise ValueError('JARVIS_TTS_SPEED must be between 0.4 and 1.2')
        self.hermes_url = loopback_url(self.hermes_url)
        self.ollama_url = loopback_url(self.ollama_url)
        if self.lan_mode:
            self.lan_host = normalize_private_ipv4(self.lan_host)
            self.origins = (self.lan_origin,)
        else:
            self.lan_host = ''
            for origin in self.origins:
                loopback_url(origin)
        if self.state_dir.resolve() in (Path.home().resolve(),Path('/tmp'),ROOT):
            raise ValueError('Choose a dedicated private application state subdirectory')
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.state_dir.chmod(0o700)
        self.login_token = self.login_token or private_secret(self.state_dir / 'login.token')
        self.plugin_token = self.plugin_token or private_secret(self.state_dir / 'plugin.token')
        if not self.hermes_key:
            key_file = self.state_dir / 'hermes.token'
            if key_file.exists():
                self.hermes_key = key_file.read_text().strip()

    @property
    def lan_origin(self) -> str:
        return f'https://{self.lan_host}:{self.port}'

    @property
    def bind_host(self) -> str:
        return self.lan_host if self.lan_mode else '127.0.0.1'

    @property
    def allowed_hosts(self) -> tuple[str, ...]:
        return (self.lan_host,) if self.lan_mode else ('127.0.0.1', 'localhost', '[::1]')

    @property
    def secure_cookie(self) -> bool:
        return self.lan_mode
