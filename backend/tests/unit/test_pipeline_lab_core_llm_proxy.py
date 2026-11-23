"""Pipeline-lab LLM record/replay proxy against a loopback fake upstream. No real provider calls."""

import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from testing.pipeline_lab import contracts as c
from testing.pipeline_lab.ledger import SpendLedger
from testing.pipeline_lab.llm_proxy import tagging, wire
from testing.pipeline_lab.llm_proxy.server import LlmProxy, ProxyConfig
from testing.pipeline_lab.store import Store

OPENAI_JSON = {
    'id': 'x',
    'model': 'fake-luna',
    'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': '{"title": "Fictional"}'}}],
    'usage': {'prompt_tokens': 1000, 'completion_tokens': 100, 'prompt_tokens_details': {'cached_tokens': 500}},
}
OPENAI_SSE = [
    b'data: {"model":"fake-luna","choices":[{"delta":{"content":"Hel"}}]}\n\n',
    b'data: {"model":"fake-luna","choices":[{"delta":{"content":"lo"}}]}\n\n',
    b'data: {"model":"fake-luna","choices":[],"usage":{"prompt_tokens":10,"completion_tokens":2}}\n\n',
    b'data: [DONE]\n\n',
]
ANTHROPIC_SSE = [
    b'event: message_start\ndata: {"type":"message_start","message":{"model":"fake-claude","usage":{"input_tokens":7,"cache_read_input_tokens":3}}}\n\n',
    b'event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hi"}}\n\n',
    b'event: message_delta\ndata: {"type":"message_delta","usage":{"output_tokens":4}}\n\n',
]


class FakeUpstream:
    def __init__(self):
        self.requests = []
        self.fail_status = None
        self.fail_next = []  # statuses answered once each, in order, before normal behaviour
        upstream = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *args):
                return

            def do_POST(self):
                body = self.rfile.read(int(self.headers['Content-Length']))
                upstream.requests.append({'path': self.path, 'headers': dict(self.headers.items()), 'body': body})
                if upstream.fail_next:
                    status = upstream.fail_next.pop(0)
                    payload = b'{"error":{"message":"transient"}}'
                    self.send_response(status)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                if upstream.fail_status:
                    payload = b'{"error":{"message":"boom"}}'
                    self.send_response(upstream.fail_status)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                parsed = json.loads(body)
                if parsed.get('stream'):
                    chunks = ANTHROPIC_SSE if self.path.endswith('/messages') else OPENAI_SSE
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/event-stream')
                    self.send_header('Transfer-Encoding', 'chunked')
                    self.end_headers()
                    for chunk in chunks:
                        self.wfile.write(b'%x\r\n%s\r\n' % (len(chunk), chunk))
                        self.wfile.flush()
                    self.wfile.write(b'0\r\n\r\n')
                    return
                if self.path.endswith('/embeddings'):
                    payload = json.dumps(
                        {
                            'model': 'fake-embedding',
                            'data': [{'embedding': [0.1] * 8}],
                            'usage': {'prompt_tokens': 5, 'total_tokens': 5},
                        }
                    ).encode()
                else:
                    payload = json.dumps(OPENAI_JSON).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_address[1]}'

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def upstream():
    fake = FakeUpstream()
    yield fake
    fake.close()


@pytest.fixture
def lab(tmp_path):
    store = Store.open(tmp_path / 'root', tmp_path / 'verdicts')
    store.create_run(c.RunRecord(run_id='run-1', day_id='d1', ref='main'))
    return store


def _proxy(lab, upstream, *, mode='record', cap_usd=1.0, run_id='run-1'):
    ledger = SpendLedger(lab.ledger_path('run-1'), budget_usd=cap_usd)
    return LlmProxy(ProxyConfig(upstream=upstream.url, mode=mode, run_id=run_id), store=lab, ledger=ledger)


def _post(url, body, headers=None):
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', **(headers or {})}
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=20) as response:
            return response.status, dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers.items()), error.read()


