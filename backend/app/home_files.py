from collections import deque
from contextlib import contextmanager
import os
from pathlib import Path
import stat
import unicodedata


class HomeFileError(ValueError):
    pass


_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
_PRIVATE_NAMES = frozenset({
    'credentials', 'credentials.json', 'credentials.yaml', 'credentials.yml',
    'secrets', 'secrets.json', 'secrets.yaml', 'secrets.yml', 'passwords.txt',
    'passwords.csv', 'password.txt', 'authorized_keys', 'known_hosts',
    'id_rsa', 'id_dsa', 'id_ecdsa', 'id_ed25519', 'login.token', 'plugin.token',
    'hermes.token', 'memory.md', 'user.md', 'soul.md',
})
_PRIVATE_SUFFIXES = ('.pem', '.key', '.p12', '.pfx', '.kdbx', '.keychain')
_PRIVATE_STEMS = frozenset({'credential', 'credentials', 'secret', 'secrets', 'password', 'passwords', 'apikey', 'api_key', 'api-key', 'access_token'})


def _plain_name(name: str) -> bool:
    return bool(name) and not any(unicodedata.category(char).startswith('C') for char in name)


@contextmanager
def _absolute_directory(path: Path):
    fd = os.open('/', _DIRECTORY_FLAGS)
    try:
        for part in path.parts[1:]:
            next_fd = os.open(part, _DIRECTORY_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        yield fd
    finally:
        os.close(fd)


class HomeFiles:
    """Bounded read-only access anchored to the account home, with no symlink following."""

    def __init__(self, home: Path | None = None, denied_paths=()):
        self.home = Path.home() if home is None else Path(home)
        if not self.home.is_absolute() or self.home == Path('/') or '..' in self.home.parts:
            raise HomeFileError('A dedicated home directory is required')
        project = Path(__file__).resolve().parents[2]
        denied = (*denied_paths, project / '.runtime', project / 'hermes/runtime')
        self._denied = []
        for path in denied:
            absolute = Path(path).absolute()
            try:
                relative = absolute.relative_to(self.home)
            except ValueError:
                continue
            self._denied.append(relative.parts)

    def _parts(self, path: str) -> tuple[str, ...]:
        if not isinstance(path, str) or len(path) > 1024 or '\\' in path:
            raise HomeFileError('Use a relative home path')
        if path == '':
            parts = ()
        else:
            parts = tuple(path.split('/'))
            if len(parts) > 32 or any(not _plain_name(part) or part in ('.', '..') or len(part.encode('utf-8')) > 255 for part in parts):
                raise HomeFileError('Use a relative home path')
        if not self._allowed(parts):
            raise HomeFileError('This home path is unavailable')
        return parts

    def _allowed(self, parts: tuple[str, ...]) -> bool:
        if any(not _plain_name(part) or part.startswith(('.', '~')) for part in parts):
            return False
        lowered = tuple(part.casefold() for part in parts)
        if any(part in _PRIVATE_NAMES or part.split('.')[0] in _PRIVATE_STEMS or part.endswith(_PRIVATE_SUFFIXES) for part in lowered):
            return False
        if any(lowered[index:index + 2] == ('hermes', 'runtime') for index in range(len(lowered) - 1)):
            return False
        return not any(parts[:len(denied)] == denied for denied in self._denied)

    @contextmanager
    def _directory(self, parts: tuple[str, ...]):
        try:
            with _absolute_directory(self.home) as root_fd:
                root_device = os.fstat(root_fd).st_dev
                fd = os.dup(root_fd)
                try:
                    for part in parts:
                        next_fd = os.open(part, _DIRECTORY_FLAGS, dir_fd=fd)
                        if os.fstat(next_fd).st_dev != root_device:
                            os.close(next_fd)
                            raise HomeFileError('This home path is unavailable')
                        os.close(fd)
                        fd = next_fd
                    yield fd, root_device
                finally:
                    os.close(fd)
        except OSError:
            raise HomeFileError('This home path is unavailable') from None

    def _scan(self, fd: int, parts: tuple[str, ...], device: int, budget: int):
        entries = []
        inspected = 0
        truncated = False
        with os.scandir(fd) as children:
            for child in children:
                if inspected >= budget:
                    truncated = True
                    break
                inspected += 1
                child_parts = (*parts, child.name)
                if not self._allowed(child_parts):
                    continue
                try:
                    info = os.stat(child.name, dir_fd=fd, follow_symlinks=False)
                except OSError:
                    continue
                if info.st_dev != device:
                    continue
                if stat.S_ISDIR(info.st_mode):
                    kind = 'directory'
                elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                    kind = 'file'
                else:
                    continue
                entries.append({'name': child.name, 'path': '/'.join(child_parts), 'kind': kind, 'size': info.st_size if kind == 'file' else None})
        entries.sort(key=lambda row: (row['kind'] != 'directory', row['name'].casefold(), row['name']))
        return entries, inspected, truncated

    @staticmethod
    def _limit(value, minimum: int, maximum: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise HomeFileError('Requested limit is unavailable')
        return value

    def list(self, path: str = '', limit: int = 100) -> dict:
        parts = self._parts(path)
        limit = self._limit(limit, 1, 100)
        with self._directory(parts) as (fd, device):
            entries, _, truncated = self._scan(fd, parts, device, 2000)
        return {'source': 'home_files', 'untrusted': True, 'path': path, 'entries': entries[:limit], 'truncated': truncated or len(entries) > limit}

    def search(self, query: str, path: str = '', limit: int = 40, max_depth: int = 4, directory_budget: int = 80) -> dict:
        parts = self._parts(path)
        limit = self._limit(limit, 1, 100)
        max_depth = self._limit(max_depth, 0, 5)
        directory_budget = self._limit(directory_budget, 1, 160)
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 120 or not _plain_name(query):
            raise HomeFileError('Use a bounded filename search')
        needle = query.strip().casefold()
        queue = deque([(parts, 0)])
        results = []
        visited = inspected = 0
        truncated = False
        while queue:
            if visited >= directory_budget or inspected >= 4000:
                truncated = True
                break
            current, depth = queue.popleft()
            try:
                with self._directory(current) as (fd, device):
                    entries, count, partial = self._scan(fd, current, device, 4000 - inspected)
            except HomeFileError:
                if current == parts:
                    raise
                continue
            visited += 1
            inspected += count
            truncated = truncated or partial
            for entry in entries:
                if needle in entry['name'].casefold():
                    results.append(entry)
                    if len(results) >= limit:
                        return {'source': 'home_files', 'untrusted': True, 'path': path, 'query': query, 'entries': results, 'truncated': True, 'directories_scanned': visited}
                if entry['kind'] == 'directory':
                    if depth < max_depth:
                        queue.append((tuple(entry['path'].split('/')), depth + 1))
                    else:
                        truncated = True
        return {'source': 'home_files', 'untrusted': True, 'path': path, 'query': query, 'entries': results, 'truncated': truncated, 'directories_scanned': visited}

    def read(self, path: str, max_bytes: int = 32768) -> dict:
        parts = self._parts(path)
        max_bytes = self._limit(max_bytes, 1, 65536)
        if not parts:
            raise HomeFileError('Choose a regular text file')
        try:
            with self._directory(parts[:-1]) as (parent_fd, device):
                fd = os.open(parts[-1], _FILE_FLAGS, dir_fd=parent_fd)
                try:
                    info = os.fstat(fd)
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_dev != device:
                        raise HomeFileError('Choose a regular text file')
                    data = os.read(fd, max_bytes + 1)
                finally:
                    os.close(fd)
        except OSError:
            raise HomeFileError('This home path is unavailable') from None
        truncated = len(data) > max_bytes or info.st_size > max_bytes
        clipped = data[:max_bytes]
        try:
            text = clipped.decode('utf-8')
        except UnicodeDecodeError as error:
            if truncated and error.reason == 'unexpected end of data' and error.end == len(clipped):
                text = clipped[:error.start].decode('utf-8')
            else:
                raise HomeFileError('Choose a UTF-8 text file') from None
        if any(unicodedata.category(char).startswith('C') and char not in '\n\r\t' for char in text):
            raise HomeFileError('Choose a UTF-8 text file')
        if '-----BEGIN ' in text and 'PRIVATE KEY-----' in text:
            raise HomeFileError('This home path is unavailable')
        return {'source': 'home_files', 'untrusted': True, 'path': path, 'text': text, 'size': info.st_size, 'truncated': truncated}

    def lookup(self, kind: str, path: str = '', query: str = '') -> dict:
        if kind == 'list':
            return self.list(path)
        if kind == 'search':
            return self.search(query, path)
        if kind == 'read':
            return self.read(path)
        raise HomeFileError('Unsupported home-file request')
