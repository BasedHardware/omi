import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:webview_flutter/webview_flutter.dart';

import 'bridge_http_host.dart';
import 'listen_preflight_policy.dart';

/// One shell-owned authority composes both privileged transports.
class ShellTransportAuthority {
  ShellTransportAuthority({required this.baseUrl, required String? token, required String runId})
    : custody = ShellCredentialCustody(token),
      clientIdentity = _clientIdentity(runId);

  static final RegExp _safeRunId = RegExp(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$');

  static String _clientIdentity(String runId) {
    if (!_safeRunId.hasMatch(runId) ||
        runId == 'anonymous' ||
        runId == 'overflow' ||
        runId.startsWith('__') ||
        runId.endsWith('::ios')) {
      throw ArgumentError.value(runId, 'runId', 'must be a raw bounded producer-evidence id');
    }
    return '$runId::ios';
  }

  final Uri baseUrl;
  final ShellCredentialCustody custody;
  final String clientIdentity;

  BridgeHttpHost makeHttpHost() => BridgeHttpHost(baseUrl: baseUrl, custody: custody, clientIdentity: clientIdentity);

  ListenSocketHost makeListenHost({bool evidenceAudioEnabled = false}) => ListenSocketHost(
    baseUrl: baseUrl,
    custody: custody,
    clientIdentity: clientIdentity,
    evidenceAudioEnabled: evidenceAudioEnabled,
  );

  ListenSocketPolicyResult prepareListen(String path) => ListenSocketHostPolicy.prepare(
    path: path,
    baseUrl: baseUrl,
    token: custody.currentToken,
    clientIdentity: clientIdentity,
  );
}

Uint8List deterministicListenEvidenceAudio() {
  final bytes = Uint8List(3200);
  final data = ByteData.sublistView(bytes);
  for (var sample = 0; sample < 1600; sample++) {
    final value = ((sample * 257) % 24001) - 12000;
    data.setInt16(sample * 2, value, Endian.little);
  }
  return bytes;
}

bool isListenProtocolReady(String text) {
  try {
    final decoded = jsonDecode(text);
    return decoded is Map<String, dynamic> && decoded['type'] == 'service_status' && decoded['status'] == 'ready';
  } on FormatException {
    return false;
  }
}

final class NativeListenEvidenceGate {
  bool _sent = false;

  Uint8List? acceptServiceFrame(String text) {
    if (_sent || !isListenProtocolReady(text)) return null;
    _sent = true;
    return deterministicListenEvidenceAudio();
  }
}

class ListenSocketPreparedRequest {
  const ListenSocketPreparedRequest({required this.url, required this.headers});

  final Uri url;
  final Map<String, String> headers;
}

class ListenSocketPolicyResult {
  const ListenSocketPolicyResult.dispatch(this.request) : failure = null;
  const ListenSocketPolicyResult.failure(this.failure) : request = null;

  final ListenSocketPreparedRequest? request;
  final String? failure;
}

/// Pure authority/auth policy shared by the live host and composition test.
class ListenSocketHostPolicy {
  static ListenSocketPolicyResult prepare({
    required String path,
    required Uri baseUrl,
    required String? token,
    required String clientIdentity,
  }) {
    if (!path.startsWith('/') || path.startsWith('//') || path.contains('://')) {
      return const ListenSocketPolicyResult.failure('path is not origin-relative');
    }
    if (token == null || token.isEmpty) {
      return const ListenSocketPolicyResult.failure('shell holds no credential');
    }
    if (baseUrl.scheme != 'http' && baseUrl.scheme != 'https') {
      return const ListenSocketPolicyResult.failure('API base must use http(s)');
    }
    final socketBase = baseUrl.replace(
      scheme: baseUrl.scheme == 'https' ? 'wss' : 'ws',
      path: '',
      query: null,
      fragment: null,
    );
    final url = socketBase.resolve(path);
    if (url.host != socketBase.host || url.port != socketBase.port) {
      return const ListenSocketPolicyResult.failure('could not resolve Listen socket URL');
    }
    return ListenSocketPolicyResult.dispatch(
      ListenSocketPreparedRequest(
        url: url,
        headers: <String, String>{HttpHeaders.authorizationHeader: 'Bearer $token', 'x-omi-client-id': clientIdentity},
      ),
    );
  }
}

class ListenSocketHost {
  ListenSocketHost({
    required this.baseUrl,
    required this.custody,
    required this.clientIdentity,
    this.evidenceAudioEnabled = false,
  });

  static const channel = 'omiListenSocket';
  static const _preflightChannel = MethodChannel('omi/listen-preflight');

  final Uri baseUrl;
  final ShellCredentialCustody custody;
  final String clientIdentity;
  final bool evidenceAudioEnabled;
  final Map<String, WebSocket> _sockets = <String, WebSocket>{};
  final Map<String, NativeListenEvidenceGate> _evidenceGates = <String, NativeListenEvidenceGate>{};

  ListenSocketPolicyResult prepareUsingCurrentCustodyForConformance(String path) => ListenSocketHostPolicy.prepare(
    path: path,
    baseUrl: baseUrl,
    token: custody.currentToken,
    clientIdentity: clientIdentity,
  );

