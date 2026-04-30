import 'package:hive/hive.dart';

/// Hive box names for the Companion Stream Home.
///
/// All three are opened in `main()` before `runApp` (parallel via `Future.wait`).
/// They persist across launches and survive `OnboardingChatProvider.reset()`
/// EXCEPT when reset explicitly wipes them via [clearAll].
class HomeBoxes {
  HomeBoxes._();

  /// Serialized `CompanionCard.toJson()` rows, keyed by `id`. Persists the
  /// rendered stream so cards don't vanish on app restart. TTL enforcement
  /// happens on Home foreground.
  static const String cards = 'home.cards.v1';

  /// Cached morning-brief LLM response, keyed by `YYYY-MM-DD` (PR2 scope).
  /// Re-fetched only when the date key rolls over.
  static const String brief = 'home.brief.v1';

  /// Card-action history rows: `{id, action, ts, until?}`. Generators consult
  /// this box and skip emitting any card whose `id` already has a `dismiss`
  /// row. Snooze rows include an `until` timestamp.
  static const String actions = 'home.actions.v1';

  /// Wipes the rendered stream, the cached brief, and the action history so
  /// the next Home build behaves like a cold start. Used by the debug "Reset
  /// onboarding" flow to give a true clean slate.
  static Future<void> clearAll() async {
    await Future.wait([
      Hive.box<Map>(cards).clear(),
      Hive.box<Map>(brief).clear(),
      Hive.box<Map>(actions).clear(),
    ]);
  }
}
