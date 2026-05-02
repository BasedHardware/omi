import 'dart:async';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:hive/hive.dart';

import 'package:nooto_v2/chat/chat_message.dart';
import 'package:nooto_v2/chat/chat_session.dart';
import 'package:nooto_v2/chat/chat_storage.dart';
import 'package:nooto_v2/services/chat_service.dart';

/// Owns chat state across multiple sessions.
///
/// State shape (in memory):
///   `_sessions`          : `List<ChatSession>`     — drawer source
///   `_currentSessionId`  : `String?`               — null = empty composer
///   `_messagesBySession` : `Map<sessionId, List<ChatMessage>>` — O(1) reads
///   `_activeStream`      : `StreamSubscription?`   — cancel hook
///
/// Persistence (Hive):
///   chat.sessions.v1 → ChatSession.toJson keyed by id
///   chat.messages.v1 → ChatMessage.toJson keyed by id, with sessionId field
///
/// On hydrate: any message without sessionId is migrated into a single
/// "Welcome chat" session (idempotent — only created if it doesn't exist).
class ChatProvider extends ChangeNotifier {
  ChatProvider({required ChatService service}) : _service = service {
    _hydrate();
  }

  final ChatService _service;
  final List<ChatSession> _sessions = [];
  final Map<String, List<ChatMessage>> _messagesBySession = {};
  String? _currentSessionId;
  bool _sending = false;
  String? _error;
  StreamSubscription<ChatStreamEvent>? _activeStream;
  String? _activeStreamSessionId;
  String? _activeStreamAssistantId;
  // Completer for the in-flight `send()` call. Cancellation paths
  // (`_cancelActiveStream`, `stopActiveStream`) complete this so the
  // awaiting `send()` future unblocks and runs its `finally` cleanup.
  Completer<void>? _activeStreamCompleter;

  // ---------------------------------------------------------------------------
  // Public read API
  // ---------------------------------------------------------------------------

  List<ChatSession> get sessions => List.unmodifiable(_sessions);
  String? get currentSessionId => _currentSessionId;
  bool get sending => _sending;
  String? get error => _error;

  /// Messages in the active session. Empty list when no session is active
  /// (default cold-start state — empty composer).
  List<ChatMessage> get messages {
    final id = _currentSessionId;
    if (id == null) return const [];
    return List.unmodifiable(_messagesBySession[id] ?? const []);
  }

  /// True when no session is active (cold-start / "+ New chat" pre-send).
  bool get isEmpty => _currentSessionId == null || messages.isEmpty;

  Box<Map> get _msgBox => Hive.box<Map>(ChatBoxes.messages);
  Box<Map> get _sessionBox => Hive.box<Map>(ChatBoxes.sessions);

  // ---------------------------------------------------------------------------
  // Session API
  // ---------------------------------------------------------------------------

  /// Creates a new session, sets it active, cancels any in-flight stream.
  /// Returns the new session id. UI does NOT need to read it — listeners fire.
  String newSession() {
    _cancelActiveStream();
    final now = DateTime.now();
    final session = ChatSession(
      id: _newId(),
      title: 'New chat',
      createdAt: now,
      updatedAt: now,
    );
    _sessions.insert(0, session);
    _messagesBySession[session.id] = [];
    _currentSessionId = session.id;
    _persistSession(session);
    notifyListeners();
    return session.id;
  }

  /// Switches the active session. Cancels any in-flight stream first so the
  /// prior session's assistant message gets finalized cleanly.
  void selectSession(String id) {
    if (_currentSessionId == id) return;
    final exists = _sessions.any((s) => s.id == id);
    if (!exists) return; // no-op for unknown ids
    _cancelActiveStream();
    _currentSessionId = id;
    notifyListeners();
  }

  /// Resets the visible thread to "no session" (empty composer). Used on
  /// cold-start and when the active session was just deleted.
  void clearCurrent() {
    if (_currentSessionId == null) return;
    _cancelActiveStream();
    _currentSessionId = null;
    notifyListeners();
  }

  /// Renames a session. Empty/whitespace-only titles are rejected.
  Future<bool> renameSession(String id, String newTitle) async {
    final trimmed = newTitle.trim();
    if (trimmed.isEmpty) return false;
    final idx = _sessions.indexWhere((s) => s.id == id);
    if (idx == -1) return false;
    final updated = _sessions[idx].copyWith(
      title: trimmed.length > 80 ? trimmed.substring(0, 80) : trimmed,
      updatedAt: DateTime.now(),
    );
    _sessions[idx] = updated;
    _persistSession(updated);
    notifyListeners();
    return true;
  }

