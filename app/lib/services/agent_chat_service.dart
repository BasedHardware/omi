import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter_timezone/flutter_timezone.dart';
import 'package:path_provider/path_provider.dart';
import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

/// File-based logging for agent chat — works in release builds (print/developer.log are stripped).
/// Pull with: pymobiledevice3 apps pull com.friend-app-with-wearable.ios12 Documents/agent_chat.log /tmp/agent_chat.log
File? agentLogFile;

Future<void> initAgentLog() async {
  if (agentLogFile != null) return;
  final dir = await getApplicationDocumentsDirectory();
  agentLogFile = File('${dir.path}/agent_chat.log');
}

void agentLog(String msg) {
  final line = '${DateTime.now().toIso8601String()} $msg';
  print('[AgentChat] $msg');
  try {
    agentLogFile?.writeAsStringSync('$line\n', mode: FileMode.append, flush: true);
  } catch (_) {}
}

Map<String, String> buildAgentWebSocketHeaders({required String token, String? timeZone}) {
  final headers = <String, String>{'Authorization': 'Bearer $token'};
  final normalizedTimeZone = timeZone?.trim();
  if (normalizedTimeZone != null && normalizedTimeZone.isNotEmpty) {
    headers['X-Timezone'] = normalizedTimeZone;
  }
  return headers;
}

Map<String, dynamic> buildAgentQueryMessage({required String prompt, String? timeZone}) {
  final normalizedTimeZone = timeZone?.trim();
  return {
    'type': 'query',
    'prompt': prompt,
    // An explicit empty value tells the proxy to use UTC when a per-query
    // timezone lookup fails; it must not silently reuse a stale handshake zone.
    'time_zone': normalizedTimeZone ?? '',
  };
}

Future<String?> _resolveLocalTimezone() async {
  try {
    final timeZone = await FlutterTimezone.getLocalTimezone();
    final normalizedTimeZone = timeZone.trim();
    return normalizedTimeZone.isEmpty ? null : normalizedTimeZone;
  } catch (e) {
    agentLog('Unable to resolve local timezone; agent proxy will use UTC: $e');
    return null;
  }
}

enum AgentChatEventType { textDelta, toolActivity, result, error, status }

class AgentChatEvent {
  final AgentChatEventType type;
  final String text;
  final String? code;
  final String? state;
  final bool? retryable;

  AgentChatEvent(this.type, this.text, {this.code, this.state, this.retryable});

  static String textFrom(Map<String, dynamic> message) =>
      message['text'] as String? ?? message['content'] as String? ?? message['message'] as String? ?? '';

  static AgentChatEvent fromMessage(AgentChatEventType type, Map<String, dynamic> message) => AgentChatEvent(
        type,
        textFrom(message),
        code: message['code'] as String?,
        state: message['state'] as String?,
        retryable: message['retryable'] as bool?,
      );
}

class AgentChatService {
  WebSocketChannel? _channel;
  StreamSubscription? _streamSubscription;
  StreamController<AgentChatEvent>? _eventController;
  bool _connected = false;
  Stopwatch? _queryStopwatch;
  bool _firstTextReceived = false;
  Timer? _responseTimer;
  final List<AgentChatEvent> _pendingStartupEvents = [];

  bool get isConnected => _connected;

