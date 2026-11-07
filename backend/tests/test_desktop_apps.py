from pathlib import Path

import pytest

from app.desktop_apps import DesktopApps, DesktopAppError
from app.permissions import ActionPolicy, ApprovalStore


@pytest.fixture
def catalog(tmp_path):
    root = tmp_path / 'applications'
    root.mkdir()
    launcher = tmp_path / 'gio'
    launcher.write_text('#!/bin/sh\nexit 91\n')
    launcher.chmod(0o700)
    (root / 'editor.desktop').write_text('[Desktop Entry]\nType=Application\nName=Notes Editor\nExec=editor %F\nTerminal=false\n')
    return DesktopApps(roots=(root,), launcher=launcher), root, launcher


def test_catalog_returns_installed_app_and_fixed_argument_free_launcher(catalog):
    apps, root, launcher = catalog
    listing = apps.list()
    row = listing['applications'][0]
    assert row['name'] == 'Notes Editor'
    assert row['desktop_id'] == 'editor.desktop'
    assert row['id'].startswith('app-')
    assert row['effect'] == 'Launch Notes Editor (editor.desktop) without file or command arguments'
    assert apps.command(row['id']) == [str(launcher), 'launch', str(root / 'editor.desktop')]
    assert str(launcher) not in str(row)
    assert listing['untrusted'] is True


def test_unknown_model_supplied_arguments_and_names_are_never_launch_targets(catalog):
    apps, _, _ = catalog
    for identifier in ['editor', 'editor.desktop', 'sh -c touch /tmp/no', '/usr/bin/editor', '../editor.desktop']:
        with pytest.raises(DesktopAppError):
            apps.command(identifier)


def test_entry_content_change_and_replacement_invalidate_approved_target(catalog):
    apps, root, _ = catalog
    identifier = apps.list()['applications'][0]['id']
    path = root / 'editor.desktop'
    path.write_text('[Desktop Entry]\nType=Application\nName=Notes Editor\nExec=different-program\n')
    with pytest.raises(DesktopAppError):
        apps.command(identifier)
    next_identifier = apps.list()['applications'][0]['id']
    content = path.read_text()
    path.unlink()
    path.write_text(content)
    with pytest.raises(DesktopAppError):
        apps.command(next_identifier)


def test_hidden_override_suppresses_system_application(catalog, tmp_path):
    apps, system_root, launcher = catalog
    user_root = tmp_path / 'user-apps'
    user_root.mkdir()
    (user_root / 'editor.desktop').write_text('[Desktop Entry]\nType=Application\nHidden=true\n')
    listing = DesktopApps(roots=(user_root, system_root), launcher=launcher).list()
    assert listing['applications'] == []


def test_filters_nonlaunchable_symlink_private_and_terminal_command_entries(catalog, tmp_path):
    apps, root, _ = catalog
    variants = {
        'hidden.desktop': 'Type=Application\nName=Hidden\nExec=hidden\nHidden=true',
        'nodisplay.desktop': 'Type=Application\nName=Hidden\nExec=hidden\nNoDisplay=true',
        'terminal.desktop': 'Type=Application\nName=Run command\nExec=run-command\nTerminal=true',
        'url.desktop': 'Type=Link\nName=Link\nURL=https://example.com',
        'missing.desktop': 'Type=Application\nName=Missing\nExec=unavailable\nTryExec=/definitely/not/installed',
        'root.desktop': 'Type=Application\nName=Root\nExec=sudo editor',
        'shell.desktop': 'Type=Application\nName=Shell command\nExec=sh -c "editor"',
        'wrapped-root.desktop': 'Type=Application\nName=Wrapped root\nExec=env DISPLAY=:0 sudo editor',
        'terminal-command.desktop': 'Type=Application\nName=Terminal command\nExec=kitty sh -c editor\nTerminal=false',
        'empty.desktop': 'Type=Application\nName=No executable',
    }
    for name, fields in variants.items():
        (root / name).write_text('[Desktop Entry]\n' + fields + '\n')
    outside = tmp_path / 'outside.desktop'
    outside.write_text('[Desktop Entry]\nType=Application\nName=Outside\nExec=outside\n')
    (root / 'linked.desktop').symlink_to(outside)
    assert [row['desktop_id'] for row in apps.list()['applications']] == ['editor.desktop']