  /// Deletes a session and its messages. If the deleted session was active,
  /// `currentSessionId` becomes null (composer goes to empty state).
  Future<void> deleteSession(String id) async {
    final idx = _sessions.indexWhere((s) => s.id == id);
    if (idx == -1) return;
    if (_currentSessionId == id) {
      _cancelActiveStream();
      _currentSessionId = null;
    }
    final msgs = _messagesBySession.remove(id) ?? const <ChatMessage>[];
    _sessions.removeAt(idx);
    for (final m in msgs) {
      await _msgBox.delete(m.id);
    }
    await _sessionBox.delete(id);
    notifyListeners();
  }

  /// Toggles the pinned flag on a session (CEO expansion #2).
  Future<void> togglePin(String id) async {
    final idx = _sessions.indexWhere((s) => s.id == id);
    if (idx == -1) return;
    final updated = _sessions[idx].copyWith(pinned: !_sessions[idx].pinned);
    _sessions[idx] = updated;
    _persistSession(updated);
    notifyListeners();
  }

  // ---------------------------------------------------------------------------
  // Send / stream
  // ---------------------------------------------------------------------------

  /// Sends a user message in the active session (creates one if none exists).
  /// Pushes the user bubble immediately, then opens a streaming assistant
  /// message that accumulates as chunks arrive. The first user message in a
  /// fresh session also sets the session title (one-shot).
  Future<void> send(String text) async {
    final trimmed = text.trim();
    if (trimmed.isEmpty || _sending) return;

    // Auto-create a session on first send if none is active.
    var sessionId = _currentSessionId ??= newSession();

    _error = null;
    _sending = true;

    final msgs = _messagesBySession.putIfAbsent(sessionId, () => []);
    final isFirstUserMessage = msgs.where((m) => m.role == ChatRole.user).isEmpty;

    final user = ChatMessage(
      id: _newId(),
      role: ChatRole.user,
      text: trimmed,
      createdAt: DateTime.now(),
      sessionId: sessionId,
    );
    msgs.add(user);
    _persistMessage(user);

    // One-shot auto-title: first user message in the session sets the title.
    if (isFirstUserMessage) {
      final sIdx = _sessions.indexWhere((s) => s.id == sessionId);
      if (sIdx != -1) {
        final updated = _sessions[sIdx].copyWith(
          title: deriveSessionTitle(trimmed),
          preview: trimmed.length > 80 ? '${trimmed.substring(0, 80)}…' : trimmed,
          updatedAt: DateTime.now(),
          messageCount: msgs.length,
        );
        _sessions[sIdx] = updated;
        _persistSession(updated);
      }
    } else {
      _bumpUpdatedAt(sessionId, msgs.length);
    }

    _trimSession(sessionId);
    notifyListeners();

    final assistantId = _newId();
    var assistant = ChatMessage(
      id: assistantId,
      role: ChatRole.assistant,
      text: '',
      createdAt: DateTime.now(),
      streaming: true,
      sessionId: sessionId,
    );
    msgs.add(assistant);
    notifyListeners();

    _activeStreamSessionId = sessionId;
    _activeStreamAssistantId = assistantId;
    final completer = Completer<void>();
    _activeStreamCompleter = completer;

    _activeStream = _service.streamChat(trimmed).listen(
      (event) {
        if (event is ChatStreamText) {
          assistant = assistant.copyWith(text: assistant.text + event.text);
        } else if (event is ChatStreamToolStart) {
          // Dedupe consecutive identical tool labels — agent re-emits the
          // same one across iterations (e.g. multi-step search).
          final events = List<String>.from(assistant.toolEvents);
          if (events.isEmpty || events.last != event.label) {
            events.add(event.label);
            assistant = assistant.copyWith(toolEvents: events);
          }
        }
        _replaceMessageInSession(sessionId, assistantId, assistant);
        notifyListeners();
      },
      onError: (e) {
        debugPrint('[ChatProvider] streamChat failed: $e');
        _error = e.toString();
        final fallback = assistant.copyWith(
          text: assistant.text.isEmpty
              ? "I couldn't reach the server. Try again in a moment."
              : assistant.text,
          streaming: false,
        );
        _replaceMessageInSession(sessionId, assistantId, fallback);
        _persistMessage(fallback);
        _bumpUpdatedAt(sessionId, msgs.length);
        if (!completer.isCompleted) completer.complete();
      },
      onDone: () {
        final finalMsg = assistant.copyWith(streaming: false);
        _replaceMessageInSession(sessionId, assistantId, finalMsg);
        _persistMessage(finalMsg);
        _bumpUpdatedAt(sessionId, msgs.length);
        if (!completer.isCompleted) completer.complete();
      },
      cancelOnError: true,
    );

    try {
      await completer.future;
    } finally {
      _sending = false;
      _activeStream = null;
      _activeStreamSessionId = null;
      _activeStreamAssistantId = null;
      _activeStreamCompleter = null;
      _trimSession(sessionId);
      notifyListeners();
    }
  }

