import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:in_app_review/in_app_review.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/services/app_review_policy.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';
import 'package:omi/utils/platform/platform_manager.dart';

export 'app_review_policy.dart' show AppReviewDecision, AppReviewMoment;

typedef AppReviewTelemetry = void Function(String eventName, Map<String, Object> properties);

/// Coordinates respectful, platform-owned app review requests.
///
/// This service does not try to infer whether a user rated the app. Store
/// surfaces deliberately do not expose that information. A request attempt is
/// reserved locally immediately before entering the native request plugin. An
/// unavailable store still consumes the in-memory session latch, while a
/// request failure consumes the durable anti-hammering budget.
class AppReviewService {
  static final AppReviewService _instance = AppReviewService._internal();

  factory AppReviewService() => _instance;

  AppReviewService._internal()
      : _providedStorage = null,
        _clock = DateTime.now,
        _platform = _currentPlatform,
        _appVersion = _productionAppVersion,
        _isAvailable = InAppReview.instance.isAvailable,
        _requestNativeReview = InAppReview.instance.requestReview,
        _writeState = null,
        _telemetry = _productionTelemetry;

  /// Creates an isolated service for hermetic tests and local policy checks.
  AppReviewService.forTesting({
    SharedPreferences? storage,
    DateTime Function()? clock,
    String? platform,
    String? appVersion,
    Future<bool> Function()? isAvailable,
    Future<void> Function()? requestNativeReview,
    Future<bool> Function(String key, String value)? writeState,
    AppReviewTelemetry? telemetry,
  })  : _providedStorage = storage,
        _clock = clock ?? DateTime.now,
        _platform = (() => platform ?? _currentPlatform()),
        _appVersion = (() => appVersion ?? _productionAppVersion()),
        _isAvailable = isAvailable ?? InAppReview.instance.isAvailable,
        _requestNativeReview = requestNativeReview ?? InAppReview.instance.requestReview,
        _writeState = writeState,
        _telemetry = telemetry ?? _productionTelemetry;

  static const String _stateKey = 'app_review_policy_v1';
  static const String _legacyPromptKey = 'has_shown_review_prompt';
  static const String _legacyConversationKey = 'has_shown_review_for_conversation';
  static const String _legacyActionItemKey = 'has_shown_review_for_action_item';

  final SharedPreferences? _providedStorage;
  final DateTime Function() _clock;
  final String Function() _platform;
  final String Function() _appVersion;
  final Future<bool> Function() _isAvailable;
  final Future<void> Function() _requestNativeReview;
  final Future<bool> Function(String key, String value)? _writeState;
  final AppReviewTelemetry _telemetry;

  Future<SharedPreferences>? _storageFuture;
  Future<void> _operationQueue = Future<void>.value();
  bool _attemptedThisSession = false;
  bool _storageBroken = false;

  /// Records that a valid reading surface was viewed.
  ///
  /// Callers should invoke this only after valid content has loaded. The
  /// service stores a local calendar day and first-seen timestamp, never the
  /// conversation, summary, or any other content.
  Future<void> recordEngagement() => _enqueue<void>(() async {
        if (_storageBroken) return;
        final now = _clock();
        final storage = await _storage();
        if (storage == null) return;

        final state = await _loadState(storage, now);
        if (state == null) return;
        state.firstSeenAtMs ??= now.millisecondsSinceEpoch;
        state.readingDays.add(_localDayKey(now));
        if (state.readingDays.length > AppReviewPolicy.maximumStoredReadingDays) {
          final sorted = state.readingDays.toList()..sort();
          state.readingDays
            ..clear()
            ..addAll(sorted.skip(sorted.length - AppReviewPolicy.maximumStoredReadingDays));
        }
        await _persistState(storage, state);
      });

  /// Requests the platform review dialog when local policy and lifecycle
  /// checks permit it. The lifecycle guard is checked before and after the
  /// asynchronous native availability query.
  Future<void> requestReview({
    required AppReviewMoment moment,
    required bool Function() isStillAppropriate,
  }) =>
      _enqueue<void>(() => _requestReviewSerialized(moment, isStillAppropriate));

