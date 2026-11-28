// Owns push-token acquisition, retry and durable write ordering.
// Auth generation changes revoke outstanding registration work.
import 'dart:async';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/integrations/connection_read.dart';
import 'package:omi/utils/debug_log_manager.dart';

/// Closed vocabularies keep credentials, account IDs and SDK error text out of
/// the opt-in developer export. Diagnostics never gate registration.
enum PushRegistrationStage { session, apns, token, timeZone, persistence, localOrder, http, retry }

enum PushRegistrationResult { unavailable, exception, timeout, declined, accepted, exhausted, invalidResponse }

typedef FcmTokenPersistence = Future<bool> Function(
    String token, String zone, AuthSessionSnapshot owner, bool Function() canLogDiagnostic);

Future<void> logPushRegistration(
  PushRegistrationStage stage,
  PushRegistrationResult result, {
  int? httpStatus,
}) async {
  try {
    await DebugLogManager.logEvent('push_registration', {
      'stage': stage.name,
      'result': result.name,
      if (httpStatus != null) 'http_status': httpStatus,
    });
  } catch (_) {
    // Diagnostic storage can itself be unavailable; preserve registration.
  }
}

/// Device-local ordering metadata, with no account identifiers or token contents.
const fcmRegistrationOrderKey = 'fcmRegistrationOrder';

Future<int?> reserveFcmRegistrationOrder() async {
  final prefs = SharedPreferencesUtil();
  final now = DateTime.now().microsecondsSinceEpoch;
  final previous = prefs.getInt(fcmRegistrationOrderKey);
  final next = now > previous ? now : previous + 1;
  // SharedPreferences reserves the cache entry synchronously. Send only after
  // storage acknowledges the order so overlapping attempts have unique values.
  return await prefs.saveInt(fcmRegistrationOrderKey, next) ? next : null;
}

/// One owner for token acquisition, accepted persistence and bounded retry.
/// SDK waits and old-account completions cannot block a replacement session.
class FcmTokenRegistration {
  FcmTokenRegistration({
    required this.capture,
    required this.isCurrent,
    required this.readApns,
    required this.readToken,
    required this.readTimeZone,
    required this.persist,
    required this.requiresApns,
    this.onDiagnostic,
    this.deadline = const Duration(seconds: 20),
    this.retryDelays = const [
      Duration(seconds: 1),
      Duration(seconds: 2),
      Duration(seconds: 4),
      Duration(seconds: 8),
      Duration(seconds: 16),
      Duration(seconds: 30),
      Duration(seconds: 60),
    ],
  });

  final AuthSessionSnapshot? Function() capture;
  final bool Function(AuthSessionSnapshot) isCurrent;
  final Future<String?> Function() readApns;
  final Future<String?> Function() readToken;
  final Future<String> Function() readTimeZone;
  final FcmTokenPersistence persist;
  final bool requiresApns;
  final void Function(PushRegistrationStage, PushRegistrationResult)? onDiagnostic;
  final Duration deadline;
  final List<Duration> retryDelays;

  AuthSessionSnapshot? _owner;
  int _epoch = 0;
  int _retryIndex = 0;
  Timer? _retry;
  ConnectionRead<Object?>? _read;
  Future<void>? _inFlight;
  String? _offeredToken;
  (String, String)? _saved;
  bool _again = false;
  bool _disposed = false;

  Future<void> refresh({String? token}) => _run(token: token, resetBudget: true);

  /// Revoke pending work immediately, without admitting a replacement owner.
  /// The normal authenticated entry point must explicitly refresh again.
  void invalidateSession() => _reset();

