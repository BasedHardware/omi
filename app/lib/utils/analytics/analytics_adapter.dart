/// Provider-agnostic primitives every analytics SDK wrapper must satisfy.
///
/// Adding a new analytics SDK is one file under `analytics/adapters/` plus
/// a single `AnalyticsManager.configure(...)` call at boot. No call site in
/// the rest of the app needs to know which adapter is active.
abstract class AnalyticsAdapter {
  /// Initialize the underlying SDK. Calls before this resolves should be no-ops
  /// inside the implementation, so the manager can fan calls through without
  /// branching on init state.
  Future<void> init();

  /// True once `init()` has resolved successfully.
  bool get isInitialized;

  /// Identify the current user. Pass `userProperties` to set them in the same
  /// call (most SDKs accept this fused shape and it's cheaper than a separate
  /// set-property call).
  void identify({required String userId, Map<String, Object>? userProperties});

  /// Link an existing anonymous identity to a known user id.
  void alias({required String newUserId});

  /// Capture a single event with optional properties.
  void track({required String eventName, Map<String, Object>? properties});

  /// Resume capture after a previous `disable()`.
  void enable();

  /// Stop capture. Calls between `disable()` and the next `enable()` are
  /// dropped by the underlying SDK.
  void disable();

  /// Forget the current identity (e.g. on logout). Does not disable capture.
  void reset();
}