CHAT = {'model': 'omi-auto:notes', 'messages': [{'role': 'user', 'content': 'Summarise a fictional chat.'}]}


def test_miss_forwards_records_and_logs_then_hit_serves_from_cache(lab, upstream):
    with _proxy(lab, upstream) as proxy:
        headers = {
            'X-Omi-LLM-Feature': 'conversation_notes',
            tagging.STAGE_HEADER: 'notes',
            tagging.CONVERSATION_HEADER: 'conv-1',
            'Authorization': 'Bearer local-fake',
        }
        status, response_headers, body = _post(proxy.url + '/v1/chat/completions', CHAT, headers)
        assert status == 200 and json.loads(body) == OPENAI_JSON
        assert response_headers['X-Pipeline-Lab-Cache'] == 'miss'
        miss_id = response_headers['X-Pipeline-Lab-Call-Id']
        status, response_headers, again = _post(proxy.url + '/v1/chat/completions', CHAT, headers)
        assert again == body and response_headers['X-Pipeline-Lab-Cache'] == 'hit'
        hit_id = response_headers['X-Pipeline-Lab-Call-Id']
    assert len(upstream.requests) == 1
    sent = upstream.requests[0]
    assert sent['path'] == '/v1/chat/completions'
    lowered = {k.lower(): v for k, v in sent['headers'].items()}
    assert lowered['accept-encoding'] == 'identity'
    assert lowered['authorization'] == 'Bearer local-fake'
    assert not any(k.startswith('x-pipeline-lab-') for k in lowered)
    calls = lab.read_llm_calls('run-1')
    assert len(calls) == 2
    # Handlers can append their log rows in a different order from the HTTP responses.
    by_id = {call.id: call for call in calls}
    assert set(by_id) == {miss_id, hit_id} and miss_id != hit_id
    miss, hit = by_id[miss_id], by_id[hit_id]
    assert not miss.cache_hit and hit.cache_hit
    assert (miss.stage, miss.conversation_id, miss.feature, miss.model) == (
        'notes',
        'conv-1',
        'conversation_notes',
        'fake-luna',
    )
    assert (miss.tokens_in, miss.tokens_out) == (1000, 100)
    assert miss.output == '{"title": "Fictional"}'
    assert miss.prompt == {'messages': CHAT['messages']}
    # 500 fresh + 500 cached at 1/10 on the default 0.10/0.60 table
    assert miss.usd == pytest.approx((500 * 0.10 + 500 * 0.01 + 100 * 0.60) / 1e6)
    assert hit.usd == 0.0
    ledger = SpendLedger(lab.ledger_path('run-1'), budget_usd=1.0).snapshot()
    assert ledger['settled_usd'] == pytest.approx(miss.usd) and ledger['in_flight_usd'] == 0


def test_cache_key_ignores_per_process_fields_but_not_prompt_or_feature(lab, upstream):
    with _proxy(lab, upstream) as proxy:
        _post(proxy.url + '/v1/chat/completions', {**CHAT, 'user': 'a', 'prompt_cache_key': 'p1'})
        _post(proxy.url + '/v1/chat/completions', {**CHAT, 'user': 'b', 'prompt_cache_key': 'p2'})
        assert len(upstream.requests) == 1
        _post(proxy.url + '/v1/chat/completions', CHAT, {'X-Omi-LLM-Feature': 'other'})
        _post(proxy.url + '/v1/chat/completions', {**CHAT, 'messages': [{'role': 'user', 'content': 'x'}]})
        assert len(upstream.requests) == 3


def test_openai_stream_is_relayed_recorded_and_replayed(lab, upstream):
    body = {**CHAT, 'stream': True, 'stream_options': {'include_usage': True}}
    with _proxy(lab, upstream) as proxy:
        status, headers, first = _post(proxy.url + '/v1/chat/completions', body)
        assert status == 200 and headers['Content-Type'] == 'text/event-stream'
        assert first == b''.join(OPENAI_SSE)
        status, headers, second = _post(proxy.url + '/v1/chat/completions', body)
        assert second == first and headers['X-Pipeline-Lab-Cache'] == 'hit'
    assert len(upstream.requests) == 1
    call = lab.read_llm_calls('run-1')[0]
    assert call.output == 'Hello' and (call.tokens_in, call.tokens_out) == (10, 2)
    assert call.extra['stream'] is True


