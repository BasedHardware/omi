import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import 'package:omi/utils/logger.dart';

enum AgentChatEventType { textDelta, toolActivity, result, error }

class AgentChatEvent {
  final AgentChatEventType type;
  final String text;

  AgentChatEvent(this.type, this.text);
}

class AgentChatService {
  WebSocketChannel? _channel;
  StreamController<AgentChatEvent>? _eventController;
  String? _ip;
  String? _authToken;
  bool _connected = false;

  bool get isConnected => _connected;

  Future<bool> connect(String ip, String authToken) async {
    _ip = ip;
    _authToken = authToken;
    try {
      final uri = Uri.parse('ws://$ip:8080/ws?token=$authToken');
      _channel = IOWebSocketChannel.connect(uri);
      await _channel!.ready;
      _connected = true;
      Logger.debug('AgentChatService: connected to $ip');
      return true;
    } catch (e) {
      Logger.error('AgentChatService: connection failed: $e');
      _connected = false;
      return false;
    }
  }

  Stream<AgentChatEvent> sendQuery(String prompt) {
    _eventController?.close();
    _eventController = StreamController<AgentChatEvent>();

    if (_channel == null || !_connected) {
      _eventController!.addError('Not connected to agent VM');
      _eventController!.close();
      return _eventController!.stream;
    }

    _channel!.sink.add(jsonEncode({'type': 'query', 'prompt': prompt}));

    _channel!.stream.listen(
      (data) {
        try {
          final msg = jsonDecode(data as String) as Map<String, dynamic>;
          final type = msg['type'] as String?;
          final text = msg['text'] as String? ?? msg['content'] as String? ?? '';

          switch (type) {
            case 'text_delta':
              _eventController?.add(AgentChatEvent(AgentChatEventType.textDelta, text));
              break;
            case 'tool_activity':
              _eventController?.add(AgentChatEvent(AgentChatEventType.toolActivity, text));
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
              // Treat unknown types as text deltas if they have content
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
        Logger.error('AgentChatService: stream error: $error');
        _eventController?.add(AgentChatEvent(AgentChatEventType.error, 'Connection error: $error'));
        _eventController?.close();
        _connected = false;
      },
      onDone: () {
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
    if (_ip != null && _authToken != null) {
      await disconnect();
      return connect(_ip!, _authToken!);
    }
    return false;
  }
}
