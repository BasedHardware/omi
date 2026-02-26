import 'dart:async';
import 'dart:convert';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

enum AgentChatEventType { textDelta, toolActivity, result, error, status }

class AgentChatEvent {
  final AgentChatEventType type;
  final String text;

  AgentChatEvent(this.type, this.text);
}

class AgentChatService {
  WebSocketChannel? _channel;
  StreamController<AgentChatEvent>? _eventController;
  bool _connected = false;

  bool get isConnected => _connected;

  Future<bool> connect() async {
    // Close any existing channel before opening a new one
    if (_channel != null) {
      try {
        await _channel!.sink.close();
      } catch (_) {}
      _channel = null;
    }
    _connected = false;

    final user = FirebaseAuth.instance.currentUser;
    final token = await user?.getIdToken();
    if (token == null) {
      print('[AgentChat] ERROR: no Firebase user/token');
      Logger.error('AgentChatService: no Firebase user');
      return false;
    }

    try {
      final uri = Uri.parse(Env.agentProxyWsUrl);
      print('[AgentChat] Connecting to $uri');
      _channel = IOWebSocketChannel.connect(
        uri,
        headers: {'Authorization': 'Bearer $token'},
        pingInterval: const Duration(seconds: 30),
      );
      await _channel!.ready;
      _connected = true;
      print('[AgentChat] Connected successfully');
      Logger.debug('AgentChatService: connected to agent proxy');
      return true;
    } catch (e) {
      print('[AgentChat] Connection failed: $e');
      Logger.error('AgentChatService: connection failed: $e');
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

    print('[AgentChat] Sending query (${prompt.length} chars)');
    _channel!.sink.add(jsonEncode({'type': 'query', 'prompt': prompt}));

    _channel!.stream.listen(
      (data) {
        try {
          final msg = jsonDecode(data as String) as Map<String, dynamic>;
          final type = msg['type'] as String?;
          final text = msg['text'] as String? ?? msg['content'] as String? ?? '';
          print('[AgentChat] Event: type=$type text=${text.length > 80 ? '${text.substring(0, 80)}...' : text}');

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
        print('[AgentChat] Stream error: $error');
        Logger.error('AgentChatService: stream error: $error');
        _eventController?.add(AgentChatEvent(AgentChatEventType.error, 'Connection error: $error'));
        _eventController?.close();
        _connected = false;
      },
      onDone: () {
        print('[AgentChat] Stream done (connection closed)');
        _connected = false;
        if (!(_eventController?.isClosed ?? true)) {
          _eventController?.close();
        }
      },
    );

    return _eventController!.stream;
  }

  Future<void> disconnect() async {
    _connected = false;
    _eventController?.close();
    _eventController = null;
    await _channel?.sink.close();
    _channel = null;
    Logger.debug('AgentChatService: disconnected');
  }

  Future<bool> reconnect() async {
    await disconnect();
    return connect();
  }

  static String _toolDisplayName(String toolName) {
    // Strip MCP prefix (e.g. "mcp__omi-tools__execute_sql" → "execute_sql")
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