  Future<bool> connect() async {
    await initAgentLog();
    final connectSw = Stopwatch()..start();
    agentLog('connect() called');
    // Startup events describe a specific socket. Never let an error from an
    // earlier connection abort a query after a successful reconnect.
    _pendingStartupEvents.clear();

    // Clean up any existing connection
    await _streamSubscription?.cancel();
    _streamSubscription = null;
    if (_channel != null) {
      try {
        await _channel!.sink.close();
      } catch (_) {}
      _channel = null;
    }
    _connected = false;

    final user = FirebaseAuth.instance.currentUser;
    agentLog('[TIMING] cleanup done +${connectSw.elapsedMilliseconds}ms');
    final token = await user?.getIdToken();
    if (token == null) {
      agentLog('ERROR: no Firebase user/token');
      return false;
    }
    agentLog('[TIMING] token fetched +${connectSw.elapsedMilliseconds}ms');

    try {
      final uri = Uri.parse(Env.agentProxyWsUrl);
      final timeZone = await _resolveLocalTimezone();
      agentLog('Connecting to $uri');
      _channel = IOWebSocketChannel.connect(
        uri,
        headers: buildAgentWebSocketHeaders(token: token, timeZone: timeZone),
        pingInterval: const Duration(seconds: 30),
      );
      await _channel!.ready;
      _connected = true;
      agentLog('[TIMING] ws connected +${connectSw.elapsedMilliseconds}ms');

      // Set up a persistent stream listener that forwards events to the current _eventController.
      // This listener survives across multiple sendQuery() calls on the same connection.
      _streamSubscription = _channel!.stream.listen(
        (data) {
          try {
            final msg = jsonDecode(data as String) as Map<String, dynamic>;
            final type = msg['type'] as String?;
            final text = AgentChatEvent.textFrom(msg);
            final elapsed = _queryStopwatch?.elapsedMilliseconds ?? 0;
            agentLog(
              '[TIMING] Event: type=$type +${elapsed}ms | text=${text.length > 80 ? '${text.substring(0, 80)}...' : text}',
            );

            // Skip init/prewarm messages that arrive before or between queries
            if (type == 'init' || type == 'prewarm' || type == 'prewarm_ack') return;

            // Log thinking_done timing (VM tells us how long Claude spent thinking)
            if (type == 'thinking_done') {
              final thinkingMs = msg['thinkingMs'] as int? ?? 0;
              agentLog('[TIMING] *** THINKING DONE *** +${elapsed}ms (VM thinking: ${thinkingMs}ms)');
              return;
            }

            if (_eventController == null || _eventController!.isClosed) {
              if (type == 'status') {
                _pendingStartupEvents.add(AgentChatEvent.fromMessage(AgentChatEventType.status, msg));
              } else if (type == 'error') {
                _pendingStartupEvents.add(AgentChatEvent.fromMessage(AgentChatEventType.error, msg));
                _connected = false;
              }
              return;
            }

            // Reset response timeout on every incoming event
            _resetResponseTimer();

            switch (type) {
              case 'text_delta':
                if (!_firstTextReceived) {
                  _firstTextReceived = true;
                  agentLog('[TIMING] *** FIRST TEXT DELTA *** +${elapsed}ms');
                }
                _eventController?.add(AgentChatEvent(AgentChatEventType.textDelta, text));
                break;
              case 'tool_activity':
                final toolName = msg['name'] as String? ?? '';
                final status = msg['status'] as String? ?? 'started';
                agentLog('[TIMING] tool=$toolName status=$status +${elapsed}ms');
                final displayText = status == 'started' ? _toolDisplayName(toolName) : '';
                _eventController?.add(AgentChatEvent(AgentChatEventType.toolActivity, displayText));
                break;
              case 'status':
                final message = msg['message'] as String? ?? text;
                _eventController?.add(AgentChatEvent(AgentChatEventType.status, message));
                break;
              case 'result':
                agentLog('[TIMING] *** RESULT *** +${elapsed}ms (total query time)');
                _queryStopwatch?.stop();
                _responseTimer?.cancel();
                _eventController?.add(AgentChatEvent(AgentChatEventType.result, text));
                _eventController?.close();
                break;
              case 'error':
                agentLog('[TIMING] *** ERROR *** +${elapsed}ms');
                _queryStopwatch?.stop();
                _responseTimer?.cancel();
                _eventController?.add(AgentChatEvent.fromMessage(AgentChatEventType.error, msg));
                _eventController?.close();
                break;
              default:
                if (text.isNotEmpty) {
                  _eventController?.add(AgentChatEvent(AgentChatEventType.textDelta, text));
                }
            }
          } catch (e) {
            Logger.error('AgentChatService: parse error: $e');
            _eventController?.add(AgentChatEvent(AgentChatEventType.error, 'Failed to parse agent response'));
            _eventController?.close();
          }
        },
        onError: (error) {
          final elapsed = _queryStopwatch?.elapsedMilliseconds ?? 0;
          agentLog('[TIMING] Stream error +${elapsed}ms: $error');
          _queryStopwatch?.stop();
          _eventController?.add(AgentChatEvent(AgentChatEventType.error, 'Connection error: $error'));
          _eventController?.close();
          _connected = false;
        },
        onDone: () {
          final elapsed = _queryStopwatch?.elapsedMilliseconds ?? 0;
          agentLog('[TIMING] Stream done +${elapsed}ms');
          _queryStopwatch?.stop();
          _connected = false;
          if (!(_eventController?.isClosed ?? true)) {
            _eventController?.close();
          }
        },
      );

      // Trigger pre-warm on the VM so a Claude session is ready before the user types
      _channel!.sink.add(jsonEncode({'type': 'prewarm'}));
      agentLog('[TIMING] prewarm sent +${connectSw.elapsedMilliseconds}ms (total connect)');

      return true;
    } catch (e) {
      agentLog('Connection failed after ${connectSw.elapsedMilliseconds}ms: $e');
      _connected = false;
      return false;
    }
  }