  /// User-triggered cancel of the in-flight stream (the "Stop generating"
  /// button on the assistant bubble — CEO expansion #1). Marks the partial
  /// assistant message as `stopped: true` so the renderer can show the
  /// "⏹ Stopped" inline marker.
  void stopActiveStream() {
    final sessionId = _activeStreamSessionId;
    final assistantId = _activeStreamAssistantId;
    if (sessionId == null || assistantId == null) return;
    final msgs = _messagesBySession[sessionId];
    if (msgs == null) return;
    final idx = msgs.indexWhere((m) => m.id == assistantId);
    if (idx == -1) return;
    final stoppedMsg = msgs[idx].copyWith(streaming: false, stopped: true);
    msgs[idx] = stoppedMsg;
    _persistMessage(stoppedMsg);
    _activeStream?.cancel();
    _activeStream = null;
    _activeStreamSessionId = null;
    _activeStreamAssistantId = null;
    final completer = _activeStreamCompleter;
    _activeStreamCompleter = null;
    if (completer != null && !completer.isCompleted) completer.complete();
    notifyListeners();
  }

  // ---------------------------------------------------------------------------
  // Internal helpers
  // ---------------------------------------------------------------------------

  /// Cancels in-flight stream WITHOUT marking as user-stopped — used when
  /// the user switches sessions or creates a new one. Finalizes the prior
  /// assistant message with what we have so far so it persists.
  void _cancelActiveStream() {
    final sessionId = _activeStreamSessionId;
    final assistantId = _activeStreamAssistantId;
    if (sessionId == null || assistantId == null) {
      _activeStream?.cancel();
      _activeStream = null;
      final completer = _activeStreamCompleter;
      _activeStreamCompleter = null;
      if (completer != null && !completer.isCompleted) completer.complete();
      return;
    }
    final msgs = _messagesBySession[sessionId];
    if (msgs != null) {
      final idx = msgs.indexWhere((m) => m.id == assistantId);
      if (idx != -1 && msgs[idx].streaming) {
        final finalMsg = msgs[idx].copyWith(streaming: false);
        msgs[idx] = finalMsg;
        _persistMessage(finalMsg);
      }
    }
    _activeStream?.cancel();
    _activeStream = null;
    _activeStreamSessionId = null;
    _activeStreamAssistantId = null;
    final completer = _activeStreamCompleter;
    _activeStreamCompleter = null;
    if (completer != null && !completer.isCompleted) completer.complete();
  }

  void _replaceMessageInSession(String sessionId, String messageId, ChatMessage updated) {
    final msgs = _messagesBySession[sessionId];
    if (msgs == null) return;
    final idx = msgs.indexWhere((m) => m.id == messageId);
    if (idx != -1) msgs[idx] = updated;
  }

  void _bumpUpdatedAt(String sessionId, int messageCount) {
    final idx = _sessions.indexWhere((s) => s.id == sessionId);
    if (idx == -1) return;
    final updated = _sessions[idx].copyWith(
      updatedAt: DateTime.now(),
      messageCount: messageCount,
    );
    _sessions[idx] = updated;
    _persistSession(updated);
  }

  void _persistMessage(ChatMessage m) => _msgBox.put(m.id, m.toJson());
  void _persistSession(ChatSession s) => _sessionBox.put(s.id, s.toJson());

  /// Per-session retention trim. Keeps the box from growing unboundedly when
  /// one chatty session would otherwise push out other sessions' messages.
  /// Cap intentionally generous — the global retentionLimit is a soft cap
  /// per session here.
  void _trimSession(String sessionId) {
    final msgs = _messagesBySession[sessionId];
    if (msgs == null) return;
    if (msgs.length <= ChatBoxes.retentionLimit) return;
    final excess = msgs.length - ChatBoxes.retentionLimit;
    final dropped = msgs.sublist(0, excess);
    msgs.removeRange(0, excess);
    for (final m in dropped) {
      _msgBox.delete(m.id);
    }
  }