def test_terminal_emulator_app_launches_without_accepting_a_command(catalog):
    apps, root, launcher = catalog
    (root / 'terminal-emulator.desktop').write_text('[Desktop Entry]\nType=Application\nName=Terminal\nExec=kitty\nTerminal=false\n')
    row = apps.list(query='Terminal')['applications'][0]
    assert apps.command(row['id']) == [str(launcher), 'launch', str(root / 'terminal-emulator.desktop')]


def test_missing_launcher_exposes_explicit_unavailable_catalog(catalog, tmp_path):
    _, root, _ = catalog
    result = DesktopApps(roots=(root,), launcher=tmp_path / 'not-installed').list()
    assert result['available'] is False and result['applications'] == []


def test_approval_store_is_required_and_stale_entries_cannot_execute(catalog, tmp_path):
    apps, root, launcher = catalog

    calls = []
    store = ApprovalStore(tmp_path / 'approvals.db', ActionPolicy(application_catalog=apps), executor=lambda argv: calls.append(argv) or {'ok': True})
    row = apps.list()['applications'][0]
    proposal = store.propose('launch', row['id'], row['effect'])
    assert calls == []
    assert store.resolve(proposal['id'], True)['status'] == 'executed'
    assert calls == [[str(launcher), 'launch', str(root / 'editor.desktop')]]
    with pytest.raises(ValueError):
        store.resolve(proposal['id'], True)
    pending = store.propose('launch', row['id'], row['effect'])
    (root / 'editor.desktop').write_text('[Desktop Entry]\nType=Application\nName=Changed\nExec=changed\n')
    with pytest.raises(DesktopAppError):
        store.resolve(pending['id'], True)
    assert len(calls) == 1


def test_display_names_cannot_insert_controls_and_catalog_is_bounded(catalog):
    apps, root, _ = catalog
    (root / 'unsafe.desktop').write_text('[Desktop Entry]\nType=Application\nName=Unsafe\u202eTitle\nExec=unsafe\n')
    rows = apps.list(limit=1)
    assert len(rows['applications']) == 1 and rows['truncated'] is True
    unsafe = apps.list(query='unsafe')['applications'][0]
    assert '\u202e' not in unsafe['name']


def test_directory_symlink_replacement_invalidates_catalog(catalog, tmp_path):
    apps, root, _ = catalog
    identifier = apps.list()['applications'][0]['id']
    moved = tmp_path / 'moved'
    root.rename(moved)
    root.symlink_to(moved, target_is_directory=True)
    with pytest.raises(DesktopAppError):
        apps.command(identifier)


def test_desktop_commands_do_not_inherit_agent_or_browser_credentials(monkeypatch):
    from types import SimpleNamespace
    from app.permissions import execute
    import app.permissions as permissions
    monkeypatch.setenv('API_SERVER_KEY','never-pass-to-apps')
    monkeypatch.setenv('JARVIS_PLUGIN_TOKEN','never-pass-to-apps')
    monkeypatch.setenv('DBUS_SESSION_BUS_ADDRESS','unix:path=/run/user/1000/bus')
    captured={}
    def run(argv,**kwargs):captured.update(kwargs);return SimpleNamespace(returncode=0)
    monkeypatch.setattr(permissions.subprocess,'run',run)
    assert execute(['/usr/bin/gio','launch','known.desktop'])['ok']
    assert 'API_SERVER_KEY' not in captured['env'] and 'JARVIS_PLUGIN_TOKEN' not in captured['env']
    assert captured['env']['DBUS_SESSION_BUS_ADDRESS'].startswith('unix:')
