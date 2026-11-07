import json
import pytest
from app.terminal import DesktopAccess
from app.permissions import ActionPolicy, ApprovalStore


@pytest.fixture
def access(tmp_path):
    home=tmp_path/'home';home.mkdir()
    programs=tmp_path/'bin';programs.mkdir()
    for name in ('kitty','fastfetch','printf'):
        item=programs/name;item.write_text('#!/bin/false\n');item.chmod(0o755)
    return DesktopAccess(tmp_path/'desktop.db',home=home,bin_dir=programs)


def test_fixed_kitty_command_and_scoped_preauthorization(access,tmp_path):
    calls=[]
    store=ApprovalStore(tmp_path/'actions.db',ActionPolicy(terminal_catalog=access),executor=lambda argv:calls.append(argv) or {'ok':True})
    recipe=access.catalog()['commands'][0]
    proposal=access.request(store,'terminal',recipe['id'])
    assert proposal['status']=='pending' and not calls
    access.configure(False)
    result=access.request(store,'terminal',recipe['id'])
    assert result['status']=='executed' and result['authorization']=='desktop_setting'
    assert calls[0]==[str(access.bin_dir/'kitty'),'--detach','--session','none','--hold','--directory',str(access.home),'--',str(access.bin_dir/'fastfetch')]
    assert next(a for a in store.list() if a['id']==proposal['id'])['status']=='pending'
    with pytest.raises(ValueError):store.resolve(result['id'],True)
    assert not access.auto_allowed('service_restart')
    access.configure(True)
    assert access.request(store,'terminal',recipe['id'])['status']=='pending'


def test_saved_commands_are_exact_browser_authored_and_durable(access):
    item=access.add('Show greeting',"printf '%s\\n' 'Hello sir'",'')
    assert access.command(item['id'])[-3:]==[str(access.bin_dir/'printf'),'%s\\n','Hello sir']
    other=DesktopAccess(access.path,home=access.home,bin_dir=access.bin_dir)
    assert other.command(item['id'])==access.command(item['id'])
    access.remove(item['id'])
    with pytest.raises(ValueError):other.command(item['id'])


@pytest.mark.parametrize('command',['sudo fastfetch','bash -c fastfetch','fastfetch; touch x','fastfetch && printf hi','fastfetch > output','fastfetch $(id)','fastfetch\nfastfetch','../fastfetch','/tmp/fastfetch'])
def test_shell_and_privilege_escalation_are_refused(access,command):
    with pytest.raises(ValueError):access.add('Bad command',command,'')


def test_working_directory_and_stale_program_are_checked(access,tmp_path):
    for cwd in ('/etc','../outside','.ssh'):
        with pytest.raises(ValueError):access.add('Bad path','fastfetch',cwd)
    (access.home/'link').symlink_to(tmp_path,target_is_directory=True)
    with pytest.raises(ValueError):access.add('Linked path','fastfetch','link')
    item=access.catalog()['commands'][0]
    (access.bin_dir/'fastfetch').write_text('changed')
    with pytest.raises(ValueError):access.command(item['id'])


def test_non_boolean_consent_is_rejected_and_policy_persists(access):
    for value in ('false',0,None):
        with pytest.raises(ValueError):access.configure(value)
    access.configure(False)
    assert not DesktopAccess(access.path,home=access.home,bin_dir=access.bin_dir).view()['ask_before_launch']


def test_removed_defaults_stay_removed_after_restart(access):
    for item in access.catalog()['commands']:access.remove(item['id'])
    assert not DesktopAccess(access.path,home=access.home,bin_dir=access.bin_dir).catalog()['commands']


def test_remove_then_readd_never_revives_old_approval(access,tmp_path):
    calls=[]
    store=ApprovalStore(tmp_path/'actions.db',ActionPolicy(terminal_catalog=access),executor=lambda argv:calls.append(argv) or {'ok':True})
    item=access.catalog()['commands'][0]
    proposal=access.request(store,'terminal',item['id'])
    access.remove(item['id'])
    replacement=access.add(item['name'],item['command'],item['cwd'])
    assert replacement['id']!=item['id']
    with pytest.raises(ValueError):store.resolve(proposal['id'],True)
    assert not calls
    assert store.resolve(proposal['id'],False)['status']=='rejected'


def test_missing_kitty_does_not_break_text_backend(tmp_path):
    home=tmp_path/'home';home.mkdir()
    programs=tmp_path/'bin';programs.mkdir()
    (programs/'fastfetch').touch()
    assert DesktopAccess(tmp_path/'desktop.db',home=home,bin_dir=programs).catalog()['commands']==[]


def test_launch_feedback_uses_real_terminal_receipts():
    from app.application_chat import launch_feedback,terminal_request
    assert terminal_request('can you open up a terminal emulator and run fastfetch')
    action={'id':'review','kind':'terminal','target':'cmd-fixture','effect':'Run fastfetch in Kitty','expires':123,'status':'executed'}
    rows=[{'role':'user','content':'Run fastfetch in Kitty'},{'role':'tool','tool_name':'jarvis_run_terminal','content':json.dumps(action)}]
    assert 'Kitty' in launch_feedback(rows,[action]) and 'completed' not in launch_feedback(rows,[action])
    assert "haven't" in launch_feedback(rows,[])


def test_bare_application_receipt_does_not_satisfy_run_request():
    from app.application_chat import launch_feedback
    action={'id':'review','kind':'launch','target':'app-fixture','effect':'Open Kitty','expires':123,'status':'executed'}
    rows=[{'role':'user','content':'Open Kitty and run fastfetch'},{'role':'tool','tool_name':'jarvis_launch_application','content':json.dumps(action)}]
    assert "haven't" in launch_feedback(rows,[action])
