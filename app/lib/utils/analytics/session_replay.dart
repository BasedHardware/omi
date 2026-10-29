import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/widgets.dart';
import 'package:posthog_flutter/posthog_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/env/env.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/experiments/session_replay_gate.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_service.dart';

/// PostHog mobile session replay, off unless the `mobile-session-replay` flag turns it on.
///
/// Setup never records: `PostHogConfig.sessionReplay` stays false because project 302298 has
/// "Record user sessions" on, so that switch would record every user from launch. Recording starts
/// through the SDK's start API once the flag resolves true for the settled analytics identity, and
/// stops when product analytics is turned off, the identity changes, the app leaves the foreground,
/// or the server hides subscription UI (App Review, also BYOK and reviewer accounts). Frames are not
/// masked: a recording shows the screen as the user sees it.
class SessionReplay {
  SessionReplay({
    ValueListenable<bool>? consent,
    ValueListenable<String?>? identity,
    Future<bool> Function(String key)? readFlag,
    bool Function()? sandboxInstall,
    bool? forceFlag,
    Future<void> Function()? start,
    Future<void> Function()? stop,
    Future<bool> Function()? isRecording,
    void Function()? requestFrame,
    this.activationChecks = const [Duration(seconds: 2), Duration(seconds: 3), Duration(seconds: 5)],
  })  : _consent = consent ?? AnalyticsManager.trackingConsent,
        _identity = identity ?? AnalyticsManager.settledIdentity,
        _readFlag = readFlag ?? AnalyticsManager().refreshBooleanFeatureFlag,
        _sandboxInstall = sandboxInstall ?? (() => Env.isTestFlight),
        _forceFlag = forceFlag ?? SessionReplayGate.debugOverrideActive,
        _start = start ?? (() => Posthog().startSessionRecording(resumeCurrent: true)),
        _stop = stop ?? Posthog().stopSessionRecording,
        _isRecording = isRecording ?? Posthog().isSessionReplayActive,
        _requestFrame = requestFrame ?? (() => SchedulerBinding.instance.scheduleFrame());

  static final SessionReplay instance = SessionReplay();

  /// At most one screenshot every 2 s (the SDK default is 1 s). Each capture walks the
  /// widget tree and hashes the frame on the UI isolate (INV-PERF-1); an unchanged frame is not sent.
  static const throttleDelay = Duration(seconds: 2);

  /// True once a config carrying these settings went to `Posthog().setup` (which stores it before
  /// its first await). `PostHogWidget` follows recording toggles only if setup ran before it
  /// mounted; setup runs during app start-up, well before the first frame.
  static bool get configured => _configured;
  static bool _configured = false;

  /// Replay settings for `Posthog().setup`. The SDK masks every text and image by default; replay
  /// here records the screen unmasked.
  static void configure(PostHogConfig config) {
    _configured = config.projectToken.isNotEmpty; // the SDK skips setup for a blank token
    config.sessionReplay = false;
    config.sessionReplayConfig
      ..maskAllTexts = false
      ..maskAllImages = false
      ..throttleDelay = throttleDelay;
  }

  final ValueListenable<bool> _consent;
  final ValueListenable<String?> _identity;
  final Future<bool> Function(String key) _readFlag;
  final bool Function() _sandboxInstall;
  final bool _forceFlag;
  final Future<void> Function() _start;
  final Future<void> Function() _stop;
  final Future<bool> Function() _isRecording;
  final void Function() _requestFrame;

  /// Waits after a start before asking the native SDK whether it records. It can decline silently
  /// (project recording off, a sample rate, opted out), and the Dart capture ticker must not keep
  /// screenshotting frames nobody receives.
  final List<Duration> activationChecks;

  bool _attached = false;
  bool _flag = false;
  bool? _appReview;
  bool _foreground = true;
  bool _recording = false;
  Timer? _frameTicker;
  bool _declined = false;
  int _identityGeneration = 0;
  int _recordingGeneration = 0;

  /// True from a start request until the next stop.
  @visibleForTesting
  bool get recording => _recording;

  /// Starts following consent and identity; idempotent.
  void attach() {
    if (_attached) return;
    _attached = true;
    _consent.addListener(_apply);
    _identity.addListener(_onIdentity);
    _onIdentity();
  }

  void detach() {
    if (!_attached) return;
    _attached = false;
    _consent.removeListener(_apply);
    _identity.removeListener(_onIdentity);
    _identityGeneration++;
    _flag = false;
    if (_recording) _stopRecording();
  }

