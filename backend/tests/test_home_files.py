import os
from pathlib import Path

import pytest

from app.home_files import HomeFiles, HomeFileError


@pytest.fixture
def home(tmp_path):
    root = tmp_path / 'home'
    root.mkdir()
    (root / 'Documents').mkdir()
    (root / 'Documents' / 'notes.txt').write_text('Review the draft.\n', encoding='utf-8')
    return root


def test_lists_and_reads_relative_home_files(home):
    files = HomeFiles(home)
    listing = files.list('Documents')
    assert listing['path'] == 'Documents'
    assert listing['entries'] == [{'name': 'notes.txt', 'path': 'Documents/notes.txt', 'kind': 'file', 'size': 18}]
    assert files.read('Documents/notes.txt')['text'] == 'Review the draft.\n'
    assert listing['untrusted'] is True


@pytest.mark.parametrize('path', ['/', '/etc/passwd', '../outside', 'Documents/../../outside', './Documents', 'Documents//notes.txt', 'Documents/../Documents/notes.txt', '~/.ssh/id_rsa', 'Documents/\ud800'])
def test_rejects_absolute_traversal_and_ambiguous_paths(home, path):
    with pytest.raises(HomeFileError):
        HomeFiles(home).read(path)


def test_hides_credentials_hidden_files_and_runtime_state(home):
    for path in ['.ssh/id_rsa', '.env', 'Documents/.env.local', 'Documents/passwords.txt', 'Documents/credentials.txt', 'Documents/secrets.ini', 'Documents/secret.pem', 'project/.runtime/login.token', 'project/hermes/runtime/memories/MEMORY.md', 'alternate/native/MEMORY.md']:
        entry = home / path
        entry.parent.mkdir(exist_ok=True, parents=True)
        entry.write_text('private')
    files = HomeFiles(home, denied_paths=(home / 'alternate/native',))
    for path in ['.ssh/id_rsa', '.env', 'Documents/.env.local', 'Documents/passwords.txt', 'Documents/credentials.txt', 'Documents/secrets.ini', 'Documents/secret.pem', 'project/.runtime/login.token', 'project/hermes/runtime/memories/MEMORY.md', 'alternate/native/MEMORY.md']:
        with pytest.raises(HomeFileError):
            files.read(path)
    assert [entry['name'] for entry in files.list('Documents')['entries']] == ['notes.txt']
    assert files.search('MEMORY')['entries'] == []
    assert files.search('id_rsa')['entries'] == []


def test_denies_symlinks_in_final_and_intermediate_components(home, tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'private.txt').write_text('outside secret')
    (home / 'external').symlink_to(outside, target_is_directory=True)
    (home / 'Documents' / 'linked.txt').symlink_to(outside / 'private.txt')
    files = HomeFiles(home)
    for path in ['external/private.txt', 'Documents/linked.txt']:
        with pytest.raises(HomeFileError):
            files.read(path)
    with pytest.raises(HomeFileError):
        files.list('external')
    assert files.search('private')['entries'] == []
    assert 'linked.txt' not in str(files.list('Documents'))


def test_directory_replacement_cannot_follow_a_new_symlink(home, tmp_path, monkeypatch):
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'private.txt').write_text('outside secret')
    (home / 'Documents' / 'private.txt').write_text('inside')
    original = os.open
    replaced = False

    def replace_then_open(path, flags, *args, **kwargs):
        nonlocal replaced
        if path == 'Documents' and kwargs.get('dir_fd') is not None and not replaced:
            replaced = True
            (home / 'Documents').rename(home / 'moved')
            (home / 'Documents').symlink_to(outside, target_is_directory=True)
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, 'open', replace_then_open)
    with pytest.raises(HomeFileError):
        HomeFiles(home).read('Documents/private.txt')


def test_denies_special_files_and_hardlinks(home, tmp_path):
    os.mkfifo(home / 'pipe')
    outside = tmp_path / 'private.txt'
    outside.write_text('outside secret')
    os.link(outside, home / 'alias.txt')
    files = HomeFiles(home)
    for path in ['pipe', 'alias.txt']:
        with pytest.raises(HomeFileError):
            files.read(path)
    assert files.search('pipe')['entries'] == []
    assert files.search('alias')['entries'] == []


def test_text_and_search_have_bounded_outputs(home):
    (home / 'Documents' / 'long.txt').write_text('é' * 100)
    (home / 'Documents' / 'binary.bin').write_bytes(b'\x00\x01private')
    for index in range(12):
        (home / 'Documents' / f'match-{index}.txt').write_text('match')
    files = HomeFiles(home)
    result = files.read('Documents/long.txt', max_bytes=9)
    assert result['text'] == 'é' * 4
    assert result['truncated'] is True
    result = files.search('match', limit=3)
    assert len(result['entries']) == 3 and result['truncated'] is True
    with pytest.raises(HomeFileError):
        files.read('Documents/binary.bin')


def test_search_depth_and_directory_budget_stop_scan(home):
    (home / 'Documents' / 'deep').mkdir()
    (home / 'Documents' / 'deep' / 'target.txt').write_text('deep')
    files = HomeFiles(home)
    assert files.search('target', max_depth=0)['entries'] == []
    assert files.search('target', max_depth=3)['entries'][0]['path'] == 'Documents/deep/target.txt'
    result = files.search('target', directory_budget=1)
    assert result['entries'] == [] and result['truncated'] is True


def test_unavailable_errors_do_not_leak_system_paths(home):
    with pytest.raises(HomeFileError) as error:
        HomeFiles(home).read('missing.txt')
    assert str(home) not in str(error.value)
    with pytest.raises(HomeFileError):
        HomeFiles(Path('/'))