  Future<void> _requestReviewSerialized(AppReviewMoment moment, bool Function() isStillAppropriate) async {
    final momentName = moment.telemetryName;
    final platform = _safeString(_platform);
    if (platform != 'ios' && platform != 'android') {
      _opportunity(momentName, AppReviewDecision.notIosOrAndroid);
      return;
    }
    if (_storageBroken) {
      _opportunity(momentName, AppReviewDecision.storageError);
      return;
    }

    final now = _clock();
    final storage = await _storage();
    if (storage == null) {
      _opportunity(momentName, AppReviewDecision.storageError);
      return;
    }
    final state = await _loadState(storage, now);
    if (state == null) {
      _opportunity(momentName, AppReviewDecision.storageError);
      return;
    }

    final version = _safeString(_appVersion).split('+').first;
    final policyDecision = AppReviewPolicy.evaluate(
      platform: platform,
      appVersion: version,
      now: now,
      firstSeen: state.firstSeen,
      distinctReadingDays: state.readingDays.length,
      attempts: state.attempts.map((attempt) => attempt.toPolicyAttempt()),
      migratedAt: state.migratedAt,
      attemptedThisSession: _attemptedThisSession,
    );
    if (policyDecision != AppReviewDecision.eligible) {
      _opportunity(momentName, policyDecision);
      return;
    }

    final firstLifecycleCheck = _safeLifecycleCheck(isStillAppropriate);
    if (!firstLifecycleCheck) {
      _opportunity(momentName, AppReviewDecision.lifecycleNotAppropriate);
      return;
    }

    // Set the session latch before entering the native availability path so a
    // slow or unavailable store cannot be hammered by repeated callbacks. The
    // durable attempt is reserved only once availability and lifecycle checks
    // pass, immediately before requestReview.
    _attemptedThisSession = true;

    bool available;
    try {
      available = await _isAvailable();
    } catch (_) {
      _opportunity(momentName, AppReviewDecision.availabilityError);
      return;
    }

    final secondLifecycleCheck = _safeLifecycleCheck(isStillAppropriate);
    if (!secondLifecycleCheck) {
      _opportunity(momentName, AppReviewDecision.lifecycleChanged);
      return;
    }
    if (!available) {
      _opportunity(momentName, AppReviewDecision.unavailable);
      return;
    }

    state.attempts.add(_StoredAttempt(atMs: now.millisecondsSinceEpoch, version: version));
    if (state.attempts.length > AppReviewPolicy.maximumStoredAttempts) {
      state.attempts.removeRange(0, state.attempts.length - AppReviewPolicy.maximumStoredAttempts);
    }
    if (!await _persistState(storage, state)) {
      _opportunity(momentName, AppReviewDecision.storageError);
      return;
    }

    // Persistence itself yields to the event loop. Recheck immediately before
    // entering the platform prompt so a disposed route cannot launch it.
    if (!_safeLifecycleCheck(isStillAppropriate)) {
      _opportunity(momentName, AppReviewDecision.lifecycleChanged);
      return;
    }

    _opportunity(momentName, AppReviewDecision.eligible);
    _telemetrySafe('App Review Request Attempted', <String, Object>{'moment': momentName});
    try {
      await _requestNativeReview();
      _finished(momentName, 'returned');
    } catch (_) {
      _finished(momentName, 'error');
    }
  }

  Future<SharedPreferences?> _storage() async {
    if (_storageBroken) return null;
    if (_providedStorage != null) return _providedStorage;
    try {
      _storageFuture ??= SharedPreferences.getInstance();
      return await _storageFuture!;
    } catch (_) {
      _storageBroken = true;
      return null;
    }
  }

  Future<_ReviewState?> _loadState(SharedPreferences storage, DateTime now) async {
    if (_storageBroken) return null;
    _ReviewState state;
    try {
      final raw = storage.getString(_stateKey);
      if (raw == null) {
        state = _ReviewState.empty();
      } else {
        state = _ReviewState.fromJson(jsonDecode(raw));
      }
      _validateState(state, now);
    } catch (_) {
      _storageBroken = true;
      return null;
    }

    if (state.migrationComplete) return state;

    bool legacyFlag(String key) => storage.get(key) == true;
    final hadLegacyPrompt =
        legacyFlag(_legacyPromptKey) || legacyFlag(_legacyConversationKey) || legacyFlag(_legacyActionItemKey);
    state
      ..migrationComplete = true
      ..migratedAtMs = hadLegacyPrompt ? now.millisecondsSinceEpoch : null;
    if (!await _persistState(storage, state)) return null;
    return state;
  }

