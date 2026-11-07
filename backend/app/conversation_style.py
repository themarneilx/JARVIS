import re


def simple_intent(text):
    text=' '.join(text.casefold().replace('’',"'").split()).strip(' .!?')
    if re.fullmatch(r'(?:hello|hi|hey|good morning|good afternoon|good evening)(?:[ ,]+jarvis)?',text):
        return 'greeting'
    if re.fullmatch(r'(?:jarvis[, ]+)?are you there',text):
        return 'attention'
    if re.fullmatch(r"(?:what is|what's) your name(?: again)?|who are you",text):
        return 'assistant_name'
    if re.fullmatch(r"(?:and )?(?:what is|what's) my name(?: again)?|do you (?:know|remember) my name",text):
        return 'user_name'
    return None


def simple_reply(intent,entries=()):
    if intent=='greeting':return 'Hello, sir.'
    if intent=='attention':return 'At your service, sir.'
    if intent=='assistant_name':return 'My name is Jarvis, sir.'
    if intent!='user_name':return None
    names=set()
    for entry in entries:
        if entry.get('previously_deleted') or entry.get('target') not in ('user','memory'):continue
        text=entry.get('text','')
        # Only explicit user-name statements qualify, never account paths or assistant descriptions.
        prefix=r"(?:User name changed to |(?:The )?User(?:'s)? (?:preferred |real )?name\s*(?:is |: ?)|User is named )"
        if entry.get('target')=='user':prefix=r'(?:'+prefix+r'|My name is )'
        match=re.match('^'+prefix+r"([\w'-]+(?: [\w'-]+){0,4})(?=[,.;\n]|$)",text,re.I)
        if match:
            name=match[1].strip()
            if name.casefold() not in ('jarvis','j.a.r.v.i.s','unknown','not known'):
                names.add(name)
    if len(names)==1:return f'Your name is {names.pop()}, sir.'
    return 'What would you like me to call you, sir?'