def test_anthropic_stream_usage(lab, upstream):
    body = {'model': 'claude-x', 'system': 'be brief', 'messages': [{'role': 'user', 'content': 'hi'}], 'stream': True}
    with _proxy(lab, upstream) as proxy:
        status, _, payload = _post(proxy.url + '/v1/messages', body, {'anthropic-version': '2023-06-01'})
    assert status == 200 and payload == b''.join(ANTHROPIC_SSE)
    call = lab.read_llm_calls('run-1')[0]
    assert call.model == 'fake-claude' and call.output == 'Hi'
    assert (call.tokens_in, call.tokens_out) == (10, 4)
    assert call.prompt['system'] == 'be brief'


def test_embeddings_never_log_vectors(lab, upstream):
    with _proxy(lab, upstream) as proxy:
        status, _, _ = _post(proxy.url + '/v1/embeddings', {'model': 'text-embedding-x', 'input': ['fictional']})
    assert status == 200
    call = lab.read_llm_calls('run-1')[0]
    assert call.output == {'items': 1, 'dims': 8}
    assert call.usd == pytest.approx(5 * 0.02 / 1e6)


def test_replay_mode_miss_is_non_retryable(lab, upstream):
    proxy = LlmProxy(ProxyConfig(upstream=upstream.url, mode='replay', run_id='run-1'), store=lab)
    with proxy:
        status, headers, body = _post(proxy.url + '/v1/chat/completions', CHAT)
    assert status == 409 and headers['x-should-retry'] == 'false'
    assert json.loads(body)['error']['code'] == 'cache_miss'
    assert upstream.requests == []


def test_spend_cap_refuses_before_sending(lab, upstream):
    with _proxy(lab, upstream, cap_usd=0.001) as proxy:  # below one reservation
        status, headers, body = _post(proxy.url + '/v1/chat/completions', CHAT)
        assert proxy.cap_reached
    assert status == 402 and headers['x-should-retry'] == 'false'
    assert json.loads(body)['error']['code'] == 'spend_cap_reached'
    assert upstream.requests == []
    assert lab.read_llm_calls('run-1')[0].extra['error'] == 'spend_cap_reached'


def test_cache_hits_still_served_after_the_cap(lab, upstream):
    with _proxy(lab, upstream) as proxy:
        _post(proxy.url + '/v1/chat/completions', CHAT)
    with _proxy(lab, upstream, cap_usd=0.0) as proxy:
        status, _, _ = _post(proxy.url + '/v1/chat/completions', CHAT)
    assert status == 200 and len(upstream.requests) == 1


def test_upstream_error_is_relayed_unbilled_and_not_cached(lab, upstream):
    upstream.fail_status = 500
    with _proxy(lab, upstream) as proxy:
        status, _, _ = _post(proxy.url + '/v1/chat/completions', CHAT)
        assert status == 500
        upstream.fail_status = None
        status, headers, _ = _post(proxy.url + '/v1/chat/completions', CHAT)
        assert status == 200 and headers['X-Pipeline-Lab-Cache'] == 'miss'
    calls = lab.read_llm_calls('run-1')
    assert calls[0].extra['status'] == 500 and calls[0].usd == 0
    assert SpendLedger(lab.ledger_path('run-1'), budget_usd=1.0).snapshot()['in_flight_usd'] == 0