  /// The server's App Review answer (subscription UI hidden), or null until the subscription loads.
  set appReview(bool? value) {
    if (value == _appReview) return;
    _appReview = value;
    _apply();
  }

  /// Capture runs only in the foreground: in the background the SDK's ticker would keep queueing a
  /// frame callback every tick with no frame to run it.
  set foreground(bool value) {
    if (value == _foreground) return;
    _foreground = value;
    _apply();
  }

  void _onIdentity() {
    final generation = ++_identityGeneration;
    _flag = false;
    _declined = false;
    _apply(); // a recording made for the previous identity stops here
    if (_identity.value == null || !_consent.value) return;
    unawaited(_resolveFlag(generation));
  }

  Future<void> _resolveFlag(int generation) async {
    bool enabled;
    try {
      enabled = _forceFlag || await _readFlag(SessionReplayGate.enabledFlag);
    } catch (_) {
      enabled = false;
    }
    if (generation != _identityGeneration) return;
    _flag = enabled;
    _apply();
  }

  void _apply() {
    final allowed = _attached &&
        _foreground &&
        SessionReplayGate.allowed(
          trackingEnabled: _consent.value,
          flagEnabled: _flag && _identity.value != null,
          appReview: _appReview,
          sandboxInstall: _sandboxInstall(),
        );
    if (allowed && !_recording && !_declined) {
      unawaited(_startRecording());
    } else if (!allowed && _recording) {
      _stopRecording();
    }
  }

  Future<void> _startRecording() async {
    final generation = ++_recordingGeneration;
    _recording = true;
    try {
      await _start();
      if (generation != _recordingGeneration) return;
      // The SDK captures on the first frame after each tick, so a screen that settles between two
      // ticks and then stays still would replay as the screen before it. A frame per tick bounds that.
      _requestFrame();
      _frameTicker = Timer.periodic(throttleDelay, (_) => _requestFrame());
      for (final wait in activationChecks) {
        await Future<void>.delayed(wait);
        if (generation != _recordingGeneration) return;
        if (await _isRecording()) {
          Logger.debug('Session replay recording');
          return;
        }
      }
    } catch (_) {}
    if (generation != _recordingGeneration) return;
    Logger.debug('Session replay declined by the SDK; stopped until the identity changes');
    _declined = true;
    _stopRecording();
  }

  void _stopRecording() {
    _frameTicker?.cancel();
    _frameTicker = null;
    _recordingGeneration++;
    _recording = false;
    unawaited(_stop().catchError((Object _) {}));
  }
}

/// Puts PostHog's replay root over the app and tells [SessionReplay] about App Review and the
/// app's lifecycle. A passthrough where replay cannot run (no PostHog key, not iOS/Android).
class SessionReplayScope extends StatefulWidget {
  const SessionReplayScope({super.key, required this.child});

  final Widget child;

  @override
  State<SessionReplayScope> createState() => _SessionReplayScopeState();
}

class _SessionReplayScopeState extends State<SessionReplayScope> with WidgetsBindingObserver {
  late final bool _enabled = SessionReplay.configured && PlatformService.isMobile;
  UsageProvider? _usage;

  @override
  void initState() {
    super.initState();
    if (!_enabled) return;
    WidgetsBinding.instance.addObserver(this);
    final state = WidgetsBinding.instance.lifecycleState;
    SessionReplay.instance
      ..foreground = state == null || _isForeground(state)
      ..attach();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_enabled) return;
    final usage = Provider.of<UsageProvider?>(context, listen: false);
    if (identical(usage, _usage)) return;
    _usage?.removeListener(_onUsage);
    _usage = usage?..addListener(_onUsage);
    _onUsage();
  }

  void _onUsage() {
    final subscription = _usage?.subscription;
    SessionReplay.instance.appReview = subscription == null ? null : !subscription.showSubscriptionUi;
  }

  static bool _isForeground(AppLifecycleState state) =>
      state == AppLifecycleState.resumed || state == AppLifecycleState.inactive;

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    SessionReplay.instance.foreground = _isForeground(state);
  }

  @override
  void dispose() {
    if (_enabled) {
      WidgetsBinding.instance.removeObserver(this);
      _usage?.removeListener(_onUsage);
      SessionReplay.instance.detach();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => _enabled ? PostHogWidget(child: widget.child) : widget.child;
}
