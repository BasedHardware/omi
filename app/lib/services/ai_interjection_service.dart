import 'dart:async';
import 'dart:convert';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/voice_playback/omi_voice_playback_service.dart';
import 'package:omi/utils/logger.dart';

class AiInterjectionService {
  AiInterjectionService._();
  static final AiInterjectionService instance = AiInterjectionService._();

  WebSocketChannel? _channel;
  StreamSubscription? _streamSubscription;
  StreamController<String>? _eventController;
  bool _connected = false;

  String _recentTranscript = '';
  Timer? _pauseTimer;
  Timer? _cooldownTimer;
  bool _isQuerying = false;
  bool _isSpeaking = false;
  bool _isInCooldown = false;

  static const _pauseDuration = Duration(seconds: 3);
  static const _interjectionCooldown = Duration(seconds: 30);
  static const _minTranscriptChars = 40;
  static const _maxTranscriptChars = 500;
  bool get isConnected => _connected;
  bool get isActive => SharedPreferencesUtil().aiInterjectionEnabled;
  bool get isQuerying => _isQuerying;
  bool get isInCooldown => _isInCooldown;

  void onTranscriptChanged(String fullTranscript) {
    if (!isActive) return;
    if (_isQuerying || _isSpeaking || _isInCooldown) return;

    final recent = _getRecentText(fullTranscript);
    if (recent.length < _minTranscriptChars) return;

    if (recent != _recentTranscript) {
      _recentTranscript = recent;
      _pauseTimer?.cancel();
      _pauseTimer = Timer(_pauseDuration, () => _onPauseDetected());
    }
  }

  String _getRecentText(String full) {
    final lines = full.split('\n');
    final recent = <String>[];
    int charCount = 0;
    for (int i = lines.length - 1; i >= 0; i--) {
      final line = lines[i].trim();
      if (line.isEmpty) continue;
      recent.add(line);
      charCount += line.length;
      if (charCount > _maxTranscriptChars) break;
    }
    return recent.reversed.join(' ');
  }

  String _sanitizeTranscript(String transcript) {
    return transcript
        .replaceAll('\n', ' ')
        .replaceAll('\r', ' ')
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
  }

  void _onPauseDetected() {
    if (!isActive || _isQuerying || _isSpeaking || _isInCooldown) return;

    final text = _recentTranscript;
    if (text.length < _minTranscriptChars) return;

    _queryAi(text);
  }

  Future<void> _queryAi(String context) async {
    _isQuerying = true;
    try {
      final response = await _sendToAgent(context);
      if (response != null && response.isNotEmpty) {
        _isSpeaking = true;
        final messageId = 'interjection_${DateTime.now().millisecondsSinceEpoch}';
        await OmiVoicePlaybackService.instance.beginResponse(messageId: messageId);
        OmiVoicePlaybackService.instance.updateStreamingResponse(
          messageId: messageId,
          fullText: response,
          isFinal: true,
        );
        await Future.delayed(const Duration(seconds: 2));
        _isSpeaking = false;
      }
    } catch (e) {
      Logger.error('AiInterjection: query failed: $e');
    } finally {
      _isQuerying = false;
      _recentTranscript = '';
      _cooldownTimer?.cancel();
      _isInCooldown = true;
      _cooldownTimer = Timer(_interjectionCooldown, () {
        _isInCooldown = false;
      });
    }
  }

  Future<String?> _sendToAgent(String userText) async {
    await _ensureConnected();
    if (!_connected) return null;

    final completer = Completer<String?>();
    final textBuffer = StringBuffer();

    _streamSubscription = _channel!.stream.listen(
      (data) {
        try {
          final msg = jsonDecode(data as String) as Map<String, dynamic>;
          final type = msg['type'] as String?;
          final text = msg['text'] as String? ?? msg['content'] as String? ?? '';

          switch (type) {
            case 'text_delta':
              textBuffer.write(text);
              break;
            case 'result':
              textBuffer.write(text);
              if (!completer.isCompleted) {
                completer.complete(textBuffer.toString());
              }
              break;
            case 'error':
              if (!completer.isCompleted) {
                completer.complete(textBuffer.toString().isNotEmpty ? textBuffer.toString() : null);
              }
              break;
          }
        } catch (_) {}
      },
      onError: (error) {
        if (!completer.isCompleted) completer.complete(null);
      },
      onDone: () {
        if (!completer.isCompleted) {
          completer.complete(textBuffer.toString().isNotEmpty ? textBuffer.toString() : null);
        }
      },
    );

    final sanitizedTranscript = _sanitizeTranscript(userText);

    final prompt = '''{
  "role": "system",
  "content": "You are an AI assistant integrated into a wearable device that hears the user's speech in real-time. The user is monologuing - thinking out loud. Decide if you should interject with a thoughtful prompt, question, or insight. If the user's train of thought would benefit from your input, respond concisely (1-3 sentences). If they're just narrating mundane activities or if you have nothing valuable to add, respond with an empty string. Only respond with actual text if you have something useful to say."
}
{
  "role": "user",
  "content": "Recent transcript:\\n$sanitizedTranscript"
}''';

    _channel!.sink.add(jsonEncode({'type': 'query', 'prompt': prompt}));
    _resetResponseTimer();

    return completer.future.timeout(const Duration(seconds: 15), onTimeout: () => null);
  }

  Timer? _responseTimer;

  void _resetResponseTimer() {
    _responseTimer?.cancel();
    _responseTimer = Timer(const Duration(seconds: 20), () {
      _streamSubscription?.cancel();
      _connected = false;
    });
  }

  Future<void> _ensureConnected() async {
    if (_connected) return;
    await connect();
  }

  Future<bool> connect() async {
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
    final token = await user?.getIdToken();
    if (token == null) return false;

    try {
      final uri = Uri.parse(Env.agentProxyWsUrl);
      _channel = IOWebSocketChannel.connect(
        uri,
        headers: {'Authorization': 'Bearer $token'},
        pingInterval: const Duration(seconds: 30),
      );
      await _channel!.ready;
      _connected = true;
      _channel!.sink.add(jsonEncode({'type': 'prewarm'}));
      return true;
    } catch (e) {
      _connected = false;
      return false;
    }
  }

  Future<void> disconnect() async {
    _connected = false;
    _responseTimer?.cancel();
    _pauseTimer?.cancel();
    _cooldownTimer?.cancel();
    _eventController?.close();
    _eventController = null;
    await _streamSubscription?.cancel();
    _streamSubscription = null;
    await _channel?.sink.close();
    _channel = null;
    _isQuerying = false;
    _isSpeaking = false;
    _isInCooldown = false;
    _recentTranscript = '';
  }
}