def test_transient_gateway_answers_are_retried_before_the_client_sees_them(lab, upstream, monkeypatch):
    # A real-day replay died on one 502 from the dev gateway while seeding embeddings.
    from testing.pipeline_lab.llm_proxy import server

    monkeypatch.setattr(server, 'UPSTREAM_BACKOFF_SECONDS', 0.0)
    upstream.fail_next = [502, 503]
    with _proxy(lab, upstream) as proxy:
        status, headers, _ = _post(proxy.url + '/v1/embeddings', {'model': 'e', 'input': ['x']})
    assert status == 200 and headers['X-Pipeline-Lab-Cache'] == 'miss'
    assert len(upstream.requests) == 3
    calls = lab.read_llm_calls('run-1')
    assert calls[0].extra['retries'] == [502, 503] and calls[0].extra['status'] == 200


def test_persistent_gateway_error_is_relayed_after_the_last_attempt(lab, upstream, monkeypatch):
    from testing.pipeline_lab.llm_proxy import server

    monkeypatch.setattr(server, 'UPSTREAM_BACKOFF_SECONDS', 0.0)
    upstream.fail_status = 502
    with _proxy(lab, upstream) as proxy:
        status, _, _ = _post(proxy.url + '/v1/chat/completions', CHAT)
    assert status == 502 and len(upstream.requests) == server.UPSTREAM_ATTEMPTS
    assert lab.read_llm_calls('run-1')[0].usd == 0


def test_refused_connections_are_waited_out_past_the_attempt_count(lab, upstream, monkeypatch):
    # The dev gateway sits behind a reconnecting port-forward; a real day lost its daily summary
    # when the tunnel was down for longer than four quick retries.
    import http.client

    from testing.pipeline_lab.llm_proxy import server

    monkeypatch.setattr(server, 'UPSTREAM_BACKOFF_SECONDS', 0.0)
    monkeypatch.setattr(server, 'UPSTREAM_CONNECT_WAIT_SECONDS', 30.0)
    refusals = [server.UPSTREAM_ATTEMPTS + 2]
    upstream_port = int(upstream.url.rsplit(':', 1)[1].split('/')[0])
    real_connect = http.client.HTTPConnection.connect

    def connect(self):
        if self.port == upstream_port and refusals[0] > 0:
            refusals[0] -= 1
            raise ConnectionRefusedError('tunnel down')
        return real_connect(self)

    monkeypatch.setattr(http.client.HTTPConnection, 'connect', connect)
    with _proxy(lab, upstream) as proxy:
        status, _, _ = _post(proxy.url + '/v1/chat/completions', CHAT)
    assert status == 200 and len(upstream.requests) == 1
    assert lab.read_llm_calls('run-1')[0].extra['retries'] == ['transport'] * (server.UPSTREAM_ATTEMPTS + 2)


def test_unreachable_upstream_releases_or_keeps_reservation(lab, monkeypatch):
    from testing.pipeline_lab.llm_proxy import server

    monkeypatch.setattr(server, 'UPSTREAM_BACKOFF_SECONDS', 0.0)
    monkeypatch.setattr(server, 'UPSTREAM_CONNECT_WAIT_SECONDS', 0.0)
    ledger = SpendLedger(lab.ledger_path('run-1'), budget_usd=1.0)
    proxy = LlmProxy(ProxyConfig(upstream='http://127.0.0.1:9', run_id='run-1', timeout=5), store=lab, ledger=ledger)
    with proxy:
        status, _, _ = _post(proxy.url + '/v1/chat/completions', CHAT)
    assert status == 502
    assert ledger.snapshot()['committed_usd'] == 0  # connect refused: never sent, released


def test_session_tag_applies_when_headers_absent(lab, upstream):
    with _proxy(lab, upstream) as proxy:
        url = proxy.url + '/v1/chat/completions'
        tagging.set_session_tag(proxy.url, 'memories', 'conv-9')
        _, inherited_headers, _ = _post(url, CHAT)
        _, explicit_headers, _ = _post(url, {**CHAT, 'n': 2}, {tagging.STAGE_HEADER: 'notes'})
        tagging.set_session_tag(proxy.url, None)
        _, cleared_headers, _ = _post(url, {**CHAT, 'n': 3})

    call_id_header = 'X-Pipeline-Lab-Call-Id'
    inherited_id = inherited_headers[call_id_header]
    explicit_id = explicit_headers[call_id_header]
    cleared_id = cleared_headers[call_id_header]
    assert len({inherited_id, explicit_id, cleared_id}) == 3

    # Handlers can append their rows in a different order than the responses.
    rows = lab.read_llm_calls('run-1')
    assert len(rows) == 3
    assert {call.id: (call.stage, call.conversation_id) for call in rows} == {
        inherited_id: ('memories', 'conv-9'),
        explicit_id: ('notes', None),
        cleared_id: (None, None),
    }


