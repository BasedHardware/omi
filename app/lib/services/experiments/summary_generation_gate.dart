import 'package:flutter/foundation.dart';

import 'package:omi/utils/analytics/analytics_manager.dart';

/// Client presentation gate for the conversation-detail summary redesign: the "Not summarized yet"
/// card, the "Summarize with" template sheet, the summary source chips and the inline failure
/// cards. Reliability fixes and the single in-tab progress state ship without it.
///
/// Lifecycle: rollout; owner: dazheng; default off. Fail-closed: no analytics identity, a slow read
/// or an error all mean off. The page reads [isEnabled] synchronously; [refresh] resolves the
/// PostHog flag once per detail page open and [listenable] rebuilds the summary tab when it lands.
abstract final class SummaryGenerationV2Gate {
  /// PostHog flag key.
  static const enabledFlag = 'summary-generation-v2';

  /// Debug builds only: `--dart-define=OMI_SUMMARY_GENERATION_V2=true` forces the redesign on.
  static const _debugForce = bool.fromEnvironment('OMI_SUMMARY_GENERATION_V2');

  static final ValueNotifier<bool> _enabled = ValueNotifier<bool>(false);

  /// Guards [refresh]: only the newest call may publish, so an older overlapping read cannot
  /// overwrite a newer decision.
  static int _refreshGeneration = 0;

  /// Tests force the gate with this (reset it in a tearDown); null reads the flag.
  @visibleForTesting
  static bool? debugOverride;

  /// Whether the redesign is on right now.
  static bool get isEnabled => debugOverride ?? ((kDebugMode && _debugForce) || _enabled.value);

  /// Notifies when [refresh] changes the flag's value.
  static ValueListenable<bool> get listenable => _enabled;

  /// Re-reads the flag. Never throws; failure leaves the redesign off. The cached value is
  /// cleared while the read is pending (fail-closed) and a stale overlapping read can never
  /// publish over a newer one.
  static Future<bool> refresh({Future<bool> Function(String key)? readFlag}) async {
    final generation = ++_refreshGeneration;
    _enabled.value = false;
    bool enabled;
    try {
      enabled =
          await (readFlag ?? AnalyticsManager().isFeatureEnabled)(enabledFlag).timeout(const Duration(seconds: 2));
    } catch (_) {
      enabled = false;
    }
    if (generation != _refreshGeneration) return isEnabled;
    _enabled.value = enabled;
    return isEnabled;
  }
}
