from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from app.shortcuts import Shortcuts, ShortcutSpec, normalize_spec, next_daily


@pytest.fixture
def clock(monkeypatch):
    current = {'now': datetime(2026, 11, 6, 6, 0, tzinfo=ZoneInfo('Asia/Manila')).timestamp()}
    monkeypatch.setattr('app.shortcuts.time.time', lambda: current['now'])
    return current


@pytest.fixture
def store(tmp_path, clock):
    return Shortcuts(tmp_path/'monitoring.db')


def spec(trigger='manual', **values):
    return {'name': 'Test shortcut', 'trigger': trigger, 'message': 'Sir, it is {time}.', 'chime': False, **values}


@pytest.mark.parametrize('change', [
    {'message': '{password}'}, {'message': '{time.__class__}'}, {'message': '{time!r}'},
    {'message': '{time:>1000000}'}, {'timezone': 'Unknown/City'}, {'time': '25:00'},
    {'threshold': True}, {'threshold': 0}, {'weekdays': [True]}, {'weekdays': [7]},
    {'weather': 'yes'}, {'command': 'rm -rf ~'}, {'message': '', 'chime': False},
])
def test_shortcut_rejects_unreviewed_fields_templates_and_bad_values(change):
    with pytest.raises(ValueError): ShortcutSpec.model_validate(spec(**change))


def test_time_uses_saved_timezone_and_pins_one_time_date(clock):
    value, at = normalize_spec(spec('once', time='07:00'), 'Asia/Manila', clock['now'])
    assert value.timezone == 'Asia/Manila' and value.date == '2026-11-06'
    assert at == clock['now']+3600
    value, tomorrow = normalize_spec(spec('once', time='05:00'), 'Asia/Manila', clock['now'])
    assert value.date == '2026-11-07' and tomorrow == clock['now']+23*3600
    with pytest.raises(ValueError, match='passed'):
        normalize_spec(spec('once', time='05:00', date='2026-11-06'), now=clock['now'])


def test_daily_weekdays_and_nonexistent_dst_time(clock):
    value, at = normalize_spec(spec('daily', time='07:00', weekdays=[0]), now=clock['now'])
    assert datetime.fromtimestamp(at, ZoneInfo('Asia/Manila')).weekday() == 0
    assert next_daily(value, at) == at+7*86400
    with pytest.raises(ValueError, match='does not exist'):
        normalize_spec(spec('once', time='02:30', date='2026-03-08', timezone='America/New_York'), now=datetime(2026, 3, 7, tzinfo=ZoneInfo('UTC')).timestamp())


def test_native_proposal_is_not_active_and_duplicates_are_reviewable(store):
    first = store.propose(spec('daily', time='07:00', weather=True))
    second = store.propose(spec('daily', time='07:00', weather=True))
    assert first['id'] == second['id'] and first['status'] == 'pending'
    assert store.list() == [] and len(store.pending()) == 1
    result = store.resolve(first['id'], True)
    assert result['status'] == 'approved'
    assert store.get(result['shortcut_id'])['enabled'] is True
    assert store.inventory()['proposal_states'][first['id']]['shortcut_id'] == result['shortcut_id']
    with pytest.raises(ValueError): store.resolve(first['id'], True)


def test_rejected_or_expired_proposals_never_enable(store, clock):
    proposal = store.propose(spec())
    assert store.resolve(proposal['id'], False)['status'] == 'rejected'
    proposal = store.propose(spec(name='Different pending request'))
    clock['now'] += 601
    assert store.pending() == []
    with pytest.raises(ValueError): store.resolve(proposal['id'], True)
    assert store.list() == []


def test_once_alarm_fires_once_across_restart_and_finishes_disabled(store, clock):
    saved = store.create(spec('once', time='07:00'))
    clock['now'] = saved['next_run']
    store.tick()
    event = store.events()[0]
    restarted = Shortcuts(store.path)
    restarted.tick()
    assert len(restarted.events()) == 1
    claim = restarted.claim(event['id'], 'browser-a')
    restarted.finish(event['id'], 'browser-a', claim['claim_id'], 'delivered')
    assert restarted.get(saved['id'])['enabled'] is False


def test_late_alarm_records_missed_instead_of_playing(store, clock):
    saved = store.create(spec('once', time='07:00'))
    clock['now'] = saved['next_run']+301
    store.tick()
    assert store.events()[0]['status'] == 'missed'
    with pytest.raises(ValueError): store.claim(store.events()[0]['id'], 'browser-a')