def test_httpx_tagging_helper_tags_only_proxy_requests(lab, upstream):
    httpx = pytest.importorskip('httpx')
    with _proxy(lab, upstream) as proxy:
        uninstall = tagging.install_httpx_tagging(proxy.url)
        try:
            with tagging.lab_tag('tasks', 'conv-3'):
                with httpx.Client() as client:
                    response = client.post(proxy.url + '/v1/chat/completions', json=CHAT)
                    assert response.status_code == 200
                    client.post(upstream.url + '/v1/embeddings', json={'input': ['direct']})
        finally:
            uninstall()
    call = lab.read_llm_calls('run-1')[0]
    assert (call.stage, call.conversation_id) == ('tasks', 'conv-3')
    direct = upstream.requests[-1]
    assert not any(k.lower().startswith('x-pipeline-lab-') for k in direct['headers'])


def test_carry_context_follows_into_threads():
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(1) as pool, tagging.lab_tag('goals', 'c1'):
        plain = pool.submit(tagging.current_headers).result()
        carried = pool.submit(tagging.carry_context(tagging.current_headers)).result()
    assert plain == {}
    assert carried == {tagging.STAGE_HEADER: 'goals', tagging.CONVERSATION_HEADER: 'c1'}


def test_proxy_binds_loopback_only_and_requires_a_ledger(lab, upstream):
    with pytest.raises(ValueError):
        LlmProxy(ProxyConfig(upstream=upstream.url), store=lab, ledger=None)
    with pytest.raises(ValueError):
        LlmProxy(ProxyConfig(upstream=upstream.url, mode='replay'), store=lab, host='0.0.0.0')
    with pytest.raises(ValueError):
        ProxyConfig(upstream='file:///etc/passwd')


def test_reservation_estimate_uses_the_output_ceiling():
    prices = wire.PriceTable()
    small = prices.reservation('/v1/chat/completions', {'max_tokens': 100}, 300)
    large = prices.reservation('/v1/chat/completions', {}, 300)
    assert small < large
    assert prices.reservation('/v1/embeddings', {'model': 'text-embedding-x'}, 300) < small


def test_foreground_serve_reports_the_bound_url(lab, upstream):
    proxy = _proxy(lab, upstream)
    ready = threading.Event()
    urls = []

    def on_ready(url):
        urls.append(url)
        ready.set()

    thread = threading.Thread(target=proxy.serve_forever, kwargs={'on_ready': on_ready}, daemon=True)
    thread.start()
    assert ready.wait(10)
    try:
        assert not urls[0].endswith(':0')
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
            urls[0] + '/_lab/health', timeout=10
        ) as r:
            assert json.loads(r.read())['run_id'] == 'run-1'
    finally:
        proxy.stop()
        thread.join(10)


def test_plain_http_upstream_is_only_allowed_on_loopback():
    from testing.pipeline_lab.llm_proxy.server import ProxyConfig

    for ok in ('http://127.0.0.1:9', 'http://localhost:9', 'http://[::1]:9', 'https://gateway.example'):
        ProxyConfig(upstream=ok)
    with pytest.raises(ValueError):
        ProxyConfig(upstream='http://gateway.example')


def test_relayed_header_values_lose_control_characters():
    from testing.pipeline_lab.llm_proxy.server import _header_value

    assert _header_value('application/json\r\nSet-Cookie: x=1') == 'application/jsonSet-Cookie: x=1'
    assert _header_value('text/event-stream; charset=utf-8') == 'text/event-stream; charset=utf-8'