  Future<void> register(WebViewController controller) {
    return controller.addJavaScriptChannel(
      channel,
      onMessageReceived: (JavaScriptMessage message) {
        unawaited(_handle(controller, message.message));
      },
    );
  }

  Future<void> _handle(WebViewController controller, String raw) async {
    final decoded = jsonDecode(raw);
    if (decoded is! Map<String, dynamic>) return;
    final id = decoded['id'];
    final action = decoded['action'];
    if (id is! String || action is! String) return;
    if (action == 'preflight') {
      final operation = decoded['operation'];
      if (operation is! String ||
          !const <String>{'check', 'request-permission', 'open-settings'}.contains(operation)) {
        return;
      }
      await _handlePreflight(controller, id, operation);
      return;
    }
    if (action == 'close') {
      final code = decoded['code'] is int ? decoded['code'] as int : WebSocketStatus.normalClosure;
      final reason = decoded['reason'] is String ? decoded['reason'] as String : null;
      await _sockets.remove(id)?.close(code, reason);
      return;
    }
    final path = decoded['path'];
    if (action != 'open' || path is! String) return;
    if (!await _listenPreflightReady()) {
      await _emit(controller, id, const <String, Object>{'type': 'error'});
      await _emit(controller, id, const <String, Object>{'type': 'close', 'code': 1008});
      return;
    }
    final decision = ListenSocketHostPolicy.prepare(
      path: path,
      baseUrl: baseUrl,
      token: custody.currentToken,
      clientIdentity: clientIdentity,
    );
    final prepared = decision.request;
    if (prepared == null) {
      await _emit(controller, id, const <String, Object>{'type': 'error'});
      await _emit(controller, id, const <String, Object>{'type': 'close', 'code': 1008});
      return;
    }
    try {
      final socket = await WebSocket.connect(prepared.url.toString(), headers: prepared.headers);
      _sockets[id] = socket;
      await _emit(controller, id, const <String, Object>{'type': 'open'});
      socket.listen(
        (dynamic data) {
          if (data is String) {
            final audio = evidenceAudioEnabled
                ? _evidenceGates.putIfAbsent(id, NativeListenEvidenceGate.new).acceptServiceFrame(data)
                : null;
            if (audio != null) {
              socket.add(audio);
            }
            unawaited(_emit(controller, id, <String, Object>{'type': 'message', 'data': data}));
          } else {
            unawaited(_emit(controller, id, const <String, Object>{'type': 'error'}));
          }
        },
        onError: (Object _) {
          unawaited(_emit(controller, id, const <String, Object>{'type': 'error'}));
        },
        onDone: () {
          _sockets.remove(id);
          _evidenceGates.remove(id);
          unawaited(_emit(controller, id, <String, Object>{'type': 'close', 'code': socket.closeCode ?? 1006}));
        },
        cancelOnError: false,
      );
    } catch (_) {
      await _emit(controller, id, const <String, Object>{'type': 'error'});
      await _emit(controller, id, const <String, Object>{'type': 'close', 'code': 1006});
    }
  }

  Future<bool> _listenPreflightReady() async {
    try {
      final value = await _preflightChannel.invokeMethod<Object?>('check');
      return value is Map && listenPreflightCanOpen(value.cast<Object?, Object?>());
    } on MissingPluginException {
      return false;
    } on PlatformException {
      return false;
    } catch (_) {
      return false;
    }
  }

  Future<void> _handlePreflight(WebViewController controller, String id, String operation) async {
    Map<String, Object?> payload;
    try {
      final method = switch (operation) {
        'check' => 'check',
        'request-permission' => 'requestPermission',
        'open-settings' => 'openSettings',
        _ => 'check',
      };
      final value = await _preflightChannel.invokeMethod<Object?>(method);
      payload = value is Map
          ? value.map((key, value) => MapEntry(key.toString(), value))
          : _unavailablePreflight;
    } on MissingPluginException {
      payload = _unavailablePreflight;
    } on PlatformException {
      payload = _unavailablePreflight;
    }
    final response = <String, Object?>{
      'type': 'preflight',
      'requestId': id,
      'permission': payload['permission'] ?? 'unavailable',
      'deviceState': payload['deviceState'] ?? 'unavailable',
      if (payload['deviceLabel'] is String) 'deviceLabel': payload['deviceLabel'],
      'recovery': payload['recovery'],
    };
    await _emit(controller, id, response, callback: '__omiListenPreflightEvent');
  }

  static const _unavailablePreflight = <String, Object?>{
    'permission': 'unavailable',
    'deviceState': 'unavailable',
    'deviceLabel': null,
    'recovery': null,
  };

  Future<void> _emit(
    WebViewController controller,
    String id,
    Map<String, Object?> payload, {
    String callback = '__omiListenSocketEvent',
  }) {
    return controller.runJavaScript('window.$callback?.(${jsonEncode(id)}, ${jsonEncode(payload)})');
  }

  Future<void> resetForNavigation() => _closeAll('surface navigation');

  Future<void> close() => _closeAll('shell teardown');

  Future<void> _closeAll(String reason) async {
    final sockets = _sockets.values.toList(growable: false);
    _sockets.clear();
    _evidenceGates.clear();
    await Future.wait(sockets.map((socket) => socket.close(WebSocketStatus.goingAway, reason)));
  }
}
