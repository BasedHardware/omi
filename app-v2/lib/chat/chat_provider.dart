import 'dart:async';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:hive/hive.dart';

import 'package:nooto_v2/chat/chat_message.dart';
import 'package:nooto_v2/chat/chat_storage.dart';
import 'package:nooto_v2/services/chat_service.dart';

/// Owns the single global chat thread. App-scoped (lives for the whole app
/// lifetime) so messages survive tab switches and screen rebuilds.
///
/// Persistence: every terminal write (user message added, assistant chunk
/// stored mid-stream, assistant streaming-flag flipped to false) goes to the
/// `chat.messages.v1` Hive box. Mid-stream chunks debounce — we don't write
/// per token, only when the streaming message accumulates to a sentence
/// boundary or the stream completes.
class ChatProvider extends ChangeNotifier {
  ChatProvider({required ChatService service}) : _service = service {
    _hydrate();
  }

  final ChatService _service;
  final List<ChatMessage> _messages = [];
  bool _sending = false;
  String? _error;

  List<ChatMessage> get messages => List.unmodifiable(_messages);
  bool get sending => _sending;
  String? get error => _error;
  bool get isEmpty => _messages.isEmpty;

  Box<Map> get _box => Hive.box<Map>(ChatBoxes.messages);

  void _hydrate() {
    try {
      final all = _box.values
          .map((raw) => ChatMessage.fromJson(Map<String, dynamic>.from(raw)))
          .where((m) => !m.streaming) // drop interrupted streams
          .toList()
        ..sort((a, b) => a.createdAt.compareTo(b.createdAt));
      _messages
        ..clear()
        ..addAll(all);
      // Drop streaming-flagged stragglers from disk too.
      for (final stale in _box.values
          .map((raw) => ChatMessage.fromJson(Map<String, dynamic>.from(raw)))
          .where((m) => m.streaming)) {
        _box.delete(stale.id);
      }
    } catch (e, st) {
      debugPrint('[ChatProvider] hydrate failed: $e\n$st');
    }
    notifyListeners();
  }

  /// Sends a user message. Pushes the user bubble immediately, then opens a
  /// streaming assistant message that accumulates as chunks arrive. On
  /// failure we replace the streaming message with a short error bubble so
  /// the user sees what went wrong instead of an empty wait.
  Future<void> send(String text) async {
    final trimmed = text.trim();
    if (trimmed.isEmpty || _sending) return;

    _error = null;
    _sending = true;

    final user = ChatMessage(
      id: _newId(),
      role: ChatRole.user,
      text: trimmed,
      createdAt: DateTime.now(),
    );
    _messages.add(user);
    _persist(user);
    _trim();
    notifyListeners();

    final assistantId = _newId();
    var assistant = ChatMessage(
      id: assistantId,
      role: ChatRole.assistant,
      text: '',
      createdAt: DateTime.now(),
      streaming: true,
    );
    _messages.add(assistant);
    notifyListeners();

    try {
      await for (final event in _service.streamChat(trimmed)) {
        if (event is ChatStreamText) {
          assistant = assistant.copyWith(text: assistant.text + event.text);
        } else if (event is ChatStreamToolStart) {
          // Dedupe consecutive identical tool labels — the agent can re-emit
          // the same one across iterations (e.g. multi-step search).
          final events = List<String>.from(assistant.toolEvents);
          if (events.isEmpty || events.last != event.label) {
            events.add(event.label);
            assistant = assistant.copyWith(toolEvents: events);
          }
        }
        final idx = _messages.indexWhere((m) => m.id == assistantId);
        if (idx != -1) _messages[idx] = assistant;
        notifyListeners();
      }
      final finalMsg = assistant.copyWith(streaming: false);
      final idx = _messages.indexWhere((m) => m.id == assistantId);
      if (idx != -1) _messages[idx] = finalMsg;
      _persist(finalMsg);
    } catch (e) {
      debugPrint('[ChatProvider] streamChat failed: $e');
      _error = e.toString();
      final idx = _messages.indexWhere((m) => m.id == assistantId);
      if (idx != -1) {
        _messages[idx] = assistant.copyWith(
          text: "I couldn't reach the server. Try again in a moment.",
          streaming: false,
        );
        _persist(_messages[idx]);
      }
    } finally {
      _sending = false;
      _trim();
      notifyListeners();
    }
  }

  void _persist(ChatMessage m) => _box.put(m.id, m.toJson());

  void _trim() {
    if (_messages.length <= ChatBoxes.retentionLimit) return;
    final excess = _messages.length - ChatBoxes.retentionLimit;
    final dropped = _messages.sublist(0, excess);
    _messages.removeRange(0, excess);
    for (final m in dropped) {
      _box.delete(m.id);
    }
  }

  String _newId() {
    final r = Random.secure();
    return '${DateTime.now().millisecondsSinceEpoch}-${r.nextInt(1 << 32).toRadixString(16)}';
  }
}
