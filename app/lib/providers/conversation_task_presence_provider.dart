// Bounded canonical task badges for mounted conversation rows. Account changes
// revoke old reads; failures remain unknown until refresh or a task mutation.
import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:omi/backend/http/api/conversation_tasks.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/services/auth_service.dart';

typedef TaskPresenceFetcher = Future<ApiResult<Map<String, bool>>> Function(List<String> ids, bool Function() canSend);

/// One bounded, account-owned presence reader shared by all visible Home rows.
/// Canonical task mutations and conversation refreshes invalidate it; summary
/// suggestions never authorize a badge. Failures stay unknown and retryable.
class ConversationTaskPresenceProvider extends ChangeNotifier {
  ConversationTaskPresenceProvider({AuthService? auth, TaskPresenceFetcher? fetch})
      : _auth = auth ?? AuthService.instance,
        _fetch = fetch ?? ((ids, current) => getConversationTaskPresence(ids, canSend: current)) {
    _auth.captureSessionSnapshot();
    _session = _auth.sessionGenerationEvents.listen((_) => _clear());
  }

  final AuthService _auth;
  final TaskPresenceFetcher _fetch;
  final Map<String, bool> _presence = {};
  final Set<String> _observed = {};
  final Set<String> _pending = {};
  Set<String>? _inFlight;
  final Set<String> _attempted = {};
  StreamSubscription<int>? _session;
  Timer? _timer;
  int _revision = 0;
  int taskRevision = 0;
  bool _disposed = false;
  ConversationProvider? _conversations;
  ActionItemsProvider? _tasks;
  Object? _conversationKey;
  Object? _taskKey;

  bool? presence(String id) => _presence[id];

  void bind(ConversationProvider conversations, ActionItemsProvider tasks) {
    if (!identical(_conversations, conversations)) {
      _conversations?.removeListener(_conversationChanged);
      _conversations = conversations..addListener(_conversationChanged);
      _conversationKey = conversations._taskPresenceInputs;
    }
    if (!identical(_tasks, tasks)) {
      _tasks?.removeListener(_tasksChanged);
      _tasks = tasks..addListener(_tasksChanged);
      _taskKey = _taskInputs(tasks);
    }
  }

  Object _taskInputs(ActionItemsProvider source) => (
        source.apiViewState,
        source.actionItems.length,
        source.isLoading,
        source.isFetching,
      );

  void _conversationChanged() {
    final conversations = _conversations!;
    final key = conversations._taskPresenceInputs;
    if (key == _conversationKey) return;
    _conversationKey = key;
    invalidate();
  }

  void _tasksChanged() {
    final key = _taskInputs(_tasks!);
    if (key == _taskKey) return;
    _taskKey = key;
    invalidate();
  }

  void request(String id) {
    if (_disposed || id.isEmpty) return;
    if (_observed.length == 100 && !_observed.contains(id)) {
      final oldest = _observed.first;
      _observed.remove(oldest);
      _presence.remove(oldest);
      _pending.remove(oldest);
      _attempted.remove(oldest);
    }
    _observed.add(id);
    if (_presence.containsKey(id) || (_inFlight?.contains(id) ?? false) || _attempted.contains(id)) return;
    _pending.add(id);
    _schedule();
  }

  void invalidate() {
    if (_disposed) return;
    _revision++;
    taskRevision++;
    _presence.clear();
    _attempted.clear();
    _pending.addAll(_observed);
    _schedule();
  }

  void _schedule() {
    _timer?.cancel();
    _timer = Timer(const Duration(milliseconds: 150), () {
      if (!_disposed) notifyListeners();
      unawaited(_drain());
    });
  }

  Future<void> _drain() async {
    if (_disposed || _inFlight != null || _pending.isEmpty) return;
    final owner = _auth.captureSessionSnapshot();
    if (owner == null || _pending.isEmpty) return;
    final revision = _revision;
    final ids = _pending.take(100).toList();
    _pending.removeAll(ids);
    final flight = _inFlight = ids.toSet();
    _attempted.addAll(ids);
    bool current() => !_disposed && revision == _revision && _auth.isSessionSnapshotCurrent(owner);
    try {
      final result = await _fetch(ids, current).timeout(const Duration(seconds: 20));
      if (!current()) return;
      if (result case ApiSuccess(:final data)) {
        for (final id in ids) {
          if (_observed.contains(id) && data[id] != null) _presence[id] = data[id]!;
        }
        notifyListeners();
      }
    } catch (_) {
      // Unknown is not "no tasks". A refresh/mutation retries; a rebuilding
      // row cannot create an infinite loop during a network outage.
    } finally {
      if (identical(_inFlight, flight)) {
        _inFlight = null;
        if (!_disposed && _pending.isNotEmpty) _schedule();
      }
    }
  }

  void _clear() {
    _revision++;
    taskRevision++;
    _timer?.cancel();
    _presence.clear();
    _observed.clear();
    _pending.clear();
    _inFlight = null;
    _attempted.clear();
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _timer?.cancel();
    _session?.cancel();
    _conversations?.removeListener(_conversationChanged);
    _tasks?.removeListener(_tasksChanged);
    super.dispose();
  }
}

extension on ConversationProvider {
  Object get _taskPresenceInputs => (
        conversations,
        conversations.length,
        searchedConversations,
        searchedConversations.length,
        processingConversations,
        processingConversations.length,
        isFetchingConversations,
        isLoadingConversations,
      );
}