  Future<void> _run({String? token, required bool resetBudget}) {
    if (_disposed) return Future.value();
    final owner = capture();
    if (owner == null) {
      _reset();
      _record(PushRegistrationStage.session, PushRegistrationResult.unavailable);
      return Future.value();
    }
    if (_owner?.ownerUid != owner.ownerUid || _owner?.generation != owner.generation) {
      _reset();
      _owner = owner;
    }
    if (resetBudget) _retryIndex = 0;
    _retry?.cancel();
    _retry = null;
    if (token?.isNotEmpty == true) _offeredToken = token;
    final pending = _inFlight;
    if (pending != null) {
      if (token?.isNotEmpty == true) _again = true;
      return pending;
    }
    final epoch = _epoch;
    late final Future<void> work;
    work = _attempt(owner, epoch).then((accepted) {
      if (!_current(owner, epoch)) return;
      if (accepted) {
        _retryIndex = 0;
      } else if (_retryIndex < retryDelays.length) {
        final delay = retryDelays[_retryIndex++];
        _retry = Timer(delay, () => unawaited(_run(resetBudget: false)));
      } else {
        _record(PushRegistrationStage.retry, PushRegistrationResult.exhausted);
      }
    }).whenComplete(() {
      if (!identical(_inFlight, work)) return;
      _inFlight = null;
      if (_again && _current(owner, epoch)) {
        _again = false;
        unawaited(_run(resetBudget: false));
      }
    });
    _inFlight = work;
    return work;
  }

  bool _current(AuthSessionSnapshot owner, int epoch) => !_disposed && epoch == _epoch && isCurrent(owner);

  Future<T> _bounded<T>(Future<T> Function() operation) => _trackRead(ConnectionRead<T>(operation, deadline));

  Future<T> _trackRead<T>(ConnectionRead<T> read) async {
    _read = read;
    try {
      return await read.future;
    } finally {
      if (identical(_read, read)) _read = null;
    }
  }

  void _record(PushRegistrationStage stage, PushRegistrationResult result) {
    try {
      final observer = onDiagnostic;
      if (observer != null) {
        observer(stage, result);
      } else {
        unawaited(logPushRegistration(stage, result));
      }
    } catch (_) {
      // A diagnostic observer must not change retry or ownership behavior.
    }
  }

  Future<bool> _attempt(AuthSessionSnapshot owner, int epoch) async {
    var stage = PushRegistrationStage.apns;
    try {
      if (!_current(owner, epoch)) return false;
      if (requiresApns) {
        final apns = await _bounded(readApns);
        if (!_current(owner, epoch)) return false;
        if (apns == null || apns.isEmpty) {
          _record(stage, PushRegistrationResult.unavailable);
          return false;
        }
      }
      stage = PushRegistrationStage.token;
      final token = _offeredToken ?? await _bounded(readToken);
      if (!_current(owner, epoch)) return false;
      if (token == null || token.isEmpty) {
        _record(stage, PushRegistrationResult.unavailable);
        return false;
      }
      // A rotation received while acquiring APNs may already be this attempt's
      // token. Only a subsequent rotation needs another attempt; re-reading the
      // SDK after consuming this one could overwrite it with an older value.
      if (_offeredToken == token) _again = false;
      stage = PushRegistrationStage.timeZone;
      final zone = await _bounded(readTimeZone);
      if (!_current(owner, epoch)) return false;
      if (_saved == (token, zone)) {
        if (_offeredToken == token) _offeredToken = null;
        return true;
      }
      stage = PushRegistrationStage.persistence;
      final accepted = await _trackRead(ConnectionRead<bool>.withLifetime(
        (isPending) => persist(token, zone, owner, () => isPending() && _current(owner, epoch)),
        deadline,
      ));
      if (!_current(owner, epoch)) return false;
      if (!accepted) {
        _record(stage, PushRegistrationResult.declined);
        return false;
      }
      _saved = (token, zone);
      _record(stage, PushRegistrationResult.accepted);
      if (_offeredToken == token) _offeredToken = null;
      return true;
    } catch (error) {
      if (_current(owner, epoch)) {
        _record(stage, error is TimeoutException ? PushRegistrationResult.timeout : PushRegistrationResult.exception);
      }
      return false;
    }
  }

  void _reset() {
    _epoch++;
    _retry?.cancel();
    _retry = null;
    _read?.cancel();
    _read = null;
    _inFlight = null;
    _owner = null;
    _offeredToken = null;
    _saved = null;
    _retryIndex = 0;
    _again = false;
  }

  void dispose() {
    _disposed = true;
    _reset();
  }
}
