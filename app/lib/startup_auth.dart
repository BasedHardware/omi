/// How long startup will wait for an id-token refresh before giving up and
/// continuing unauthenticated. Generous enough not to log out a user on a slow
/// network, short enough that a stalled refresh cannot hold the first frame.
const Duration startupAuthTimeout = Duration(seconds: 10);

/// Resolve whether startup has a usable session, without ever blocking forever.
///
/// This runs before `runApp()`, so an unbounded stall here leaves the launch
/// storyboard on screen indefinitely — no crash, no UI, no diagnostic. Measured
/// on iPhone 17 Pro / iOS 27.0 against a Firebase Auth emulator on a non-loopback
/// host, FirebaseAuth's forced token refresh never returned at all (not an error,
/// just silence), and the app could not be launched again until it was deleted,
/// because the cached session made every start hang on this call.
///
/// A timeout is deliberately treated as "not authenticated" rather than as an
/// error: [getIdToken] already returns null on every failure branch, and startup
/// already continues to the sign-in screen in that case. So this only makes a
/// hang behave like the failure it effectively is, and never blocks startup where
/// the previous code would have proceeded.
///
/// Kept in its own library, free of Firebase and generated-env imports, so it is
/// testable without codegen — the same reason `startup_routing.dart` is separate.
///
/// Not test-only: called from [main] to gate the first frame, and directly by
/// startup_auth_timeout_test.dart.
Future<bool> resolveStartupAuth(
  Future<String?> Function() getIdToken, {
  Duration timeout = startupAuthTimeout,
}) async {
  // A race rather than Future.timeout(onTimeout:). `onTimeout` must return the
  // *concrete* future's type, so if the supplied callback happens to produce a
  // Future<String> rather than Future<String?>, `() => null` throws a TypeError
  // at runtime — turning a hang-guard into a new startup crash. Racing sidesteps
  // the variance entirely.
  return await Future.any<bool>([
    getIdToken().then((token) => token != null),
    Future<bool>.delayed(timeout, () => false),
  ]);
}
