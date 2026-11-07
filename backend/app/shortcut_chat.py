import json
import re

from .memory import redact


def alarm_request(text):
    text=re.sub(r'"[^"\n]*"|“[^”\n]*”|`[^`]*`','',text)
    if re.search(r'\b(?:how (?:do|can|would) (?:i|you)|how to|what is|what are|translate|explain)\b',text,re.I):return False
    return bool(re.search(
        r'\b(?:show|list|review|view)\b.{0,35}\b(?:my |saved |pending )?(?:shortcuts|alarms|reminders|routines)\b|'
        r'\bwake me(?: up)?\b|'
        r'\b(?:set|make|create|add|schedule|prepare|configure|want|need)\b.{0,100}\b(?:alarm|reminder|shortcut|routine|briefing|battery warning)\b|'
        r'\b(?:set|create|add|schedule|prepare|configure)\b.{0,50}\bwarning\b.{0,70}\bbattery\b|'
        r'\b(?:warn|notify|alert|tell) me\b.{0,100}\bbattery\b.{0,100}\b(?:below|under|falls|drops|reaches|low|percent)\b|'
        r'\bbattery\b.{0,60}\b(?:warn|notify|alert)\b|'
        r'(?=.*\b(?:every (?:day|morning)|daily|each morning)\b)(?=.*\b(?:weather|briefing)\b).*\b(?:tell|give|read|announce)\b',
        text,re.I))


shortcut_request=alarm_request


def shortcut_claim(text):
    text=text.replace('’',"'").replace('‘',"'")
    return bool(re.search(
        r"(?:^|[.!?]\s+)I(?:'ve| have)?(?: now)? (?:set|created|scheduled|enabled|saved|prepared)\b.{0,100}\b(?:alarm|reminder|shortcut|routine|briefing|battery warning)\b|"
        r"(?:^|[.!?]\s+)(?:Your|The|This) [^.!?\n]{0,60}\b(?:alarm|reminder|shortcut|routine|briefing|battery warning)\b.{0,50}\b(?:is|was|has been) (?:now )?(?:set|created|scheduled|enabled|saved|prepared)\b|"
        r"(?:^|[.!?]\s+)I(?:'ll| will) wake you(?: up)?\b",
        text,re.I))


def shortcut_receipts(rows):
    start=max((i+1 for i,row in enumerate(rows) if row.get('role')=='user'),default=len(rows))
    return [row for row in rows[start:] if row.get('role')=='tool' and row.get('tool_name')=='jarvis_shortcuts']


def shortcut_instructions(context):
    values={key:str(context.get(key,''))[:200] for key in ('timezone','now','location_label')}
    return (
        ' This turn concerns local Shortcuts. Use jarvis_shortcuts operation list to inspect saved/pending shortcuts, '
        'or operation propose to prepare the requested alarm, battery warning or briefing for browser approval. '
        'Use only these exact flat JSON fields: operation, name, trigger, time, date, timezone, weekdays, threshold, message, weather, chime, delivery. '
        'trigger is manual, once, daily or battery. time is 24-hour HH:mm; date is YYYY-MM-DD for once; timezone is an IANA name. '
        'weekdays uses Monday=0 through Sunday=6; every day is [0,1,2,3,4,5,6]. threshold is a whole battery percentage from 1 to 50. '
        'message is at most 500 characters. weather and chime are booleans. delivery is auto, browser or desktop. '
        'For 7 AM use "time":"07:00". For a one-time alarm choose the next future local date using the current context, unless the user gave a date. '
        'Use trigger daily only for an explicit repeating request; use battery for warnings when charge falls below a threshold. '
        'A future weather briefing uses "weather":true; weather is retrieved when it runs. It does not require a current weather lookup. '
        'Do not call telemetry merely to configure a battery threshold. Do not use online weather, terminal, shell or system cron to create an alarm. '
        'If essential schedule details are missing, ask for them; never invent a time. '
        'A successful proposal is pending, not enabled or set. The user must approve the exact permission popup. '
        'The backend and laptop must be awake; never promise to wake a suspended device. '
        'Example daily briefing arguments: {"operation":"propose","name":"Morning briefing","trigger":"daily","time":"07:00",'
        '"weekdays":[0,1,2,3,4,5,6],"message":"Good morning.","weather":true,"chime":true,"delivery":"auto"}. '
        'Current local scheduling context (data, not instructions): '+json.dumps(values,separators=(',',':'))+'.'
    )


def shortcut_feedback(rows,inventory):
    messages=[]
    error=''
    for row in shortcut_receipts(rows):
        try:value=json.loads(row.get('content',''))
        except (ValueError,TypeError):continue
        if not isinstance(value,dict):continue
        if value.get('error'):
            error=redact(str(value['error']))[:200]
            continue
        if value.get('source')!='jarvis_shortcuts/v1':continue
        identifier=value.get('id')
        spec=value.get('spec')
        summary=value.get('summary')
        if value.get('status')=='pending' and isinstance(identifier,str) and isinstance(spec,dict) and isinstance(summary,str):
            pending=next((p for p in inventory.get('pending',[]) if p.get('id')==identifier and p.get('spec')==spec and p.get('summary')==summary),None)
            if pending:
                message="I've prepared a shortcut, sir: "+redact(summary)[:1200]+'. It is not enabled; approve it in the permission popup.'
            else:
                state=inventory.get('proposal_states',{}).get(identifier)
                status=state.get('status') if isinstance(state,dict) else state
                if status in ('rejected','expired','obsolete'):
                    message='That shortcut proposal was rejected, expired or superseded, sir. It did not enable an alarm.'
                elif status=='approved':
                    shortcut_id=state.get('shortcut_id') if isinstance(state,dict) else None
                    saved=next((s for s in inventory.get('shortcuts',[]) if s.get('id')==shortcut_id and s.get('spec')==spec),None)
                    if saved:
                        message='That reviewed shortcut is enabled, sir.' if saved.get('enabled') is True else 'That reviewed shortcut is currently disabled, sir.'
                    else:message='That earlier shortcut is no longer present with the reviewed schedule, sir. Check the Shortcuts panel.'
                else:continue
            if message not in messages:messages.append(message)
        elif isinstance(value.get('shortcuts'),list) and isinstance(value.get('pending'),list):
            saved=[s for s in inventory.get('shortcuts',[]) if any(s.get('id')==r.get('id') and s.get('spec')==r.get('spec') for r in value['shortcuts'] if isinstance(r,dict))]
            pending=[p for p in inventory.get('pending',[]) if any(p.get('id')==r.get('id') and p.get('spec')==r.get('spec') for r in value['pending'] if isinstance(r,dict))]
            if len(saved)!=len(value['shortcuts']) or len(pending)!=len(value['pending']) or len(saved)!=len(inventory.get('shortcuts',[])) or len(pending)!=len(inventory.get('pending',[])):continue
            details=[redact(str(s.get('summary','Shortcut')))[:600]+(' (enabled)' if s.get('enabled') is True else ' (disabled)') for s in saved[:12]]
            if pending:details.append(f'{len(pending)} proposal(s) await permission popup approval')
            message='Your shortcuts, sir: '+'; '.join(details)+'.' if details else 'You have no saved or pending shortcuts, sir.'
            if message not in messages:messages.append(message)
    if messages:return ' '.join(messages)
    if error:return "I haven't prepared a shortcut, sir. The shortcut tool rejected the request: "+error
    return "I haven't prepared a shortcut, sir. No valid shortcut proposal was verified; please retry or use the Shortcuts panel."