  Future<bool> _persistState(SharedPreferences storage, _ReviewState state) async {
    if (_storageBroken) return false;
    try {
      final encoded = jsonEncode(state.toJson());
      final ok =
          _writeState == null ? await storage.setString(_stateKey, encoded) : await _writeState!(_stateKey, encoded);
      if (!ok) {
        _storageBroken = true;
        return false;
      }
      return true;
    } catch (_) {
      _storageBroken = true;
      return false;
    }
  }

  void _validateState(_ReviewState state, DateTime now) {
    final nowMs = now.millisecondsSinceEpoch;
    void validTimestamp(int? timestamp) {
      if (timestamp != null && (timestamp < 0 || timestamp > nowMs)) {
        throw const FormatException('invalid review timestamp');
      }
    }

    validTimestamp(state.firstSeenAtMs);
    validTimestamp(state.migratedAtMs);
    if (state.readingDays.length > AppReviewPolicy.maximumStoredReadingDays ||
        state.attempts.length > AppReviewPolicy.maximumStoredAttempts) {
      throw const FormatException('review history exceeds bound');
    }

    final currentDay = _localDayKey(now);
    final seenDays = <String>{};
    for (final day in state.readingDays) {
      if (!_isDayKey(day) || !seenDays.add(day) || day.compareTo(currentDay) > 0) {
        throw const FormatException('invalid review engagement day');
      }
      if (state.firstSeenAtMs != null) {
        final firstDay = _localDayKey(DateTime.fromMillisecondsSinceEpoch(state.firstSeenAtMs!));
        if (day.compareTo(firstDay) < 0) {
          throw const FormatException('engagement precedes first seen');
        }
      }
    }

    for (final attempt in state.attempts) {
      validTimestamp(attempt.atMs);
      if (attempt.version.isEmpty || attempt.version.length > 256) {
        throw const FormatException('invalid review version');
      }
    }
  }

  bool _safeLifecycleCheck(bool Function() check) {
    try {
      return check();
    } catch (_) {
      return false;
    }
  }

  String _safeString(String Function() getter) {
    try {
      return getter().trim();
    } catch (_) {
      return '';
    }
  }

  Future<T> _enqueue<T>(Future<T> Function() operation) {
    final result = _operationQueue.then<T>((_) => operation());
    _operationQueue = result.then<void>((_) {}, onError: (_, __) {});
    return result;
  }

  void _opportunity(String moment, AppReviewDecision decision) {
    _telemetrySafe('App Review Opportunity', <String, Object>{
      'moment': moment,
      'decision': decision.telemetryName,
    });
  }

  void _finished(String moment, String result) {
    _telemetrySafe('App Review Request Finished', <String, Object>{
      'moment': moment,
      'result': result,
    });
  }

  void _telemetrySafe(String eventName, Map<String, Object> properties) {
    try {
      _telemetry(eventName, properties);
    } catch (_) {
      // Telemetry must never change review eligibility or block the prompt.
    }
  }

  static String _localDayKey(DateTime instant) {
    final local = instant.toLocal();
    String twoDigits(int value) => value.toString().padLeft(2, '0');
    return '${local.year.toString().padLeft(4, '0')}-${twoDigits(local.month)}-${twoDigits(local.day)}';
  }

  static bool _isDayKey(String value) {
    final match = RegExp(r'^\d{4}-\d{2}-\d{2}$').firstMatch(value);
    if (match == null) return false;
    final pieces = value.split('-').map(int.parse).toList(growable: false);
    final parsed = DateTime(pieces[0], pieces[1], pieces[2]);
    return parsed.year == pieces[0] && parsed.month == pieces[1] && parsed.day == pieces[2];
  }

  static String _productionAppVersion() => PlatformManager.instance.appVersion;

  static String _currentPlatform() => Platform.operatingSystem;

