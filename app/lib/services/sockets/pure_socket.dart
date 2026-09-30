import 'dart:async';
import 'dart:io';

import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/status.dart' as socket_channel_status;
import 'package:web_socket_channel/web_socket_channel.dart';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_manager.dart';

enum PureSocketStatus { notConnected, connecting, connected, disconnected }

abstract class IPureSocketListener {
  void onConnected();
  void onMessage(dynamic message);
  void onClosed([int? closeCode]);
  void onError(Object err, StackTrace trace);
}

abstract class IPureSocket {
  PureSocketStatus get status;

  Future<bool> connect();
  Future disconnect();
  Future stop();
  void send(dynamic message);

  void setListener(IPureSocketListener listener);

  void onMessage(dynamic message);
  void onConnected();
  void onClosed();
  void onError(Object err, StackTrace trace);
}

class PureSocketMessage {
  String? raw;
}

typedef SocketHeadersProvider = Future<Map<String, String>> Function();

class PureSocket implements IPureSocket {
  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _subscription;
  int _connectionGeneration = 0;
  WebSocketChannel get channel {
    if (_channel == null) {
      throw Exception('Socket is not connected');
    }
    return _channel!;
  }

  PureSocketStatus _status = PureSocketStatus.notConnected;
  @override
  PureSocketStatus get status => _status;

  IPureSocketListener? _listener;

  String url;
  final SocketHeadersProvider _headersProvider;
  final Map<String, String> _extraHeaders;

  PureSocket(this.url, {SocketHeadersProvider? headersProvider, Map<String, String> extraHeaders = const {}})
      : _headersProvider =
            headersProvider ?? (() => buildHeaders(requireAuthCheck: true, url: url, forWebSocket: true)),
        _extraHeaders = Map.unmodifiable(extraHeaders);

  @override
  void setListener(IPureSocketListener listener) {
    _listener = listener;
  }

  @override
  Future<bool> connect() async {
    if (_status == PureSocketStatus.connecting || _status == PureSocketStatus.connected) {
      return false;
    }

    // Reserve the attempt before auth can yield. Teardown invalidates both
    // auth and transport readiness, so neither can revive a retired session.
    final generation = ++_connectionGeneration;
    _status = PureSocketStatus.connecting;
    Logger.debug("request wss $url");
    final Map<String, String> headers;
    try {
      headers = {...await _headersProvider(), ..._extraHeaders};
    } on AuthTokenUnavailableException catch (e) {
      Logger.debug('[Socket] Connect blocked before send: ${e.result.runtimeType}');
      if (generation == _connectionGeneration) _status = PureSocketStatus.notConnected;
      return false;
    } catch (_) {
      if (generation == _connectionGeneration) _status = PureSocketStatus.notConnected;
      rethrow;
    }
    if (generation != _connectionGeneration) return false;

    final channel = IOWebSocketChannel.connect(
      url,
      headers: headers,
      pingInterval: const Duration(seconds: 20),
      connectTimeout: const Duration(seconds: 15),
    );
    _channel = channel;
    // Consume connection errors even when this attempt has been retired.
    _subscription = channel.stream.listen(
      (message) {
        if (generation != _connectionGeneration) return;
        if (message == "ping") {
          // Logger.debug(message);
          // Pong frame added manually https://www.rfc-editor.org/rfc/rfc6455#section-5.5.2
          channel.sink.add([0x8A, 0x00]);
          return;
        }
        onMessage(message);
      },
      onError: (err, trace) {
        // Handshake failures are handled by ready below, without emitting a
        // second failure through the established-connection listener.
        if (generation == _connectionGeneration && _status == PureSocketStatus.connected) onError(err, trace);
      },
      onDone: () {
        if (generation != _connectionGeneration) return;
        Logger.debug("onDone with close code: ${channel.closeCode}");
        onClosed(channel.closeCode);
      },
      cancelOnError: true,
    );

    dynamic err;
    try {
      await channel.ready;
    } on TimeoutException catch (e) {
      err = e;
      DebugLogManager.logWarning('pure_socket_connect_timeout', {'url': url, 'error': e.toString()});
    } on SocketException catch (e) {
      err = e;
      DebugLogManager.logWarning('pure_socket_connect_socket_error', {'url': url, 'error': e.toString()});
    } on WebSocketChannelException catch (e) {
      err = e;
      DebugLogManager.logWarning('pure_socket_connect_websocket_error', {'url': url, 'error': e.toString()});
    }
    if (generation != _connectionGeneration) return false;
    if (err != null) {
      Logger.debug("[Socket] Connect error: $err");
      _retireChannel();
      _status = PureSocketStatus.notConnected;
      return false;
    }
    _status = PureSocketStatus.connected;
    DebugLogManager.logEvent('pure_socket_connected', {'url': url});
    onConnected();

    return generation == _connectionGeneration;
  }

  void _retireChannel() {
    _connectionGeneration++;
    final channel = _channel;
    final subscription = _subscription;
    _channel = null;
    _subscription = null;
    // Close even while connecting; the adapter delivers the queued close
    // when its handshake finishes. Never wait for a peer acknowledgement.
    if (channel != null) unawaited(channel.sink.close(socket_channel_status.normalClosure));
    if (subscription != null) unawaited(subscription.cancel());
  }

  @override
  Future disconnect() async {
    DebugLogManager.logEvent('pure_socket_disconnecting', {'url': url, 'current_status': _status.toString()});
    if (_status == PureSocketStatus.disconnected && _channel == null) return;
    Logger.debug("[Socket] disconnect");
    onClosed(_channel?.closeCode);
  }

  @override
  Future stop() async {
    DebugLogManager.logEvent('pure_socket_stopping', {'url': url});
    await disconnect();
  }

  @override
  void onClosed([int? closeCode]) {
    _status = PureSocketStatus.disconnected;
    _retireChannel();
    final closeReason = _getCloseCodeReason(closeCode);
    Logger.debug("Socket closed with code: $closeCode ($closeReason)");

    DebugLogManager.logEvent('pure_socket_closed', {
      'close_code': closeCode ?? -1,
      'close_reason': closeReason,
      'url': url,
    });

    _listener?.onClosed(closeCode);
  }

  String _getCloseCodeReason(int? code) {
    switch (code) {
      case 1000:
        return 'normal_closure';
      case 1001:
        return 'going_away_os_or_background';
      case 1006:
        return 'abnormal_closure';
      case 1008:
        return 'policy_violation_or_auth_error';
      case 1011:
        return 'server_error';
      case 4001:
        return 'auth_token_refresh_required';
      case 4004:
        return 'auth_relogin_required';
      default:
        return 'unknown';
    }
  }

  @override
  void onError(Object err, StackTrace trace) {
    _status = PureSocketStatus.disconnected;
    _retireChannel();
    Logger.debug("[Socket] Error: $err");

    DebugLogManager.logError(err, trace, 'pure_socket_error', {'url': url});

    _listener?.onError(err, trace);
    PlatformManager.instance.crashReporter.reportCrash(err, trace);
  }

  @override
  void onMessage(dynamic message) {
    // Logger.debug("[Socket] Message $message");
    _listener?.onMessage(message);
  }

  @override
  void onConnected() {
    _listener?.onConnected();
  }

  @override
  void send(message) {
    _channel?.sink.add(message);
  }
}
