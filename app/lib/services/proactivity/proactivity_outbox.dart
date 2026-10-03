import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:uuid/uuid.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/proactivity_wire.g.dart';

enum ProactivityAction { shown, opened, thumbsUp, thumbsDown, dismissed, producerDisabled }

extension ProactivityActionWire on ProactivityAction {
  String get wire => switch (this) {
        ProactivityAction.thumbsUp => 'thumbs_up',
        ProactivityAction.thumbsDown => 'thumbs_down',
        ProactivityAction.producerDisabled => 'producer_disabled',
        _ => name,
      };
}

typedef OutcomeSender = Future<ApiResult<GeneratedProactivityOutcomeResponse>> Function(
  String itemId,
  GeneratedProactivityOutcomeRequest event,
);

/// Only receipts, never feed content. Writes serialize before network attempts.
/// Account epochs fence delayed storage, navigation and transport completions.
class ProactivityOutbox extends ChangeNotifier {
  ProactivityOutbox({
    required this.read,
    required this.write,
    required this.send,
    required this.surface,
    required this.ownerIsCurrent,
    this.track,
    this.now = DateTime.now,
    this.retryDelay = const Duration(seconds: 30),
  });

  final String Function() read;
  final Future<void> Function(String) write;
  final OutcomeSender send;
  final String Function() surface;
  final bool Function(String) ownerIsCurrent;
  final void Function(String action, String channel, String surface)? track;
  final Duration retryDelay;
  final DateTime Function() now;
  String? _owner;
  int _epoch = 0;
  bool _loaded = false;
  bool _disposed = false;
  Future<void> _writes = Future.value();
  final List<({String itemId, GeneratedProactivityOutcomeRequest event})> _pending = [];
  final Map<String, DateTime> _shown = {};
  final Map<String, String> feedback = {};
  final Set<String> dismissed = {};
  final Set<String> disabledProducers = {};
  Timer? _retry;
  int? _sendingEpoch;

  String? get owner => _owner;
  int get epoch => _epoch;
  int get pendingCount => _pending.length;
  bool isCurrent(int epoch) => !_disposed && epoch == _epoch && _owner != null && ownerIsCurrent(_owner!);

  Future<void> bindOwner(String? owner) async {
    if (_loaded && owner == _owner) return;
    _loaded = true;
    _epoch++;
    _owner = owner;
    _retry?.cancel();
    _pending.clear();
    _shown.clear();
    feedback.clear();
    dismissed.clear();
    disabledProducers.clear();
    try {
      final saved = read();
      if (owner != null && saved.isNotEmpty) {
        final data = jsonDecode(saved) as Map<String, dynamic>;
        if (data['owner'] == owner) {
          final shown = Map<String, dynamic>.from(data['shown']);
          for (final entry in shown.entries) {
            final date = DateTime.parse(entry.value as String);
            if (now().difference(date) < const Duration(days: 31)) _shown[entry.key] = date;
          }
          for (final row in (data['pending'] as List).take(100)) {
            final event = GeneratedProactivityOutcomeRequest.fromJson(Map<String, dynamic>.from(row['event']));
            if (!ProactivityAction.values.any((a) => a.wire == event.action)) continue;
            _pending.add((itemId: row['item_id'] as String, event: event));
            if (event.action == 'thumbs_up' || event.action == 'thumbs_down') feedback[row['item_id']] = event.action;
            if (event.action == 'dismissed') dismissed.add(row['item_id']);
          }
          disabledProducers.addAll((data['disabled'] as List).cast<String>());
        }
      }
    } catch (_) {
      _pending.clear();
      _shown.clear();
      feedback.clear();
      dismissed.clear();
      disabledProducers.clear();
    }
    notifyListeners();
    await _persist();
    unawaited(flush());
  }

  Future<void> record(String itemId, ProactivityAction action, {String channel = 'feed', String? producer}) async {
    final epoch = _epoch;
    if (!isCurrent(epoch) || _pending.length >= 100) return;
    if (action == ProactivityAction.shown) {
      if (_shown.containsKey(itemId)) return;
      final date = now();
      _shown.removeWhere((_, shownAt) => date.difference(shownAt) >= const Duration(days: 31));
      _shown[itemId] = date;
    }
    if (action == ProactivityAction.thumbsUp || action == ProactivityAction.thumbsDown) feedback[itemId] = action.wire;
    if (action == ProactivityAction.dismissed) dismissed.add(itemId);
    if (action == ProactivityAction.producerDisabled && producer != null) disabledProducers.add(producer);
    final event = GeneratedProactivityOutcomeRequest(
      action: action.wire,
      channel: channel,
      eventId: const Uuid().v4(),
      surface: surface(),
    );
    _pending.add((itemId: itemId, event: event));
    try {
      track?.call(action.wire, channel, event.surface);
    } catch (_) {
      // Analytics is observational; it cannot prevent an outcome receipt.
    }
    notifyListeners();
    await _persist();
    if (isCurrent(epoch)) unawaited(flush());
  }

  Future<void> _persist() {
    final snapshot = _owner == null
        ? ''
        : jsonEncode({
            'owner': _owner,
            'shown': _shown.map((id, date) => MapEntry(id, date.toUtc().toIso8601String())),
            'disabled': disabledProducers.toList(),
            'pending': _pending.map((e) => {'item_id': e.itemId, 'event': e.event.toJson()}).toList(),
          });
    return _writes = _writes.then((_) => write(snapshot)).catchError((Object _) {
      // Storage can be unavailable; keep the in-memory receipts and retry transport.
    });
  }

  Future<void> flush() async {
    final epoch = _epoch;
    if (!isCurrent(epoch) || _sendingEpoch == epoch) return;
    _sendingEpoch = epoch;
    _retry?.cancel();
    try {
      await _writes;
      while (isCurrent(epoch) && _pending.isNotEmpty) {
        final entry = _pending.first;
        ApiResult<GeneratedProactivityOutcomeResponse> result;
        try {
          result = await send(entry.itemId, entry.event);
        } catch (_) {
          result = const ApiFailure(ApiProblem(ApiProblemKind.transport));
        }
        if (!isCurrent(epoch)) return;
        if (result is ApiFailure<GeneratedProactivityOutcomeResponse> && result.problem.retryable) {
          _retry = Timer(result.problem.retryAfter ?? retryDelay, () => unawaited(flush()));
          return;
        }
        _pending.removeAt(0); // Success (including deduplication) or terminal 4xx.
        await _persist();
      }
    } finally {
      if (_sendingEpoch == epoch) _sendingEpoch = null;
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _retry?.cancel();
    super.dispose();
  }
}
