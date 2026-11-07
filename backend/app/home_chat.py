import json,re


def home_request(text):
    if re.search(r'\b(?:user|memory|soul)\.md\b',text,re.I):return False
    if re.search(r'\b(web|internet|online)\b',text,re.I) and not re.search(r'\bmy (?:files|folders|home)\b',text,re.I):return False
    scope=re.search(r'\b(?:my|our|this|the) (?:files?|folders?|directories|directory|filesystem|file system|home)\b|\b(home directory|downloads|documents|pictures)\b|[\w/-]+\.(?:md|txt|json|py|tsx?|ya?ml)\b',text,re.I)
    direct=re.match(r'\s*(?:please )?(?:list|browse|search|find|read|inspect|look through) (?:the )?(?:files|folders|directories)\b',text,re.I)
    return bool((scope or direct) and re.search(r'\b(list|show|browse|search|find|read|inspect|look through)\b',text,re.I))


def home_receipts(rows):
    start=max((i+1 for i,row in enumerate(rows) if row.get('role')=='user'),default=len(rows))
    return [r for r in rows[start:] if r.get('role')=='tool' and r.get('tool_name')=='jarvis_home_files']


def home_summary(rows):
    for row in reversed(home_receipts(rows)):
        try:value=json.loads(row.get('content',''))
        except (ValueError,TypeError):continue
        if not isinstance(value,dict) or value.get('source')!='home_files' or value.get('error'):continue
        path=str(value.get('path','')).replace('`','')[:1024]
        if isinstance(value.get('text'),str):
            text=value['text'][:6000]
            fence='`'*max(3,max((len(m[0]) for m in re.finditer(r'`+',text)),default=0)+1)
            note=' (preview truncated)' if value.get('truncated') or len(value['text'])>6000 else ''
            return f'File in your home: `{path}`{note}.\n\n{fence}text\n{text}\n{fence}'
        if isinstance(value.get('entries'),list):
            names=[str(e.get('name','')).replace('`','')[:120]+('/' if e.get('kind')=='directory' else '') for e in value['entries'][:12] if isinstance(e,dict)]
            label='Matching names' if value.get('query') else 'Entries'
            summary=f"{label} within `{path or 'home'}`: "+(', '.join('`'+name+'`' for name in names) if names else 'none reported')+'.'
            if value.get('truncated') or len(value['entries'])>12:summary+=' Results are bounded; narrow the folder or filename search for more.'
            return summary
    return None
