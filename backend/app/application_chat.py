import json,re


def launch_request(text):
    if re.search(r'\b(service|server|daemon|unit)\b',text,re.I):return False
    return terminal_request(text) or bool(re.match(r'\s*(?:jarvis[, ]+)?(?:please )?(?:(?:can|could) you )?(?:open|launch)\s+(?!(?:source|file|folder|directory)\b|~|/)[^\n]+',text,re.I))


def terminal_request(text):
    return bool(re.search(r'\b(?:run|execute)\b',text,re.I) and (re.search(r'\b(?:kitty|terminal|fastfetch)\b',text,re.I) or re.match(r'\s*(?:jarvis[, ]+)?(?:please )?(?:(?:can|could) you )?(?:run|execute)\s+',text,re.I)))


def launch_claim(text):
    text=text.replace('’',"'")
    return bool(re.search(r"(?:^|[.!?]\s+)I(?:'ve| have)?(?: now)? (?:opened|launched|started)\b",text,re.I))


def launch_receipts(rows):
    start=max((i+1 for i,row in enumerate(rows) if row.get('role')=='user'),default=len(rows))
    return [r for r in rows[start:] if r.get('role')=='tool' and r.get('tool_name') in ('jarvis_launch_application','jarvis_run_terminal')]


def launch_feedback(rows,actions):
    prompt=next((str(row.get('content','')) for row in reversed(rows) if row.get('role')=='user'),'')
    for row in reversed(launch_receipts(rows)):
        if terminal_request(prompt) and row.get('tool_name')!='jarvis_run_terminal':continue
        try:value=json.loads(row.get('content',''))
        except (ValueError,TypeError):continue
        if not isinstance(value,dict) or value.get('error'):continue
        kind='terminal' if row.get('tool_name')=='jarvis_run_terminal' else 'launch'
        action=next((a for a in actions if a.get('id')==value.get('id') and a.get('kind')==kind and all(a.get(k)==value.get(k) for k in ('target','effect','expires'))),None)
        if not action:continue
        status=action.get('status')
        if status=='pending':return f"{action['effect']}. Your approval is required in the popup, sir; it has not been launched."
        if status=='executed':
            if kind=='terminal':return 'Kitty accepted the launch request, sir. The saved command runs there; its output and exit status remain in the terminal.'
            return 'The application launcher accepted the request, sir.'
        if status=='failed':return 'The approved launch failed, sir. Inspect its result in the System panel.'
        return 'That launch request was rejected, expired or superseded, sir.'
    return "I haven't opened an application or run a command, sir. Choose an installed app in System or a saved terminal command in Settings, then retry."
