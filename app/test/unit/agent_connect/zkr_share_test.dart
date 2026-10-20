import 'dart:convert';

import 'package:cryptography/cryptography.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:omi/services/agent_connect/zkr_share.dart';

// protocol/test-vectors.json from github.com/Git-on-my-level/zk-relay — the reference client's
// deterministic AES-GCM vector (public test payload). The web suite pins the same vector
// (web/app/src/lib/__tests__/zkr.test.ts), so phone and browser links decrypt identically.
const _vectorKey = 'AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8';
const _vectorNonce = 'EBESExQVFhcYGRob';
const _vectorEnvelope = {
  'v': 1,
  'kind': 'text',
  'name': 'secret.txt',
  'mediaType': 'text/plain; charset=utf-8',
  'data': 'emstcmVsYXktaW50ZXJvcGVyYWJpbGl0eQ',
};
const _vectorCiphertext =
    'BtzuNHP4FpGhHGZ5LUNLJ7IoOiw34DnQipzAXXwnMbgijCMtgd4azVIU_zTu8XJPaswiUdmpLZfEahVBn_bNBT7YXEsozHhRGb1Air7s0JwRm_bMEvxwAKKVTWya545DD14W3cbLLKReU4k5Gh6VxCyTv2yY3b6ThpuKwQJWGJSJEOrvnz_wskNDeGG6';

const _secret = 'omi_mcp_7f3c0a9e1b2d4c5e6f708192a3b4c5d6';

/// Independent receiver: decrypt exactly as the protocol describes.
Future<String> _receive(String fragment, Map<String, Object?> request) async {
  final parts = fragment.split('.');
  expect(parts.first, 'v1');
  final bytes = base64UrlToBytes(request['ciphertext'] as String);
  final box = SecretBox(
    bytes.sublist(0, bytes.length - 16),
    nonce: base64UrlToBytes(request['nonce'] as String),
    mac: Mac(bytes.sublist(bytes.length - 16)),
  );
  final plain = await AesGcm.with256bits().decrypt(
    box,
    secretKey: SecretKey(base64UrlToBytes(parts[1])),
    aad: utf8.encode(zkrAad),
  );
  final envelope = jsonDecode(utf8.decode(plain)) as Map<String, dynamic>;
  expect(envelope['kind'], 'text');
  return utf8.decode(base64UrlToBytes(envelope['data'] as String));
}

void main() {
  test('matches the reference test vector byte for byte', () async {
    expect(zkrTextEnvelope('zk-relay-interoperability'), _vectorEnvelope);
    final ciphertext = await zkrEncryptEnvelope(
      zkrTextEnvelope('zk-relay-interoperability'),
      base64UrlToBytes(_vectorKey),
      base64UrlToBytes(_vectorNonce),
    );
    expect(bytesToBase64Url(ciphertext), _vectorCiphertext);
  });

  test('round-trips a key through the create request and link fragment', () async {
    final prepared = await prepareZkrShare(_secret);
    expect(await _receive(prepared.fragment, prepared.request), _secret);
    final token = base64UrlToBytes(prepared.fragment.split('.')[2]);
    expect(prepared.request['accessTokenHash'], bytesToBase64Url((await Sha256().hash(token)).bytes));
    expect(prepared.request['expiresInSeconds'], 3600);
    expect(prepared.request['expireAfterReveal'], true);
  });

  test('uses fresh key material for every share', () async {
    final a = await prepareZkrShare(_secret);
    final b = await prepareZkrShare(_secret);
    expect(a.fragment, isNot(b.fragment));
    expect(a.request['nonce'], isNot(b.request['nonce']));
  });

  test('sends only ciphertext to zkr and builds the agent link locally', () async {
    late http.Request sent;
    final client = MockClient((request) async {
      sent = request;
      return http.Response(jsonEncode({'id': 'AbCdEfGhIjKlMnOpQrStUv', 'expiresAt': '2026-10-16T19:00:00Z'}), 201);
    });
    final share = await createZkrShare(_secret, client: client);
    expect(sent.url.toString(), '$zkrOrigin/api/v1/secrets');
    expect(sent.body, isNot(contains(_secret)));
    expect(sent.body, isNot(contains(bytesToBase64Url(utf8.encode(_secret)))));
    final fragment = share.agentLink.split('#').last;
    expect(sent.body, isNot(contains(fragment.split('.')[1])));
    expect(sent.body, isNot(contains(fragment.split('.')[2])));
    expect((jsonDecode(sent.body) as Map).keys.toSet(),
        {'v', 'ciphertext', 'nonce', 'accessTokenHash', 'expiresInSeconds', 'expireAfterReveal'});
    expect(share.agentLink, startsWith('$zkrOrigin/a/AbCdEfGhIjKlMnOpQrStUv#v1.'));
    expect(await _receive(fragment, jsonDecode(sent.body) as Map<String, Object?>), _secret);
  });

  test('a rejected or malformed create fails instead of returning a link', () async {
    await expectLater(
      createZkrShare(_secret, client: MockClient((_) async => http.Response('{}', 429))),
      throwsA(isA<ZkrShareException>()),
    );
    await expectLater(
      createZkrShare(_secret, client: MockClient((_) async => http.Response(jsonEncode({'id': 'short'}), 201))),
      throwsA(isA<ZkrShareException>()),
    );
  });
}