  Stream<AgentChatEvent> sendQuery(String prompt) {
    _eventController?.close();
    _eventController = StreamController<AgentChatEvent>();

    if (_pendingStartupEvents.isNotEmpty) {
      final pending = List<AgentChatEvent>.of(_pendingStartupEvents);
      _pendingStartupEvents.clear();
      for (final event in pending) {
        _eventController!.add(event);
      }
      if (pending.any((event) => event.type == AgentChatEventType.error)) {
        _eventController!.close();
        return _eventController!.stream;
      }
    }

    if (_channel == null || !_connected) {
      _eventController!.addError('Not connected to agent proxy');
      _eventController!.close();
      return _eventController!.stream;
    }

    _queryStopwatch = Stopwatch()..start();
    _firstTextReceived = false;
    agentLog('[TIMING] === QUERY START === (${prompt.length} chars)');
    final controller = _eventController!;
    unawaited(_sendQueryWithCurrentTimezone(prompt, controller));

    return _eventController!.stream;
  }

  Future<void> _sendQueryWithCurrentTimezone(String prompt, StreamController<AgentChatEvent> controller) async {
    final timeZone = await _resolveLocalTimezone();
    if (_eventController != controller || controller.isClosed || _channel == null || !_connected) return;

    _channel!.sink.add(jsonEncode(buildAgentQueryMessage(prompt: prompt, timeZone: timeZone)));
    agentLog('[TIMING] query sent +${_queryStopwatch?.elapsedMilliseconds ?? 0}ms');

    // Start response timeout — if no event arrives within 120s, connection is dead.
    _resetResponseTimer();
  }

  Future<void> disconnect() async {
    _connected = false;
    _pendingStartupEvents.clear();
    _responseTimer?.cancel();
    _eventController?.close();
    _eventController = null;
    await _streamSubscription?.cancel();
    _streamSubscription = null;
    await _channel?.sink.close();
    _channel = null;
  }

  Future<bool> reconnect() async {
    await disconnect();
    return connect();
  }

  void _resetResponseTimer() {
    _responseTimer?.cancel();
    _responseTimer = Timer(const Duration(seconds: 120), () {
      agentLog('[TIMING] *** RESPONSE TIMEOUT *** — no event received in 120s');
      _queryStopwatch?.stop();
      _connected = false;
      if (_eventController != null && !_eventController!.isClosed) {
        _eventController!.add(AgentChatEvent(AgentChatEventType.error, 'Connection timed out'));
        _eventController!.close();
      }
    });
  }

  static String _toolDisplayName(String toolName) {
    final cleanName = toolName.startsWith('mcp__') ? toolName.split('__').last : toolName;
    switch (cleanName) {
      case 'execute_sql':
        return 'Querying database';
      case 'semantic_search':
        return 'Searching conversations';
      case 'Read':
        return 'Reading file';
      case 'Write':
        return 'Writing file';
      case 'Edit':
        return 'Editing file';
      case 'Bash':
        return 'Running command';
      case 'Grep':
        return 'Searching code';
      case 'Glob':
        return 'Finding files';
      case 'WebSearch':
        return 'Searching the web';
      case 'WebFetch':
        return 'Fetching page';
      default:
        return cleanName.isNotEmpty ? 'Using $cleanName' : 'Thinking';
    }
  }
}