  String _newId() {
    final r = Random.secure();
    return '${DateTime.now().millisecondsSinceEpoch}-${r.nextInt(1 << 32).toRadixString(16)}';
  }

  // ---------------------------------------------------------------------------
  // Hydrate + migration
  // ---------------------------------------------------------------------------

  void _hydrate() {
    try {
      // Load sessions first.
      _sessions.clear();
      for (final raw in _sessionBox.values) {
        try {
          _sessions.add(ChatSession.fromJson(Map<String, dynamic>.from(raw)));
        } catch (e) {
          debugPrint('[ChatProvider] skipped bad session: $e');
        }
      }

      // Load messages, partition by sessionId, drop streaming stragglers.
      _messagesBySession.clear();
      final orphaned = <ChatMessage>[];
      for (final raw in _msgBox.values.toList()) {
        try {
          final m = ChatMessage.fromJson(Map<String, dynamic>.from(raw));
          if (m.streaming) {
            // Interrupted stream from prior process; drop on disk too.
            _msgBox.delete(m.id);
            continue;
          }
          if (m.sessionId == null) {
            orphaned.add(m);
            continue;
          }
          _messagesBySession.putIfAbsent(m.sessionId!, () => []).add(m);
        } catch (e) {
          debugPrint('[ChatProvider] skipped bad message: $e');
        }
      }

      // Migration: any pre-sessions messages get folded into a single
      // "Welcome chat". Idempotent: if a Welcome chat already exists from a
      // prior migration pass, reuse it.
      if (orphaned.isNotEmpty) {
        var welcome = _sessions.firstWhere(
          (s) => s.id == _welcomeSessionId,
          orElse: () => _createWelcomeSession(orphaned),
        );
        if (!_sessions.any((s) => s.id == _welcomeSessionId)) {
          _sessions.add(welcome);
          _persistSession(welcome);
        }
        final bucket = _messagesBySession.putIfAbsent(_welcomeSessionId, () => []);
        for (final m in orphaned) {
          final tagged = m.copyWith(sessionId: _welcomeSessionId);
          bucket.add(tagged);
          _persistMessage(tagged);
        }
        // Refresh title/preview/messageCount on the welcome session if any
        // user messages came through — gives the migrated session a useful
        // title instead of "Welcome chat" forever.
        final firstUser = bucket.firstWhere(
          (m) => m.role == ChatRole.user,
          orElse: () => bucket.first,
        );
        final updatedWelcome = welcome.copyWith(
          title: welcome.title == 'Welcome chat'
              ? deriveSessionTitle(firstUser.text)
              : welcome.title,
          preview: firstUser.text.length > 80
              ? '${firstUser.text.substring(0, 80)}…'
              : firstUser.text,
          messageCount: bucket.length,
          updatedAt: bucket.last.createdAt,
        );
        final wIdx = _sessions.indexWhere((s) => s.id == _welcomeSessionId);
        if (wIdx != -1) {
          _sessions[wIdx] = updatedWelcome;
          _persistSession(updatedWelcome);
        }
      }

      // Sort messages within each session by createdAt asc.
      for (final list in _messagesBySession.values) {
        list.sort((a, b) => a.createdAt.compareTo(b.createdAt));
      }

      // Default cold-start: no active session (empty composer).
      _currentSessionId = null;
    } catch (e, st) {
      debugPrint('[ChatProvider] hydrate failed: $e\n$st');
    }
    notifyListeners();
  }

  /// Stable id for the migrated "Welcome chat" so a second hydrate finds it.
  static const String _welcomeSessionId = 'welcome-chat';

  ChatSession _createWelcomeSession(List<ChatMessage> orphaned) {
    final firstAt = orphaned
        .map((m) => m.createdAt)
        .reduce((a, b) => a.isBefore(b) ? a : b);
    final lastAt = orphaned
        .map((m) => m.createdAt)
        .reduce((a, b) => a.isAfter(b) ? a : b);
    return ChatSession(
      id: _welcomeSessionId,
      title: 'Welcome chat',
      createdAt: firstAt,
      updatedAt: lastAt,
      messageCount: orphaned.length,
    );
  }

  @override
  void dispose() {
    _activeStream?.cancel();
    super.dispose();
  }
}
