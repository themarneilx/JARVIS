from collections import deque
from contextlib import contextmanager
import configparser
import hashlib
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import unicodedata


class DesktopAppError(ValueError):
    pass


_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
_FORBIDDEN_EXECUTABLES = frozenset({'sudo', 'sudoedit', 'su', 'pkexec', 'doas', 'gksu', 'gksudo', 'kdesu', 'kdesudo', 'runuser', 'sh', 'bash', 'zsh', 'dash', 'fish', 'ksh', 'csh', 'tcsh'})
_TERMINALS = frozenset({'kitty', 'alacritty', 'gnome-terminal', 'konsole', 'xterm', 'uxterm', 'urxvt', 'foot', 'footclient', 'wezterm', 'tilix', 'xfce4-terminal', 'st', 'terminator', 'ghostty', 'cool-retro-term'})


def _label(value: str, maximum: int = 80) -> str:
    return ' '.join(''.join(char for char in value if not unicodedata.category(char).startswith('C')).split())[:maximum]


@contextmanager
def _directory(path: Path):
    fd = os.open('/', _DIRECTORY_FLAGS)
    try:
        for component in path.parts[1:]:
            next_fd = os.open(component, _DIRECTORY_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        yield fd
    finally:
        os.close(fd)


def _read_entry(path: Path):
    with _directory(path.parent) as parent_fd:
        fd = os.open(path.name, _FILE_FLAGS, dir_fd=parent_fd)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > 65536:
                return None
            content = os.read(fd, 65537)
            after = os.fstat(fd)
            identity = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            if len(content) > 65536 or identity(before) != identity(after):
                return None
            return content, identity(after)
        finally:
            os.close(fd)


def _eligible_exec(value: str) -> bool:
    if not value or len(value) > 4096 or any(unicodedata.category(char).startswith('C') for char in value):
        return False
    try:
        words = shlex.split(value)
    except ValueError:
        return False
    if not words:
        return False
    if Path(words[0]).name == 'env':
        words = words[1:]
        while words and ('=' in words[0] or words[0] == '--'):
            words = words[1:]
        if not words or words[0].startswith('-'):
            return False
    executable = Path(words[0]).name
    if executable in _TERMINALS and any(word not in ('%f', '%F', '%u', '%U') for word in words[1:]):
        return False
    return executable not in _FORBIDDEN_EXECUTABLES


class DesktopApps:
    """Discover installed desktop entries; return launch argv only for an unchanged entry."""

    def __init__(self, roots=None, launcher: Path | None = None):
        self.roots = tuple(Path(root) for root in roots) if roots is not None else (
            Path.home() / '.local/share/applications',
            Path.home() / '.local/share/flatpak/exports/share/applications',
            Path('/usr/local/share/applications'),
            Path('/usr/share/applications'),
            Path('/var/lib/flatpak/exports/share/applications'),
        )
        if len(self.roots) > 8 or any(not root.is_absolute() or root == Path('/') or '..' in root.parts for root in self.roots):
            raise DesktopAppError('Installed application catalog is unavailable')
        if launcher is None:
            launcher = next((path for path in (Path('/usr/bin/gio'), Path('/bin/gio')) if path.is_file() and os.access(path, os.X_OK)), None)
        self.launcher = Path(launcher) if launcher is not None else None
        if self.launcher is not None and not self.launcher.is_absolute():
            raise DesktopAppError('Desktop launcher is unavailable')

    def _available(self):
        return self.launcher is not None and self.launcher.is_file() and os.access(self.launcher, os.X_OK)

    @staticmethod
    def _entry(path: Path, desktop_id: str):
        try:
            snapshot = _read_entry(path)
            if snapshot is None:
                return None
            content, identity = snapshot
            parser = configparser.ConfigParser(interpolation=None, strict=True)
            parser.optionxform = str
            parser.read_string(content.decode('utf-8'))
            entry = parser['Desktop Entry']
            if entry.get('Type') != 'Application' or any(entry.get(key, '').casefold() == 'true' for key in ('Hidden', 'NoDisplay', 'Terminal')):
                return None
            if not _eligible_exec(entry.get('Exec', '')):
                return None
            try_exec = entry.get('TryExec', '')
            if try_exec and (len(try_exec) > 1024 or any(char.isspace() for char in try_exec) or not shutil.which(try_exec, path=os.defpath)):
                return None
            name = _label(entry.get('Name', ''))
            if not name:
                return None
        except (OSError, UnicodeError, configparser.Error, KeyError):
            return None
        fingerprint = hashlib.sha256(str(path).encode('utf-8') + b'\0' + repr(identity).encode('ascii') + b'\0' + content).hexdigest()[:24]
        effect = f'Launch {name} ({desktop_id}) without file or command arguments'
        return {'id': 'app-' + fingerprint, 'name': name, 'desktop_id': desktop_id, 'effect': effect, '_path': path}

    def _scan(self):
        applications = []
        seen = set()
        inspected = directories = 0
        truncated = False
        for root in self.roots:
            queue = deque([(root, 0)])
            while queue:
                if directories >= 128 or inspected >= 5000:
                    truncated = True
                    break
                current, depth = queue.popleft()
                try:
                    with _directory(current) as fd:
                        directories += 1
                        names = []
                        with os.scandir(fd) as children:
                            for child in children:
                                if inspected >= 5000:
                                    truncated = True
                                    break
                                inspected += 1
                                if child.name.startswith('.') or any(unicodedata.category(char).startswith('C') for char in child.name):
                                    continue
                                try:
                                    info = os.stat(child.name, dir_fd=fd, follow_symlinks=False)
                                except OSError:
                                    continue
                                if stat.S_ISDIR(info.st_mode):
                                    if depth < 3:
                                        queue.append((current / child.name, depth + 1))
                                    else:
                                        truncated = True
                                elif stat.S_ISREG(info.st_mode) and child.name.endswith('.desktop'):
                                    names.append(child.name)
                        for name in sorted(names):
                            path = current / name
                            desktop_id = '-'.join(path.relative_to(root).parts)
                            if len(desktop_id) > 100 or desktop_id in seen:
                                continue
                            seen.add(desktop_id)
                            row = self._entry(path, desktop_id)
                            if row is not None:
                                applications.append(row)
                except OSError:
                    continue
        applications.sort(key=lambda row: (row['name'].casefold(), row['desktop_id']))
        return applications, truncated

    def list(self, query: str = '', limit: int = 100) -> dict:
        if not isinstance(query, str) or len(query) > 120 or isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 300:
            raise DesktopAppError('Use a bounded application search')
        if not self._available():
            return {'source': 'installed_desktop_entries', 'untrusted': True, 'available': False, 'applications': [], 'truncated': False, 'message': 'Desktop launcher unavailable'}
        applications, truncated = self._scan()
        needle = query.strip().casefold()
        rows = [{key: value for key, value in row.items() if not key.startswith('_')} for row in applications if not needle or needle in row['name'].casefold() or needle in row['desktop_id'].casefold()]
        return {'source': 'installed_desktop_entries', 'untrusted': True, 'available': True, 'applications': rows[:limit], 'truncated': truncated or len(rows) > limit}

    def _resolve(self, identifier: str):
        if not isinstance(identifier, str) or not re.fullmatch(r'app-[a-f0-9]{24}', identifier) or not self._available():
            raise DesktopAppError('Installed application is unavailable; refresh the catalog')
        applications, _ = self._scan()
        row = next((row for row in applications if row['id'] == identifier), None)
        if row is None:
            raise DesktopAppError('Installed application changed or is unavailable; refresh the catalog')
        return row

    def command(self, identifier: str) -> list[str]:
        row = self._resolve(identifier)
        return [str(self.launcher), 'launch', str(row['_path'])]

    def effect(self, identifier: str) -> str:
        return self._resolve(identifier)['effect']