def test_daily_does_not_replay_every_missed_day(store, clock):
    saved = store.create(spec('daily', time='07:00'))
    clock['now'] = saved['next_run']+86400*30
    store.tick()
    assert len(store.events()) == 1 and store.events()[0]['status'] == 'missed'
    assert store.get(saved['id'])['next_run'] > clock['now']


@pytest.mark.parametrize('battery', [None, {'percent': 10, 'charging': True}, {'percent': 10, 'charging': None}, {'percent': float('nan'), 'charging': False}, {'percent': '10', 'charging': False}])
def test_missing_unknown_or_charging_battery_never_fires(store, clock, battery):
    store.create(spec('battery'))
    store.tick({'battery': battery}); clock['now'] += 20; store.tick({'battery': battery})
    assert store.events() == []


def test_battery_warning_is_sustained_latched_and_durable(store, clock):
    saved = store.create(spec('battery', threshold=10))
    low = {'battery': {'percent': 10, 'charging': False}}
    store.tick(low); clock['now'] += 5; store.tick(None)
    assert store.events() == []
    clock['now'] += 5; store.tick(low)
    assert len(store.events()) == 1
    assert store.events()[0]['payload']['snapshot']['battery_percent'] == 10
    restarted = Shortcuts(store.path)
    clock['now'] += 30; restarted.tick(low)
    assert len(restarted.events()) == 1
    restarted.tick({'battery': {'percent': 14, 'charging': False}})
    clock['now'] += 20; restarted.tick(low)
    assert len(restarted.events()) == 1
    restarted.tick({'battery': {'percent': 15, 'charging': False}})
    clock['now'] += 1; restarted.tick(low); clock['now'] += 10; restarted.tick(low)
    assert len(restarted.events()) == 2 and restarted.get(saved['id'])['enabled']


def test_claims_are_owner_scoped_single_use_and_globally_serial(store, clock):
    saved = store.create(spec())
    first, second = store.run(saved['id']), store.run(saved['id'])
    claim = store.claim(first['id'], 'browser-a')
    with pytest.raises(ValueError): store.claim(first['id'], 'browser-b')
    with pytest.raises(ValueError, match='in progress'): store.claim(second['id'], 'desktop')
    with pytest.raises(ValueError): store.finish(first['id'], 'browser-b', claim['claim_id'], 'delivered')
    store.finish(first['id'], 'browser-a', claim['claim_id'], 'muted')
    with pytest.raises(ValueError): store.finish(first['id'], 'browser-a', claim['claim_id'], 'delivered')
    assert store.claim(second['id'], 'desktop')['event']['id'] == second['id']


def test_edit_disable_delete_cancel_inflight_and_old_revisions(store):
    saved = store.create(spec())
    event = store.run(saved['id']); claim = store.claim(event['id'], 'browser-a')
    saved = store.update(saved['id'], saved['revision'], spec(name='Reviewed new name'))
    assert not store.valid_event(event['id']) and store.event(event['id'])['status'] == 'cancelled'
    with pytest.raises(ValueError): store.validate_claim(event['id'], 'browser-a', claim['claim_id'])
    with pytest.raises(ValueError): store.set_enabled(saved['id'], saved['revision']-1, False)
    event = store.run(saved['id']); saved = store.set_enabled(saved['id'], saved['revision'], False)
    assert store.event(event['id'])['status'] == 'cancelled'
    manual = store.run(saved['id'])
    assert store.valid_event(manual['id'])  # Explicit Run now is allowed on a disabled schedule.
    store.delete(saved['id'], saved['revision'])
    assert not store.valid_event(manual['id']) and store.list() == []


def test_claim_interruption_does_not_auto_replay(store, clock):
    saved = store.create(spec())
    event = store.run(saved['id']); store.claim(event['id'], 'browser-a')
    clock['now'] += 301; store.tick()
    assert store.event(event['id'])['status'] == 'failed'
    with pytest.raises(ValueError): store.claim(event['id'], 'browser-b')


def test_pending_event_expiry_and_history_bound(store, clock):
    saved = store.create(spec())
    event = store.run(saved['id']); clock['now'] += 301; store.tick()
    assert store.event(event['id'])['status'] == 'missed'
    for _ in range(205):
        event = store.run(saved['id']); store.stop(event['id']); clock['now'] += 1
    store.tick()
    assert len(store.events()) == 200


def test_shortcut_settings_are_private_and_strict(store):
    assert store.path.stat().st_mode & 0o077 == 0
    assert store.settings({'voice_enabled': False}) == {'voice_enabled': False}
    assert Shortcuts(store.path).settings()['voice_enabled'] is False
    with pytest.raises(ValueError): store.settings({'voice_enabled': 'false'})
