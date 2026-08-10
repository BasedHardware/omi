import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:webview_flutter/webview_flutter.dart';

import 'bridge_http_host.dart';
import 'chat_bridge_javascript_sink.dart';
import 'chat_native_http.dart';
import 'gen/bridge_http_contract.g.dart';

const int _maxSafeInteger = 9007199254740991;
final RegExp _safeOpaque = RegExp(r'^[\x21-\x7e]{1,1024}$');

bool _hasExactKeys(Map<String, dynamic> value, Set<String> expected) =>
    value.length == expected.length && value.keys.every(expected.contains);

bool _hasOptionalKeys(Map<String, dynamic> value, Set<String> allowed, Set<String> required) =>
    value.keys.every(allowed.contains) && required.every(value.containsKey);

bool _isPositiveCredit(Object? value) => value is int && value > 0 && value <= _maxSafeInteger;

class ChatStreamHost {
  ChatStreamHost({
    required this.baseUrl,
    required this.custody,
    required this.clientIdentity,
    required this.sink,
    ChatNativeHttpClient? httpClient,
  }) : _httpClient = httpClient ?? DartIoChatNativeHttpClient();

  final Uri baseUrl;
  final ShellCredentialCustody custody;
  final String? clientIdentity;
  final ChatBridgeJavaScriptSink sink;
  final ChatNativeHttpClient _httpClient;
  final Map<String, _ChatStreamSession> _sessions = <String, _ChatStreamSession>{};

  bool _registered = false;
  bool _closed = false;
  int _documentEpoch = 0;

  int get activeSessionCount => _sessions.length;

  Future<void> register(WebViewController controller) {
    if (_registered) return Future<void>.value();
    _registered = true;
    return controller.addJavaScriptChannel(
      BridgeStreamContract.messageChannel,
      onMessageReceived: (JavaScriptMessage message) {
        unawaited(handleMessage(message.message));
      },
    );
  }

  Future<void> handleMessage(String raw) async {
    if (_closed) return;
    dynamic decoded;
    try {
      decoded = jsonDecode(raw);
    } on FormatException {
      return;
    }
    if (decoded is! Map<String, dynamic>) return;
    final type = decoded['t'];
    final id = decoded['id'];
    final channel = decoded['channel'];
    if (type is! String || id is! String || channel is! String || !_safeOpaque.hasMatch(id)) {
      return;
    }

    if (type == BridgeStreamContract.openMessage) {
      await _open(decoded, id, channel);
      return;
    }
    final session = _sessions[id];
    if (session == null || channel != BridgeStreamContract.chatGenerationChannel) {
      return;
    }
    if (type == BridgeStreamContract.grantMessage) {
      final fields = BridgeStreamContract.toShellFields[BridgeStreamContract.grantMessage]!;
      if (!_hasExactKeys(decoded, fields) || !_isPositiveCredit(decoded['credit'])) {
        return;
      }
      session.grant(decoded['credit'] as int);
      return;
    }
    if (type == BridgeStreamContract.cancelMessage) {
      final fields = BridgeStreamContract.toShellFields[BridgeStreamContract.cancelMessage]!;
      if (!_hasOptionalKeys(decoded, fields, fields.difference(const {'reason'}))) {
        return;
      }
      final reason = decoded['reason'];
      if (reason != null && (reason is! String || reason.length > 1024)) return;
      await session.cancel();
    }
  }

  Future<void> _open(Map<String, dynamic> frame, String id, String channel) async {
    if (_sessions.containsKey(id)) return;
    if (channel != BridgeStreamContract.chatGenerationChannel) {
      await _emitError(id, 'invalid-request', _documentEpoch, channel: channel);
      return;
    }
    final fields = BridgeStreamContract.toShellFields[BridgeStreamContract.openMessage]!;
    if (!_hasExactKeys(frame, fields) || !_isPositiveCredit(frame['credit']) || frame['params'] is! String) {
      await _emitError(id, 'invalid-request', _documentEpoch);
      return;
    }
    dynamic decodedParams;
    try {
      decodedParams = jsonDecode(frame['params'] as String);
    } on FormatException {
      await _emitError(id, 'invalid-request', _documentEpoch);
      return;
    }
    if (decodedParams is! Map<String, dynamic> ||
        !_hasOptionalKeys(decodedParams, BridgeStreamContract.chatGenerationParameterFields, const {'generationId'})) {
      await _emitError(id, 'invalid-request', _documentEpoch);
      return;
    }
    final generationId = decodedParams['generationId'];
    final lastEventId = decodedParams['lastEventId'];
    if (generationId is! String ||
        !_safeOpaque.hasMatch(generationId) ||
        (lastEventId != null && (lastEventId is! String || !_safeOpaque.hasMatch(lastEventId)))) {
      await _emitError(id, 'invalid-request', _documentEpoch);
      return;
    }
    final token = custody.currentToken;
    if (token == null) {
      await _emitError(id, 'not-authenticated', _documentEpoch);
      return;
    }
    final session = _ChatStreamSession(
      host: this,
      id: id,
      generationId: generationId,
      lastEventId: lastEventId as String?,
      credit: frame['credit'] as int,
      token: token,
      epoch: _documentEpoch,
      documentGeneration: sink.generation,
    );
    _sessions[id] = session;
    unawaited(session.start());
  }

  Uri _eventsUrl(String generationId) =>
      baseUrl.resolve('/v1/chat-generations/${Uri.encodeComponent(generationId)}/events');

  bool _isCurrent(_ChatStreamSession session) =>
      !_closed && session.epoch == _documentEpoch && identical(_sessions[session.id], session);

