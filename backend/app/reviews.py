"""Short-lived confirmations tied to a paired browser and an immutable proposal."""
import hashlib
import hmac
import json
import secrets
import time


def snapshot(proposal):
    return hashlib.sha256(json.dumps(proposal, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class ReviewTickets:
    def __init__(self):
        self.tickets = {}

    def issue(self, owner, proposals):
        now = time.time()
        self.tickets = {key: value for key, value in self.tickets.items() if value['expires'] > now}
        result = []
        for proposal in proposals[:100]:
            digest = snapshot(proposal)
            existing = next((value for value in self.tickets.values() if value['_owner'] == owner and value['_snapshot'] == digest), None)
            if not existing:
                used = {value['code'] for value in self.tickets.values() if value['_owner'] == owner}
                code = f'{secrets.randbelow(10000):04d}'
                while code in used:
                    code = f'{secrets.randbelow(10000):04d}'
                existing = {**proposal, 'id': secrets.token_urlsafe(24), 'code': code,
                            'expires': min(now + 120, proposal.get('expires', now + 120)),
                            '_owner': owner, '_snapshot': digest}
                self.tickets[existing['id']] = existing
            result.append({key: value for key, value in existing.items() if not key.startswith('_')})
        return result

    def consume(self, owner, identifier, code, proposals):
        ticket = self.tickets.get(identifier)
        if not ticket or ticket['_owner'] != owner or ticket['expires'] <= time.time():
            raise ValueError('This confirmation expired or belongs to another browser. Review the current proposal.')
        if not hmac.compare_digest(str(code).encode(), ticket['code'].encode()):
            raise ValueError('The confirmation code does not match the displayed proposal.')
        if not any(snapshot(proposal) == ticket['_snapshot'] for proposal in proposals):
            raise ValueError('The original proposal changed or was already resolved. Review it again.')
        del self.tickets[identifier]
        return ticket

    def forget(self, owner):
        self.tickets = {key: value for key, value in self.tickets.items() if value['_owner'] != owner}
