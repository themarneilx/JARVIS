import asyncio
import hashlib
import json
import os
import re
import stat
import tempfile

import httpx
import yaml

REQUIRED_CONTEXT = 64000
_MODEL_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._/-]*(?::[A-Za-z0-9._-]+)?\Z')


class ModelError(Exception):
    pass


def valid_model_name(name):
    return (isinstance(name, str) and 0 < len(name) <= 240 and
            bool(_MODEL_NAME.fullmatch(name)) and '//' not in name and
            all(part not in ('.', '..', '') for part in name.split(':')[0].split('/')))


def prepared_name(name):
    if not valid_model_name(name):
        raise ModelError('Choose an exact installed local model name.')
    label = re.sub(r'[^a-z0-9]+', '-', name.lower().split(':')[0].split('/')[-1]).strip('-')[:36]
    return f'jarvis-{label}-{hashlib.sha256(name.encode()).hexdigest()[:12]}-64k:latest'


def model_context(metadata):
    parameters = metadata.get('parameters', '')
    matches = re.findall(r'(?m)^\s*num_ctx\s+(\d+)\s*$', parameters) if isinstance(parameters, str) else []
    default = int(matches[-1]) if matches else 0
    info = metadata.get('model_info', {})
    limits = [value for key, value in info.items() if key.endswith('.context_length') and
              isinstance(value, int) and not isinstance(value, bool) and value > 0] if isinstance(info, dict) else []
    return default, max(limits, default=0)


class ModelManager:
    def __init__(self, settings, transport=None):
        self.settings = settings
        self.path = settings.state_dir / 'model-selection.json'
        self.selected_model = self._load_selected()
        self.client = httpx.AsyncClient(base_url=settings.ollama_url, timeout=8,
                                       trust_env=False, follow_redirects=False, transport=transport)
        self.lock = asyncio.Lock()

    def _load_selected(self):
        try:
            descriptor = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise ModelError('The private model selection state could not be read safely.') from exc
        with os.fdopen(descriptor) as file:
            mode = os.fstat(file.fileno())
            if not stat.S_ISREG(mode.st_mode) or mode.st_mode & 0o077 or mode.st_size > 1024:
                raise ModelError('The private model selection state has unsafe permissions or content.')
            try:
                data = json.load(file)
            except (ValueError, UnicodeError) as exc:
                raise ModelError('The private model selection state is invalid.') from exc
        if not isinstance(data, dict) or set(data) != {'version', 'model'} or data['version'] != 1 or not valid_model_name(data['model']):
            raise ModelError('The private model selection state is invalid.')
        return data['model']

    def _persist(self, name):
        if self.path.is_symlink():
            raise ModelError('The private model selection state cannot be a symbolic link.')
        descriptor, temporary = tempfile.mkstemp(prefix='.model-selection-', dir=self.path.parent)
        try:
            with os.fdopen(descriptor, 'w') as file:
                json.dump({'version': 1, 'model': name}, file)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        self.selected_model = name

    async def close(self):
        await self.client.aclose()

    async def _request(self, method, path, **kwargs):
        try:
            response = await self.client.request(method, path, **kwargs)
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict) or result.get('error'):
                raise ValueError('Unexpected Ollama response')
            return result
        except (httpx.HTTPError, ValueError) as exc:
            raise ModelError('The local Ollama model service is unavailable or returned an unsupported response. No model was downloaded.') from exc

    async def _tags(self):
        response = await self._request('GET', '/api/tags')
        models = response.get('models')
        if not isinstance(models, list) or len(models) > 512:
            raise ModelError('The local model inventory returned an unsupported response.')
        return {row['name']: row for row in models if isinstance(row, dict) and valid_model_name(row.get('name'))}

    async def _inspect(self, name, tag):
        metadata = await self._request('POST', '/api/show', json={'model': name})
        context, limit = model_context(metadata)
        capabilities = metadata.get('capabilities', [])
        tools = isinstance(capabilities, list) and 'tools' in capabilities
        remote = any(source.get(key) for source in (tag, metadata) for key in ('remote_host', 'remote_model'))
        details = metadata.get('details', {})
        details = details if isinstance(details, dict) else {}
        if remote:
            reason = 'Remote model tags are unavailable in this local workspace.'
        elif not tools:
            reason = 'Ollama does not advertise tool support for this model.'
        elif limit < REQUIRED_CONTEXT:
            reason = 'The model does not advertise a context limit of at least 64,000 tokens.'
        elif context < REQUIRED_CONTEXT:
            reason = 'A separate local tag with a 64,000-token default is required.'
        else:
            reason = None
        ready = reason is None
        return {'name': name, 'size_bytes': tag.get('size', 0),
                'parameter_size': details.get('parameter_size', ''), 'quantization': details.get('quantization_level', ''),
                'context_limit': limit, 'context_default': context, 'supports_tools': tools,
                'ready': ready, 'can_prepare': not remote and tools and limit >= REQUIRED_CONTEXT and not ready,
                'prepare_model': prepared_name(name), 'reason': reason, 'runtime_verified': False,
                'selected': name == self.selected_model}

    def _default_model(self):
        try:
            profile = yaml.safe_load((self.settings.hermes_home / 'config.yaml').read_text())
            name = profile['model']['default']
            return name if valid_model_name(name) else None
        except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError):
            return None

    async def catalog(self):
        tags = await self._tags()
        semaphore = asyncio.Semaphore(4)
        async def inspect(name, tag):
            async with semaphore:
                return await self._inspect(name, tag)
        rows = await asyncio.gather(*(inspect(name, tag) for name, tag in sorted(tags.items())))
        selected = self.selected_model or self._default_model()
        for row in rows:
            row['selected'] = row['name'] == selected
        return {'selected_model': selected, 'required_context': REQUIRED_CONTEXT, 'models': rows}

    async def _installed(self, name):
        if not valid_model_name(name):
            raise ModelError('Choose an exact installed local model name.')
        tags = await self._tags()
        if name not in tags:
            raise ModelError('The selected model is not installed locally. This action never downloads models.')
        return tags, await self._inspect(name, tags[name])

    async def select(self, name):
        async with self.lock:
            _, row = await self._installed(name)
            if not row['ready']:
                raise ModelError(row['reason'])
            try:
                self._persist(name)
            except OSError as exc:
                raise ModelError('The private model selection could not be saved.') from exc
            row['selected'] = True
            return row

    async def prepare(self, name):
        async with self.lock:
            tags, source = await self._installed(name)
            if source['ready']:
                return source
            if not source['can_prepare']:
                raise ModelError(source['reason'])
            alias = prepared_name(name)
            if alias in tags:
                row = await self._inspect(alias, tags[alias])
                if not row['ready']:
                    raise ModelError('The separate model tag already exists with an unsupported configuration; it was not overwritten.')
                return row
            await self._request('POST', '/api/create', json={'model': alias, 'from': name,
                                'parameters': {'num_ctx': REQUIRED_CONTEXT}, 'stream': False}, timeout=120)
            _, row = await self._installed(alias)
            if not row['ready']:
                raise ModelError('The separate tag was created but its model metadata did not pass the local context and tool checks.')
            return row