  static void _productionTelemetry(String eventName, Map<String, Object> properties) {
    final momentName = properties['moment'];
    if (momentName is! String) return;
    switch (eventName) {
      case 'App Review Opportunity':
        final decisionName = properties['decision'];
        if (decisionName is! String) return;
        final moment = AppReviewOpportunityMoment.values.firstWhere(
          (value) => value.wireName == momentName,
          orElse: () => throw StateError('unknown app review moment'),
        );
        final decision = AppReviewOpportunityDecision.values.firstWhere(
          (value) => value.wireName == decisionName,
          orElse: () => throw StateError('unknown app review decision'),
        );
        const TypedEvents().emit(AppReviewOpportunity(moment: moment, decision: decision));
      case 'App Review Request Attempted':
        final moment = AppReviewRequestAttemptedMoment.values.firstWhere(
          (value) => value.wireName == momentName,
          orElse: () => throw StateError('unknown app review moment'),
        );
        const TypedEvents().emit(AppReviewRequestAttempted(moment: moment));
      case 'App Review Request Finished':
        final resultName = properties['result'];
        if (resultName is! String) return;
        final moment = AppReviewRequestFinishedMoment.values.firstWhere(
          (value) => value.wireName == momentName,
          orElse: () => throw StateError('unknown app review moment'),
        );
        final result = AppReviewRequestFinishedResult.values.firstWhere(
          (value) => value.wireName == resultName,
          orElse: () => throw StateError('unknown app review result'),
        );
        const TypedEvents().emit(AppReviewRequestFinished(moment: moment, result: result));
    }
  }
}

final class _StoredAttempt {
  const _StoredAttempt({required this.atMs, required this.version});

  final int atMs;
  final String version;

  factory _StoredAttempt.fromJson(Object? raw) {
    if (raw is! Map) throw const FormatException('invalid review attempt');
    final atMs = raw['atMs'];
    final version = raw['version'];
    if (atMs is! int || version is! String) {
      throw const FormatException('invalid review attempt fields');
    }
    return _StoredAttempt(atMs: atMs, version: version);
  }

  Map<String, Object> toJson() => <String, Object>{'atMs': atMs, 'version': version};

  AppReviewAttempt toPolicyAttempt() => AppReviewAttempt(
        at: DateTime.fromMillisecondsSinceEpoch(atMs),
        version: version,
      );
}

final class _ReviewState {
  _ReviewState({
    required this.migrationComplete,
    required this.migratedAtMs,
    required this.firstSeenAtMs,
    required this.readingDays,
    required this.attempts,
  });

  factory _ReviewState.empty() => _ReviewState(
        migrationComplete: false,
        migratedAtMs: null,
        firstSeenAtMs: null,
        readingDays: <String>{},
        attempts: <_StoredAttempt>[],
      );

  factory _ReviewState.fromJson(Object? raw) {
    if (raw is! Map || raw['schema'] != 1 || raw['migrationComplete'] is! bool) {
      throw const FormatException('invalid review state');
    }
    final migrationAt = raw['migratedAtMs'];
    final firstSeenAt = raw['firstSeenAtMs'];
    final rawDays = raw['readingDays'];
    final rawAttempts = raw['attempts'];
    if ((migrationAt != null && migrationAt is! int) ||
        (firstSeenAt != null && firstSeenAt is! int) ||
        rawDays is! List ||
        rawAttempts is! List) {
      throw const FormatException('invalid review state fields');
    }
    return _ReviewState(
      migrationComplete: raw['migrationComplete'] as bool,
      migratedAtMs: migrationAt as int?,
      firstSeenAtMs: firstSeenAt as int?,
      readingDays: rawDays.map((value) => value is String ? value : throw const FormatException('invalid day')).toSet(),
      attempts: rawAttempts.map(_StoredAttempt.fromJson).toList(growable: true),
    );
  }

  bool migrationComplete;
  int? migratedAtMs;
  int? firstSeenAtMs;
  Set<String> readingDays;
  List<_StoredAttempt> attempts;

  DateTime? get firstSeen => firstSeenAtMs == null ? null : DateTime.fromMillisecondsSinceEpoch(firstSeenAtMs!);
  DateTime? get migratedAt => migratedAtMs == null ? null : DateTime.fromMillisecondsSinceEpoch(migratedAtMs!);

  Map<String, Object?> toJson() => <String, Object?>{
        'schema': 1,
        'migrationComplete': migrationComplete,
        'migratedAtMs': migratedAtMs,
        'firstSeenAtMs': firstSeenAtMs,
        'readingDays': readingDays.toList()..sort(),
        'attempts': attempts.map((attempt) => attempt.toJson()).toList(growable: false),
      };
}