  void _retire(_ChatStreamSession session) {
    if (identical(_sessions[session.id], session)) _sessions.remove(session.id);
  }

  Future<void> _emitData(_ChatStreamSession session, String payload) async {
    if (!_isCurrent(session)) return;
    await sink.streamFrame(<String, Object>{
      't': BridgeStreamContract.dataMessage,
      'id': session.id,
      'channel': BridgeStreamContract.chatGenerationChannel,
      'payload': payload,
    }, generation: session.documentGeneration);
  }

  Future<void> _emitEnd(_ChatStreamSession session) async {
    if (_closed || session.epoch != _documentEpoch) return;
    await sink.streamFrame(<String, Object>{
      't': BridgeStreamContract.endMessage,
      'id': session.id,
      'channel': BridgeStreamContract.chatGenerationChannel,
    }, generation: session.documentGeneration);
  }

  Future<void> _emitError(String id, String failure, int epoch, {String? channel, int? documentGeneration}) async {
    if (_closed || epoch != _documentEpoch) return;
    await sink.streamFrame(<String, Object>{
      't': BridgeStreamContract.errorMessage,
      'id': id,
      'channel': channel ?? BridgeStreamContract.chatGenerationChannel,
      'failure': failure,
    }, generation: documentGeneration ?? sink.generation);
  }

  Future<void> resetForNavigation() async {
    sink.resetForNavigation();
    _documentEpoch += 1;
    final sessions = _sessions.values.toList(growable: false);
    _sessions.clear();
    await Future.wait(sessions.map((session) => session.cancel()));
  }

  Future<void> close() async {
    if (_closed) return;
    _closed = true;
    sink.close();
    _documentEpoch += 1;
    final sessions = _sessions.values.toList(growable: false);
    _sessions.clear();
    await Future.wait(sessions.map((session) => session.cancel()));
    _httpClient.close(force: true);
  }
}

class _ChatStreamSession {
  _ChatStreamSession({
    required this.host,
    required this.id,
    required this.generationId,
    required this.lastEventId,
    required this.credit,
    required this.token,
    required this.epoch,
    required this.documentGeneration,
  });

  final ChatStreamHost host;
  final String id;
  final String generationId;
  final String? lastEventId;
  final String token;
  final int epoch;
  final int documentGeneration;
  int credit;

  ChatNativeHttpRequest? _request;
  StreamSubscription<String>? _subscription;
  bool _deliveryInFlight = false;
  bool _terminal = false;

  Future<void> start() async {
    try {
      final request = await host._httpClient.openUrl('GET', host._eventsUrl(generationId));
      _request = request;
      if (!host._isCurrent(this)) {
        request.abort();
        return;
      }
      request.followRedirects = false;
      request.setHeader(HttpHeaders.authorizationHeader, 'Bearer $token');
      request.setHeader(AppRequestContract.versionHeader, AppRequestContract.version);
      if (host.clientIdentity != null) {
        request.setHeader(BridgeHttpHostPolicy.clientIdHeader, host.clientIdentity!);
      }
      if (lastEventId != null) request.setHeader('Last-Event-ID', lastEventId!);
      final response = await request.close().timeout(const Duration(seconds: 12));
      if (!host._isCurrent(this)) {
        await response.bytes.listen(null).cancel();
        return;
      }
      if (response.isRedirect || response.statusCode != HttpStatus.ok) {
        await response.bytes.listen(null).cancel();
        await fail('http-status');
        return;
      }
      if (!responseHasMediaType(response.contentType, 'text/event-stream')) {
        await response.bytes.listen(null).cancel();
        await fail('transport-error');
        return;
      }
      late final StreamSubscription<String> subscription;
      subscription = response.bytes
          .transform(const Utf8Decoder())
          .listen(
            (String payload) {
              subscription.pause();
              _deliveryInFlight = true;
              credit -= 1;
              unawaited(_deliver(payload));
            },
            onError: (Object _, StackTrace _) {
              unawaited(fail('transport-error'));
            },
            onDone: () {
              unawaited(end());
            },
            cancelOnError: true,
          );
      _subscription = subscription;
      if (credit == 0) subscription.pause();
    } on TimeoutException {
      await fail('transport-error');
    } on SocketException {
      await fail('transport-error');
    } on HttpException {
      await fail('transport-error');
    } catch (_) {
      await fail('transport-error');
    }
  }

  Future<void> _deliver(String payload) async {
    try {
      if (!_terminal && payload.isNotEmpty) await host._emitData(this, payload);
    } catch (_) {
      await cancel();
      return;
    } finally {
      _deliveryInFlight = false;
    }
    if (!_terminal && credit > 0) _subscription?.resume();
  }

  void grant(int count) {
    if (_terminal) return;
    if (credit > _maxSafeInteger - count) {
      unawaited(fail('invalid-request'));
      return;
    }
    credit += count;
    if (!_deliveryInFlight) _subscription?.resume();
  }

  Future<void> end() async {
    if (_terminal) return;
    _terminal = true;
    host._retire(this);
    await host._emitEnd(this);
  }

  Future<void> fail(String failure) async {
    if (_terminal) return;
    _terminal = true;
    host._retire(this);
    _request?.abort();
    await _subscription?.cancel();
    await host._emitError(id, failure, epoch, documentGeneration: documentGeneration);
  }

  Future<void> cancel() async {
    if (_terminal) return;
    _terminal = true;
    host._retire(this);
    _request?.abort();
    await _subscription?.cancel();
  }
}
