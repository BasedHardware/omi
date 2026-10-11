"""Network-only doubles. Real parsing, renderers, sinks and provider request code run."""

import copy
import httpx


class FixtureTransport:
    def __init__(self, responses=()):
        self.responses = list(responses)
        self.calls = []
        self.downloads = []

    async def request(self, method, url, **kwargs):
        self.calls.append((method, url, copy.deepcopy(kwargs)))
        if self.responses:
            response = self.responses.pop(0)
            if isinstance(response, Exception):
                raise response
            status, body, headers = response
            return httpx.Response(status, json=body, headers=headers)
        if url.endswith('/getFile'):
            return httpx.Response(200, json={'ok': True, 'result': {'file_path': 'documents/fixture.txt'}})
        if url.endswith('/attachments'):
            return httpx.Response(
                200,
                json={
                    'upload_url': 'https://uploads.linqapp.com/fixture',
                    'required_headers': {'Content-Type': 'text/plain'},
                    'attachment_id': 'fixture-upload',
                },
            )
        return httpx.Response(200, json={'ok': True, 'result': {'message_id': 71}, 'id': 'provider-receipt'})

    async def download(self, url, **kwargs):
        self.downloads.append((url, kwargs))
        return b'test file'


class FixtureLedger:
    def __init__(self):
        self.received, self.sent, self.receipts = set(), 0, {}

    async def receive(self, message):
        self.received.add((message.external_chat_id, message.provider_message_id))

    async def begin(self, message, operation, *, ratio=None, retry_reserved=False):
        state = self.receipts.get(operation)
        if state == 'accepted':
            return False
        if state:
            if retry_reserved:
                return True
            raise RuntimeError('Ambiguous delivery requires reconciliation')
        if ratio and self.sent + 1 > len(self.received) * ratio:
            raise PermissionError('Send/receive ratio exhausted')
        self.sent += 1
        self.receipts[operation] = 'reserved'
        return True

    async def commit(self, message, operation, provider_id):
        self.receipts[operation] = 'accepted'


async def no_sleep(seconds):
    pass
