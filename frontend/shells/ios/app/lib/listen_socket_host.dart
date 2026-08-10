import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:webview_flutter/webview_flutter.dart';

import 'bridge_http_host.dart';

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

  ListenSocketHost makeListenHost() => ListenSocketHost(baseUrl: baseUrl, custody: custody);

  ListenSocketPolicyResult prepareListen(String path) =>
      ListenSocketHostPolicy.prepare(path: path, baseUrl: baseUrl, token: custody.currentToken);
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
  static ListenSocketPolicyResult prepare({required String path, required Uri baseUrl, required String? token}) {
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
        headers: <String, String>{HttpHeaders.authorizationHeader: 'Bearer $token'},
      ),
    );
  }
}

class ListenSocketHost {
  ListenSocketHost({required this.baseUrl, required this.custody});

  static const channel = 'omiListenSocket';

  final Uri baseUrl;
  final ShellCredentialCustody custody;
  final Map<String, WebSocket> _sockets = <String, WebSocket>{};

  ListenSocketPolicyResult prepareUsingCurrentCustodyForConformance(String path) =>
      ListenSocketHostPolicy.prepare(path: path, baseUrl: baseUrl, token: custody.currentToken);

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
    if (action == 'close') {
      final code = decoded['code'] is int ? decoded['code'] as int : WebSocketStatus.normalClosure;
      final reason = decoded['reason'] is String ? decoded['reason'] as String : null;
      await _sockets.remove(id)?.close(code, reason);
      return;
    }
    final path = decoded['path'];
    if (action != 'open' || path is! String) return;
    final decision = ListenSocketHostPolicy.prepare(path: path, baseUrl: baseUrl, token: custody.currentToken);
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
          unawaited(_emit(controller, id, <String, Object>{'type': 'close', 'code': socket.closeCode ?? 1006}));
        },
        cancelOnError: false,
      );
    } catch (_) {
      await _emit(controller, id, const <String, Object>{'type': 'error'});
      await _emit(controller, id, const <String, Object>{'type': 'close', 'code': 1006});
    }
  }

  Future<void> _emit(WebViewController controller, String id, Map<String, Object> payload) {
    return controller.runJavaScript('window.__omiListenSocketEvent?.(${jsonEncode(id)}, ${jsonEncode(payload)})');
  }

  Future<void> close() async {
    final sockets = _sockets.values.toList(growable: false);
    _sockets.clear();
    await Future.wait(sockets.map((socket) => socket.close(WebSocketStatus.goingAway, 'shell teardown')));
  }
}
