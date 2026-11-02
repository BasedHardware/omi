// Phone side of the ZK Relay (zkr) v1 hand-off: encrypt a freshly created Omi key on the device and
// turn it into a one-time agent link, so the copy-paste prompt carries a capability URL instead of
// the raw secret. Mirrors web/app/src/lib/zkr.ts byte for byte.
//
// Protocol: https://zkr.scalingforever.com/protocol/v1
//
// What leaves the phone: ciphertext, nonce, and SHA-256 of the access token. The AES key K and the
// access token T exist only in memory and in the link fragment (`#v1.K.T`), which HTTP clients never
// send.

import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

import 'package:cryptography/cryptography.dart';
import 'package:http/http.dart' as http;

/// Public zkr instance. Native apps are not bound by CORS, so the phone calls it directly (the web
/// app needs a same-origin relay for the same request).
const zkrOrigin = 'https://zkr.scalingforever.com';

const zkrAad = 'zk-relay/v1;envelope';

/// Shortest TTL zkr accepts. A key share is consumed once, within minutes.
const zkrShareTtlSeconds = 3600;

/// Receive command the prompt tells the agent to run (link on stdin).
const zkrReceiveCommand = 'zkr receive --link-stdin --output';

/// Agent-facing install/usage guide.
const zkrLlmsTxt = '$zkrOrigin/llms.txt';

class ZkrShare {
  const ZkrShare({required this.id, required this.agentLink});

  final String id;

  /// `/a/:id#v1.K.T` — what an agent receives with `zkr receive`.
  final String agentLink;
}

class PreparedZkrShare {
  const PreparedZkrShare({required this.request, required this.fragment});

  /// The exact body `POST /api/v1/secrets` accepts; nothing secret in it.
  final Map<String, Object> request;

  /// `v1.<key>.<token>`; never sent anywhere.
  final String fragment;
}

String bytesToBase64Url(List<int> bytes) => base64Url.encode(bytes).replaceAll('=', '');

Uint8List base64UrlToBytes(String value) {
  if (!RegExp(r'^[A-Za-z0-9_-]*$').hasMatch(value)) throw const FormatException('Invalid base64url value');
  return Uint8List.fromList(base64Url.decode(value.padRight((value.length + 3) ~/ 4 * 4, '=')));
}

/// A `text` envelope; the field order matches the reference client byte for byte.
Map<String, Object> zkrTextEnvelope(String secret, {String name = 'secret.txt'}) => {
      'v': 1,
      'kind': 'text',
      'name': name,
      'mediaType': 'text/plain; charset=utf-8',
      'data': bytesToBase64Url(utf8.encode(secret)),
    };

/// AES-256-GCM over the UTF-8 JSON envelope with the fixed v1 AAD; returns ciphertext then tag.
Future<Uint8List> zkrEncryptEnvelope(Map<String, Object> envelope, List<int> key, List<int> nonce) async {
  if (key.length != 32 || nonce.length != 12) throw ArgumentError('Invalid encryption material');
  final box = await AesGcm.with256bits().encrypt(
    utf8.encode(jsonEncode(envelope)),
    secretKey: SecretKey(key),
    nonce: nonce,
    aad: utf8.encode(zkrAad),
  );
  return Uint8List.fromList([...box.cipherText, ...box.mac.bytes]);
}

Future<String> zkrHashAccessToken(List<int> token) async => bytesToBase64Url((await Sha256().hash(token)).bytes);

/// Encrypt [secret] and build the create request plus the fragment capability. [key], [token] and
/// [nonce] exist for the protocol test vector; production omits them.
Future<PreparedZkrShare> prepareZkrShare(
  String secret, {
  String name = 'secret.txt',
  List<int>? key,
  List<int>? token,
  List<int>? nonce,
}) async {
  final random = Random.secure();
  List<int> bytes(int n) => List<int>.generate(n, (_) => random.nextInt(256));
  final k = key ?? bytes(32);
  final t = token ?? bytes(32);
  final n = nonce ?? bytes(12);
  if (t.length != 32) throw ArgumentError('Invalid encryption material');
  final ciphertext = await zkrEncryptEnvelope(zkrTextEnvelope(secret, name: name), k, n);
  return PreparedZkrShare(
    request: {
      'v': 1,
      'ciphertext': bytesToBase64Url(ciphertext),
      'nonce': bytesToBase64Url(n),
      'accessTokenHash': await zkrHashAccessToken(t),
      'expiresInSeconds': zkrShareTtlSeconds,
      'expireAfterReveal': true,
    },
    fragment: 'v1.${bytesToBase64Url(k)}.${bytesToBase64Url(t)}',
  );
}

/// Create a one-time, one-hour share of [secret] and return its agent link. Only the ciphertext
/// request crosses the network; the fragment is assembled locally.
Future<ZkrShare> createZkrShare(String secret, {String name = 'secret.txt', http.Client? client}) async {
  final prepared = await prepareZkrShare(secret, name: name);
  final httpClient = client ?? http.Client();
  try {
    final response = await httpClient
        .post(
          Uri.parse('$zkrOrigin/api/v1/secrets'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(prepared.request),
        )
        .timeout(const Duration(seconds: 10));
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw ZkrShareException('Secure link failed (${response.statusCode})');
    }
    final body = jsonDecode(response.body);
    final id = body is Map ? body['id'] : null;
    if (id is! String || !RegExp(r'^[A-Za-z0-9_-]{22,}$').hasMatch(id)) {
      throw const ZkrShareException('Secure link failed (invalid response)');
    }
    return ZkrShare(id: id, agentLink: '$zkrOrigin/a/$id#${prepared.fragment}');
  } finally {
    if (client == null) httpClient.close();
  }
}

class ZkrShareException implements Exception {
  const ZkrShareException(this.message);

  final String message;

  @override
  String toString() => message;
}
