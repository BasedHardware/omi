import 'dart:async';
import 'dart:convert';

import 'package:omi/services/auth/auth_token_result.dart';

/// A bounded, account-owned outbox for the three onboarding state fields.
/// Local writes and acknowledgements serialize; network I/O never holds that lock.
class OnboardingSyncService {
  OnboardingSyncService({
    required this.read,
    required this.write,
    required this.send,
    required this.isCurrent,
    this.retryDelay = const Duration(seconds: 30),
  });

  final String Function(String owner) read;
  final Future<bool> Function(String owner, String value) write;
  final Future<bool> Function(AuthSessionSnapshot session, Map<String, dynamic> fields) send;
  final bool Function(AuthSessionSnapshot session) isCurrent;
  final Duration retryDelay;
  AuthSessionSnapshot? _session;
  Future<void> _writes = Future.value();
  Future<void>? _inFlight;
  Timer? _retry;
  bool _active = true;
  bool _disposed = false;

  Map<String, dynamic> pending(String owner) {
    final saved = read(owner);
    if (saved.isEmpty) return {};
    final data = jsonDecode(saved) as Map<String, dynamic>;
    return Map<String, dynamic>.from(data['fields'] as Map);
  }

  void bindSession(AuthSessionSnapshot? session) {
    _session = session;
    _retry?.cancel();
  }

  void setActive(bool active) {
    _active = active;
    if (!active) _retry?.cancel();
  }

  bool _canSend(AuthSessionSnapshot session) =>
      !_disposed &&
      _active &&
      (_session?.ownerUid == session.ownerUid && _session?.generation == session.generation) &&
      isCurrent(session);

  Future<T> _serialize<T>(Future<T> Function() action) {
    final result = _writes.then((_) => action());
    // One failed disk write must not poison subsequent user retries.
    _writes = result.then<void>((_) {}, onError: (Object _, StackTrace __) {});
    return result;
  }

  /// Returns only after the intent is on disk. A failed write keeps the caller
  /// on its current step; the HTTP result does not block offline navigation.
  Future<bool> enqueue(
    AuthSessionSnapshot session, {
    bool? completed,
    String? acquisitionSource,
    bool? deviceOnboardingCompleted,
  }) async {
    final saved = await _serialize(() async {
      if (_disposed || !isCurrent(session)) return false;
      final fields = pending(session.ownerUid);
      if (completed != null) fields['completed'] = completed;
      if (acquisitionSource != null) fields['acquisition_source'] = acquisitionSource;
      if (deviceOnboardingCompleted != null) fields['device_onboarding_completed'] = deviceOnboardingCompleted;
      if (fields.isEmpty) return true;
      // The revision changes the persisted snapshot even when fields repeat,
      // so an older acknowledgement cannot clear a newer identical submission.
      final old = read(session.ownerUid);
      final revision = old.isEmpty ? 0 : (jsonDecode(old) as Map)['revision'] as int;
      final ok = await write(session.ownerUid, jsonEncode({'revision': revision + 1, 'fields': fields}));
      return ok && !_disposed && isCurrent(session);
    });
    if (saved) unawaited(flush());
    return saved;
  }

  Future<void> flush() {
    if (_disposed) return Future.value();
    if (_inFlight != null) return _inFlight!;
    _retry?.cancel();
    final future = _drain();
    _inFlight = future;
    return future.whenComplete(() {
      _inFlight = null;
      final session = _session;
      if (session != null && _canSend(session) && read(session.ownerUid).isNotEmpty) {
        _retry = Timer(retryDelay, () => unawaited(flush()));
      }
    });
  }

  Future<void> _drain() async {
    while (!_disposed) {
      await _writes;
      final session = _session;
      if (session == null || !_canSend(session)) return;
      final snapshot = read(session.ownerUid);
      if (snapshot.isEmpty) return;
      try {
        final fields = Map<String, dynamic>.from((jsonDecode(snapshot) as Map)['fields'] as Map);
        final acknowledged = await send(session, fields);
        if (!_canSend(session)) continue;
        if (!acknowledged) return;
        await _serialize(() async {
          if (!_canSend(session)) return;
          // An in-flight acknowledgement must not erase a newer user answer.
          if (read(session.ownerUid) == snapshot && !await write(session.ownerUid, '')) {
            throw StateError('Onboarding acknowledgement could not be persisted');
          }
        });
      } catch (_) {
        // Preserve intent on transport, decode or acknowledgement-write failure.
        return;
      }
    }
  }

  void dispose() {
    _disposed = true;
    _session = null;
    _retry?.cancel();
  }
}
