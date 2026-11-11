/// Recoverable diagnostics must never escape into the global uncaught-error
/// handler, including when Crashlytics itself is unavailable.
Future<void> recordNonFatalFailure(
  Object error,
  StackTrace stack, {
  required Future<void> Function(Object, StackTrace, {required bool fatal}) record,
  required Future<void> Function(String, String) setAttribute,
  Map<String, String> attributes = const {},
}) async {
  for (final entry in attributes.entries) {
    try {
      await setAttribute(entry.key, entry.value);
    } catch (_) {
      // A failed attribute write must not suppress the event itself.
    }
  }
  try {
    await record(error, stack, fatal: false);
  } catch (_) {
    // A diagnostics transport failure cannot turn a handled fetch into a crash.
  }
}
