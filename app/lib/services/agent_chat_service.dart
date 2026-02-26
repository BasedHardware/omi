import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:firebase_auth/firebase_auth.dart';
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

enum AgentChatEventType { textDelta, toolActivity, result, error, status }

class AgentChatEvent {
  final AgentChatEventType type;
  final String text;

  AgentChatEvent(this.type, this.text);
}

class AgentChatService {
  WebSocketChannel? _channel;
  StreamSubscription? _streamSubscription;
  StreamController<AgentChatEvent>? _eventController;
  bool _connected = false;

  bool get isConnected => _connected;

  Future<bool> connect() async {
    await initAgentLog();
    agentLog('connect() called');

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
    agentLog('Firebase user: ${user?.uid}, email: ${user?.email}');
    final token = await user?.getIdToken();
    if (token == null) {
      agentLog('ERROR: no Firebase user/token');
      return false;
    }

    try {
      final uri = Uri.parse(Env.agentProxyWsUrl);
      agentLog('Connecting to $uri');
      _channel = IOWebSocketChannel.connect(
        uri,
        headers: {'Authorization': 'Bearer $token'},
        pingInterval: const Duration(seconds: 30),
      );
      await _channel!.ready;
      _connected = true;
      agentLog('Connected successfully');

      // Set up a persistent stream listener that forwards events to the current _eventController.
      // This listener survives across multiple sendQuery() calls on the same connection.
      _streamSubscription = _channel!.stream.listen(
        (data) {
          try {
            final msg = jsonDecode(data as String) as Map<String, dynamic>;
            final type = msg['type'] as String?;
            final text = msg['text'] as String? ?? msg['content'] as String? ?? '';
            agentLog('Event: type=$type text=${text.length > 80 ? '${text.substring(0, 80)}...' : text}');

            // Skip init/prewarm messages that arrive before or between queries
            if (type == 'init' || type == 'prewarm') return;

            if (_eventController == null || _eventController!.isClosed) return;

            switch (type) {
              case 'text_delta':
                _eventController?.add(AgentChatEvent(AgentChatEventType.textDelta, text));
                break;
              case 'tool_activity':
                final toolName = msg['name'] as String? ?? '';
                final status = msg['status'] as String? ?? 'started';
                final displayText = status == 'started' ? _toolDisplayName(toolName) : '';
                _eventController?.add(AgentChatEvent(AgentChatEventType.toolActivity, displayText));
                break;
              case 'status':
                final message = msg['message'] as String? ?? text;
                _eventController?.add(AgentChatEvent(AgentChatEventType.status, message));
                break;
              case 'result':
                _eventController?.add(AgentChatEvent(AgentChatEventType.result, text));
                _eventController?.close();
                break;
              case 'error':
                _eventController?.add(AgentChatEvent(AgentChatEventType.error, text));
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
          agentLog('Stream error: $error');
          _eventController?.add(AgentChatEvent(AgentChatEventType.error, 'Connection error: $error'));
          _eventController?.close();
          _connected = false;
        },
        onDone: () {
          agentLog('Stream done (connection closed)');
          _connected = false;
          if (!(_eventController?.isClosed ?? true)) {
            _eventController?.close();
          }
        },
      );

      // Trigger pre-warm on the VM so a Claude session is ready before the user types
      _channel!.sink.add(jsonEncode({'type': 'prewarm'}));
      agentLog('Sent prewarm signal');

      return true;
    } catch (e) {
      agentLog('Connection failed: $e');
      _connected = false;
      return false;
    }
  }

  Stream<AgentChatEvent> sendQuery(String prompt) {
    _eventController?.close();
    _eventController = StreamController<AgentChatEvent>();

    if (_channel == null || !_connected) {
      _eventController!.addError('Not connected to agent proxy');
      _eventController!.close();
      return _eventController!.stream;
    }

    agentLog('Sending query (${prompt.length} chars)');
    _channel!.sink.add(jsonEncode({'type': 'query', 'prompt': prompt}));

    return _eventController!.stream;
  }

  Future<void> disconnect() async {
    _connected = false;
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
