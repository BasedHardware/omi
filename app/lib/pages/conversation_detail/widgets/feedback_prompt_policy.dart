import 'dart:async';
import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';

enum FeedbackPromptKind { summary, recording }

/// Chooses one feedback population before either prompt is mounted. The
/// recording branch gets a separate hash byte so it does not share the
/// sampling bucket with the prompt budget itself. A summary is the fallback
/// when no completed recording is eligible; app-result summaries stay out of
/// this population until their result coordinates are part of the wire.
FeedbackPromptKind? feedbackPromptKindForTarget({
  required String targetId,
  required bool hasSummary,
  required bool hasRecording,
}) {
  if (!hasSummary && !hasRecording) return null;
  if (!hasRecording) return hasSummary ? FeedbackPromptKind.summary : null;
  if (!hasSummary) return FeedbackPromptKind.recording;
  if (targetId.isEmpty || targetId.length > 256) return null;
  final digest = sha256.convert(utf8.encode(targetId)).bytes;
  return (digest[4] & 1) == 0 ? FeedbackPromptKind.summary : FeedbackPromptKind.recording;
}

/// Local sampling and suppression policy for sparse feedback prompts.
///
/// The budget is shared by all feedback kinds, so a summary and a recording
/// prompt cannot stack on the same detail view or appear repeatedly during a
/// short session. Only bounded opaque target IDs are stored locally; they are
/// never emitted as analytics properties by this policy.
class FeedbackPromptPolicy {
  FeedbackPromptPolicy({
    Future<SharedPreferences> Function()? preferencesLoader,
    DateTime Function()? now,
    String? Function()? ownerKey,
    this.sampleFraction = defaultSampleFraction,
  })  : _preferencesLoader = preferencesLoader ?? SharedPreferences.getInstance,
        _now = now ?? DateTime.now,
        _ownerKey = ownerKey ?? (() => AnalyticsManager.currentIdentity) {
    if (sampleFraction < 0 || sampleFraction > 1) {
      throw ArgumentError.value(sampleFraction, 'sampleFraction', 'must be between 0 and 1');
    }
  }

  static final FeedbackPromptPolicy instance = FeedbackPromptPolicy();

  static const double defaultSampleFraction = 0.25;
  static const Duration cooldown = Duration(days: 7);
  static const int maxSuppressedTargets = 64;
  static const String _lastExposureKey = 'mobile_feedback_prompt_last_exposure_ms';
  static const String _suppressedTargetsKey = 'mobile_feedback_prompt_suppressed_targets';

  final Future<SharedPreferences> Function() _preferencesLoader;
  final DateTime Function() _now;
  final String? Function() _ownerKey;
  final double sampleFraction;
  Future<void> _serialQueue = Future<void>.value();

  /// Returns whether the target is eligible without consuming the shared
  /// prompt budget. Unknown or malformed preferences fail closed.
  Future<bool> canShow(String targetId) async {
    try {
      final scope = _scopeKey();
      if (scope == null) return false;
      return await _serial(() async {
        try {
          final preferences = await _preferencesLoader();
          return _eligible(preferences, targetId, _now(), scope);
        } catch (_) {
          return false;
        }
      });
    } catch (_) {
      return false;
    }
  }

  /// Atomically consumes the shared prompt budget for one visible target.
  /// Calling this after viewport visibility is known makes the resulting
  /// Product Journey Started event a true feedback exposure.
  Future<bool> claim(String targetId) async {
    try {
      final scope = _scopeKey();
      if (scope == null) return false;
      return await _serial(() async {
        try {
          final preferences = await _preferencesLoader();
          final now = _now();
          if (!_eligible(preferences, targetId, now, scope)) return false;
          final saved = await preferences.setInt(_scopedKey(_lastExposureKey, scope), now.millisecondsSinceEpoch);
          return saved;
        } catch (_) {
          return false;
        }
      });
    } catch (_) {
      return false;
    }
  }

  /// Suppress a target after a successful answer or explicit dismissal. The
  /// bounded list prevents unbounded local growth while retaining recent
  /// decisions.
  Future<void> recordDecision(String targetId) async {
    try {
      final scope = _scopeKey();
      if (scope == null) return;
      await _serial(() async {
        try {
          if (!_validTarget(targetId)) return;
          final preferences = await _preferencesLoader();
          final key = _scopedKey(_suppressedTargetsKey, scope);
          final targets = _readSuppressedTargets(preferences, key);
          if (targets == null) return;
          final next = <String>[...targets.where((value) => value != targetId), targetId];
          await preferences.setStringList(
            key,
            next.length <= maxSuppressedTargets ? next : next.sublist(next.length - maxSuppressedTargets),
          );
        } catch (_) {
          // Prompt suppression is best effort; telemetry and product behavior
          // remain fail-open after a completed response.
        }
      });
    } catch (_) {
      // Preferences are an optional local optimization. Never surface a
      // loader or queue failure from an unawaited UI task.
    }
  }

  bool _eligible(SharedPreferences preferences, String targetId, DateTime now, String scope) {
    if (!_validTarget(targetId)) return false;
    final lastExposureKey = _scopedKey(_lastExposureKey, scope);
    final suppressedTargetsKey = _scopedKey(_suppressedTargetsKey, scope);
    final lastExposure = _readLastExposure(preferences, lastExposureKey);
    if (lastExposure == null && preferences.containsKey(lastExposureKey)) return false;
    if (lastExposure != null && now.isBefore(lastExposure.add(cooldown))) return false;
    final suppressedTargets = _readSuppressedTargets(preferences, suppressedTargetsKey);
    if (suppressedTargets == null || suppressedTargets.contains(targetId)) return false;
    return _sample(targetId);
  }

  DateTime? _readLastExposure(SharedPreferences preferences, String key) {
    try {
      final value = preferences.getInt(key);
      return value == null ? null : DateTime.fromMillisecondsSinceEpoch(value);
    } catch (_) {
      return null;
    }
  }

  List<String>? _readSuppressedTargets(SharedPreferences preferences, String key) {
    if (!preferences.containsKey(key)) return <String>[];
    try {
      final values = preferences.getStringList(key);
      if (values == null || values.any((value) => !_validTarget(value))) return null;
      return values;
    } catch (_) {
      return null;
    }
  }

  bool _sample(String targetId) {
    if (sampleFraction >= 1) return true;
    if (sampleFraction <= 0) return false;
    final digest = sha256.convert(utf8.encode(targetId)).bytes;
    var bucket = 0;
    for (final byte in digest.take(4)) {
      bucket = (bucket << 8) | byte;
    }
    return (bucket / 0x100000000) < sampleFraction;
  }

  bool _validTarget(String value) => value.isNotEmpty && value.length <= 256;

  String? _scopeKey() {
    try {
      final owner = _ownerKey()?.trim();
      if (owner == null || owner.isEmpty || owner.length > 256) return null;
      // Keep the local preference namespace unlinkable to the canonical user
      // identifier while retaining deterministic per-user isolation.
      return sha256.convert(utf8.encode(owner)).toString().substring(0, 16);
    } catch (_) {
      return null;
    }
  }

  String _scopedKey(String base, String scope) => '${base}_$scope';

  Future<T> _serial<T>(Future<T> Function() operation) async {
    final previous = _serialQueue;
    final release = Completer<void>();
    _serialQueue = release.future;
    await previous;
    try {
      return await operation();
    } finally {
      release.complete();
    }
  }
}
