import json,re
from .conversation_style import simple_intent
from .memory import redact


def memory_request(text):
    if simple_intent(text)=='user_name':return False
    text=re.sub(r'"[^"\n]*"|“[^”\n]*”|`[^`]*`','',text)
    return bool(re.search(
        r"(?:^|[.!?]\s+)(?:jarvis[, ]+)?(?:please )?(?:remember|forget)\b|"
        r"\b(?:please|always|you to|can you|could you) remember\b|"
        r"\b(?:save|store|keep|add|write|update|delete|remove|forget)\b.{0,100}\b(?:memory|memories|user\.md|memory\.md)\b|"
        r"\b(?:did not|didn't|haven't|hasn't) save\b.{0,80}\b(?:memory|user\.md|memory\.md)\b|"
        r"(?:^|[.!?]\s+)(?:please )?my name is\b|(?:^|[.!?]\s+)(?:please )?(?:call|address) me\b.{0,70}\b(?:from now on|always|formally|sir|mister|mr\.)\b",
        text,re.I))


def memory_claim(text):
    text=text.replace('’',"'").replace('‘',"'")
    return bool(re.search(r"(?:^|[.!?]\s+)(?:I(?:'ve| have)?(?: now)? (?:saved|stored|recorded|updated|committed|remembered)|(?:Your|The|This) (?:name|preference|memory|change).{0,30}(?:has been|is now|was|is) (?:saved|stored|locked|recorded))\b",text,re.I))


def memory_receipts(rows):
    start=max((i+1 for i,row in enumerate(rows) if row.get('role')=='user'),default=len(rows))
    return [row for row in rows[start:] if row.get('role')=='tool' and row.get('tool_name')=='jarvis_memory_propose']


def memory_feedback(rows,inventory):
    messages=[]
    error=''
    for row in memory_receipts(rows):
        try:value=json.loads(row.get('content',''))
        except (ValueError,TypeError):continue
        if not isinstance(value,dict):continue
        if value.get('error'):
            error=redact(str(value['error']))[:200]
            continue
        target=value.get('target');action=value.get('action');identifier=value.get('id')
        if target not in ('user','memory') or action not in ('add','patch','remove'):continue
        filename='USER.md' if target=='user' else 'MEMORY.md'
        pending=next((p for p in inventory.get('pending',[]) if p.get('id')==identifier and all(p.get(k,'')==value.get(k,'') for k in ('action','target','content','old_text','reason'))),None)
        if pending:
            message=f"I've prepared a change to {filename}, sir. It is not saved yet; approve it in the permission popup."
        else:
            status=inventory.get('proposal_states',{}).get(identifier)
            present=lambda text:any(e.get('target')==target and e.get('text')==text and not e.get('previously_deleted') for e in inventory.get('entries',[]))
            if status in ('rejected','obsolete'):
                message='That memory proposal was rejected or superseded, sir. It did not save a new preference.'
            elif action in ('add','patch') and value.get('content') and present(value['content']):
                message=f'That preference is saved in {filename}, sir.'
            elif action=='remove' and status=='approved' and value.get('old_text') and not present(value['old_text']):
                message=f'The reviewed entry was removed from {filename}, sir.'
            elif status=='approved':
                message='That earlier change is not present in current saved memory, sir.'
            else:continue
        if message not in messages:messages.append(message)
    if messages:return ' '.join(messages)
    if error:return "I haven't saved a memory, sir. The memory tool rejected the change: "+error
    return "I haven't saved a memory, sir. No valid memory change was prepared; please retry or use the Memory panel."
