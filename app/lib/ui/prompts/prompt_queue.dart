import 'dart:async';
import 'dart:collection';

import 'package:flutter/widgets.dart';

import 'package:omi/app_globals.dart';

/// How urgent a queued prompt is. Higher runs first; equal priorities run in arrival order.
abstract final class PromptPriority {
  /// Must be seen before anything else (a forced upgrade, a blocking consent).
  static const int critical = 100;

  /// Device safety and firmware notices.
  static const int high = 75;

  /// Product announcements, changelog, tutorials.
  static const int normal = 50;

  /// Upsells, review requests, tips.
  static const int low = 25;
}

/// Presents a prompt. Resolves when the prompt is gone (dismissed, accepted or skipped).
typedef PromptPresenter = Future<void> Function(BuildContext context);

/// One modal prompt at a time, in priority order, never while the user is busy
/// (docs/ux-contract.md §14).
///
/// Startup and background prompts — upgrade alert, announcements, changelog, device tutorial,
/// firmware notice, plan sheet, review request — are enqueued here instead of calling `showDialog`
/// themselves. The queue:
/// * shows one prompt, waits for it to close, then shows the next;
/// * orders by [PromptPriority], then arrival;
/// * drops a second [enqueue] with an id that is already queued or showing;
/// * holds everything while [blocked] is true (the home shell sets it for recording, a call or a
///   firmware update) and while a prompt's own `canShowNow` says no, re-checking on [pump].
///
/// ```dart
/// PromptQueue.instance.enqueue(
///   'changelog-1.0.543',
///   PromptPriority.normal,
///   show: (context) => ChangelogSheet.show(context),
/// );
/// ```
class PromptQueue {
  PromptQueue({BuildContext? Function()? contextProvider}) : _contextProvider = contextProvider ?? _defaultContext;

  /// The app-wide queue, presenting on the root navigator.
  static final PromptQueue instance = PromptQueue();

  static BuildContext? _defaultContext() {
    final state = globalNavigatorKey.currentState;
    return state?.overlay?.context ?? state?.context;
  }

  final BuildContext? Function() _contextProvider;
  final List<_QueuedPrompt> _pending = [];
  _QueuedPrompt? _showing;
  int _sequence = 0;
  bool _pumpScheduled = false;

  /// Global hold. The home shell sets it to "recording, a call or a firmware update is in
  /// progress"; while it returns true nothing new is shown. Call [pump] when it may have changed.
  bool Function() blocked = _neverBlocked;
  static bool _neverBlocked() => false;

  /// Ids waiting to be shown, in the order they will be shown.
  List<String> get pendingIds => UnmodifiableListView(_sortedPending().map((p) => p.id).toList());

  /// The id on screen now, if any.
  String? get showingId => _showing?.id;

  /// Queues [show] under [id]. Returns false (and does nothing) if [id] is already queued or
  /// showing. [canShowNow] lets one prompt wait for its own condition (e.g. "a device is
  /// connected"); it is re-checked on every [pump].
  bool enqueue(String id, int priority, {required PromptPresenter show, bool Function()? canShowNow}) {
    if (_showing?.id == id || _pending.any((p) => p.id == id)) return false;
    _pending.add(_QueuedPrompt(id, priority, _sequence++, show, canShowNow));
    _schedulePump();
    return true;
  }

  /// Drops a queued prompt that is no longer relevant. Has no effect on the prompt on screen.
  bool remove(String id) {
    final before = _pending.length;
    _pending.removeWhere((p) => p.id == id);
    return _pending.length != before;
  }

  /// Tries to show the next eligible prompt. Call after [blocked] or a `canShowNow` condition may
  /// have changed (recording stopped, device connected). Safe to call at any time.
  void pump() {
    if (_showing != null || blocked()) return;
    final context = _contextProvider();
    if (context == null || !context.mounted) return;
    final next = _sortedPending().where((p) => p.canShowNow?.call() ?? true).firstOrNull;
    if (next == null) return;
    _pending.remove(next);
    _showing = next;
    unawaited(_present(next, context));
  }

  Future<void> _present(_QueuedPrompt prompt, BuildContext context) async {
    try {
      await prompt.show(context);
    } catch (error, stack) {
      FlutterError.reportError(
        FlutterErrorDetails(
            exception: error, stack: stack, library: 'prompt_queue', context: ErrorDescription(prompt.id)),
      );
    } finally {
      if (identical(_showing, prompt)) _showing = null;
      _schedulePump();
    }
  }

  void _schedulePump() {
    if (_pumpScheduled) return;
    _pumpScheduled = true;
    scheduleMicrotask(() {
      _pumpScheduled = false;
      pump();
    });
  }

  List<_QueuedPrompt> _sortedPending() {
    final sorted = [..._pending];
    sorted.sort((a, b) {
      final byPriority = b.priority.compareTo(a.priority);
      return byPriority != 0 ? byPriority : a.sequence.compareTo(b.sequence);
    });
    return sorted;
  }

  /// Clears every queued prompt and the global hold. Tests only.
  @visibleForTesting
  void reset() {
    _pending.clear();
    _showing = null;
    blocked = _neverBlocked;
  }
}

class _QueuedPrompt {
  _QueuedPrompt(this.id, this.priority, this.sequence, this.show, this.canShowNow);

  final String id;
  final int priority;
  final int sequence;
  final PromptPresenter show;
  final bool Function()? canShowNow;
}
