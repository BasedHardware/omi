/// Typed, versioned semantic controls for local development builds (C2 lane
/// of the mobile development foundation, SCA-488).
///
/// This module extends the existing debug `MarionetteBinding` surface — the
/// transport stays the debug VM service (`ext.omi.controls.*` extensions),
/// registered alongside Marionette's own `ext.marionette.*` extensions. It
/// does not add a second transport, server, or UI automation framework.
///
/// What it adds over Marionette's tree/tap/enterText primitives is product
/// semantics: named readiness conditions with bounded polling, the app's real
/// navigation path, typed actions that call the same production
/// services/controllers the UI calls, and the privileged seed/reset/fault
/// controls the seeded journeys need. State is privacy-safe: identity is
/// uid/email/flags, never tokens or raw credentials.
///
/// Eligibility is fail-closed and compile-time-resolvable:
/// `kDebugMode` excludes profile/release/AOT builds, and
/// `Env.profile == AppEnvironmentProfile.localDev` excludes production-family
/// builds *including production-flavor debug builds*. An explicit
/// `OMI_DEV_CONTROLS=1` dart-define is additionally required so an ordinary
/// debug build never exposes privileged controls unasked. When ineligible,
/// every entrypoint here is inert: [installIfEligible] is a no-op, the fault
/// gate passes requests through untouched, and no VM service extension is
/// registered. `semantic_controls_guard_test.dart` pins exactly that.
library;

import 'dart:async';
import 'dart:convert' show JsonEncoder;
import 'dart:developer' as developer;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/env/environment_profile.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/dev_controls/journey_faults.dart';
import 'package:omi/utils/enums.dart';

/// Version of the semantic-controls contract. Bump on any breaking change;
/// additive capabilities append without a bump.
const String semanticControlsVersion = 'semantic-controls/v1';

/// Compile-time opt-in for privileged dev controls. Deliberately a
/// dart-define, not a runtime flag: it cannot be flipped on a built artifact.
const String _controlsDefine = String.fromEnvironment('OMI_DEV_CONTROLS');

/// True only in local test builds: debug JIT, `local_dev` profile, explicit
/// opt-in. Everything below keys off this single predicate.
bool get semanticControlsEligible =>
    kDebugMode && Env.profile == AppEnvironmentProfile.localDev && _controlsDefine == '1';

/// The named semantic conditions [SemanticControls.waitReady] can poll.
///
/// Conditions are product-meaningful states, not widget-count heuristics. Each
/// id maps to a synchronous probe below; polling is bounded by a deadline and
/// never by fixed sleeps.
enum SemanticReadiness {
  /// A signed-in, non-anonymous principal is present (SharedPreferences uid
  /// set + auth provider reports signed-in, when a context is available).
  signedIn,

  /// The navigator has a mounted route below it.
  routed,

  /// No capture recording is active (safe point for seed/reset).
  captureIdle,
}

class SemanticPrincipal {
  const SemanticPrincipal({
    required this.uid,
    required this.email,
    required this.signedIn,
    required this.requiresReauthentication,
  });

  final String uid;
  final String email;
  final bool signedIn;
  final bool requiresReauthentication;

  /// Privacy-safe projection: uid/email identity and auth flags only. Never a
  /// token, never preferences beyond identity.
  Map<String, Object?> toJson() => {
        'uid': uid,
        'email': email,
        'signed_in': signedIn,
        'requires_reauthentication': requiresReauthentication,
      };
}

class SemanticCaptureState {
  const SemanticCaptureState({
    required this.activeRecordingId,
    required this.activeCaptureSessionId,
    required this.recordingState,
    required this.backlogObservability,
  });

  /// Per-recording identity. Authoritative for journeys (see the
  /// capture-scenario/v1 contract: `activeCaptureSessionId` is the
  /// conversation/WAL window and can stay stale across sequential phone-mic
  /// live sessions — never assert its uniqueness across stop/next-start).
  final String? activeRecordingId;
  final String? activeCaptureSessionId;
  final String recordingState;

  /// Honest label for the upload-backlog field: 'unavailable-live' when no
  /// live capture surface is reachable from the navigator context (e.g. the
  /// capture journey runs through the deterministic replay adapter instead).
  final String backlogObservability;

  Map<String, Object?> toJson() => {
        'active_recording_id': activeRecordingId,
        'active_capture_session_id': activeCaptureSessionId,
        'recording_state': recordingState,
        'upload_backlog': backlogObservability,
      };
}

class SemanticState {
  const SemanticState({
    required this.contractVersion,
    required this.profile,
    required this.route,
    required this.principal,
    required this.capture,
    required this.readiness,
    required this.faultsArmed,
  });

  final String contractVersion;
  final String profile;
  final String route;
  final SemanticPrincipal principal;
  final SemanticCaptureState capture;
  final Map<String, bool> readiness;
  final List<String> faultsArmed;

  Map<String, Object?> toJson() => {
        'contract_version': contractVersion,
        'profile': profile,
        'route': route,
        'principal': principal.toJson(),
        'capture': capture.toJson(),
        'readiness': readiness,
        'faults_armed': faultsArmed,
      };
}

/// Thrown by [SemanticControls.waitReady] when the deadline passes. Carries
/// the last observed state — structured, actionable, and secret-free — so a
/// caller can tell *what* was not ready, not just that something timed out.
class SemanticReadinessTimeout implements Exception {
  SemanticReadinessTimeout(this.condition, this.deadlineMs, this.lastState);

  final String condition;
  final int deadlineMs;
  final SemanticState lastState;

  @override
  String toString() =>
      'SemanticReadinessTimeout: condition "$condition" not met within ${deadlineMs}ms. Last state: ${lastState.toJson()}';
}

class SemanticControls {
  SemanticControls._();

  static final SemanticControls instance = SemanticControls._();

  bool _installed = false;

  /// Capabilities reported to callers: the operation names this surface
  /// supports. Stable strings; append-only.
  static const List<String> capabilities = [
    'state',
    'wait_ready',
    'navigate',
    'action',
    'fault.arm',
    'fault.clear',
    'capabilities',
  ];

  /// Installs the VM service extensions when (and only when) the current
  /// build is [semanticControlsEligible]. Called from the debug branch of
  /// `main()` next to `MarionetteBinding.ensureInitialized()`; inert elsewhere.
  void installIfEligible() {
    if (!semanticControlsEligible || _installed) return;
    _installed = true;
    _registerExtensions();
  }

  bool get installed => _installed;

  static const JsonEncoder _json = JsonEncoder();

  void _registerExtensions() {
    developer.registerExtension('omi.controls.capabilities', (method, params) async {
      return developer.ServiceExtensionResponse.result(_json.convert({
        'contract_version': semanticControlsVersion,
        'capabilities': capabilities,
        'faults': [for (final f in JourneyFault.values) f.name],
      }));
    });
    developer.registerExtension('omi.controls.state', (method, params) async {
      return developer.ServiceExtensionResponse.result(_json.convert(state().toJson()));
    });
    developer.registerExtension('omi.controls.wait_ready', (method, params) async {
      final condition = params['condition'];
      if (condition == null) {
        return developer.ServiceExtensionResponse.error(
          -32602,
          'missing "condition"',
        );
      }
      final deadlineMs = int.tryParse(params['deadline_ms'] ?? '') ?? 30000;
      try {
        final state = await waitReady(condition, deadline: Duration(milliseconds: deadlineMs));
        return developer.ServiceExtensionResponse.result(_json.convert({'ok': true, 'state': state.toJson()}));
      } on SemanticReadinessTimeout catch (e) {
        return developer.ServiceExtensionResponse.error(-32000, e.toString());
      }
    });
    developer.registerExtension('omi.controls.navigate', (method, params) async {
      final destination = params['destination'];
      if (destination == null) {
        return developer.ServiceExtensionResponse.error(
          -32602,
          'missing "destination"',
        );
      }
      final ok = navigate(destination);
      return ok
          ? developer.ServiceExtensionResponse.result(_json.convert({'ok': true}))
          : developer.ServiceExtensionResponse.error(-32001, 'unknown destination "$destination"');
    });
    developer.registerExtension('omi.controls.fault', (method, params) async {
      final fault = params['fault'];
      final clear = params['clear'] == 'true';
      if (fault == null) {
        return developer.ServiceExtensionResponse.error(
          -32602,
          'missing "fault"',
        );
      }
      try {
        final parsed = JourneyFault.values.firstWhere((f) => f.name == fault);
        if (clear) {
          clearFault(parsed);
        } else {
          armFault(parsed);
        }
      } on StateError {
        return developer.ServiceExtensionResponse.error(
          -32602,
          'unknown fault "$fault"',
        );
      }
      return developer.ServiceExtensionResponse.result(
        _json.convert({'ok': true, 'armed': armedFaults.map((f) => f.name).toList()}),
      );
    });
  }

  // ---------------------------------------------------------------- state

  /// Snapshot of the semantic product state. Reads only public production
  /// surfaces: the global navigator (route + provider scope),
  /// SharedPreferencesUtil identity fields, auth-provider session flags, and
  /// the capture provider's public recording identity. No tokens, no raw
  /// preference dumps, no arbitrary introspection.
  SemanticState state() {
    final context = globalNavigatorKey.currentContext;
    final route = _currentRoute(context);
    final principal = _principal(context);
    final capture = _capture(context);
    return SemanticState(
      contractVersion: semanticControlsVersion,
      profile: Env.profile.name,
      route: route,
      principal: principal,
      capture: capture,
      readiness: {
        for (final c in SemanticReadiness.values) c.name: isReady(c),
      },
      faultsArmed: [for (final f in armedFaults) f.name],
    );
  }

  String _currentRoute(BuildContext? context) {
    if (context == null) return '<no-navigator-context>';
    final modalRoute = ModalRoute.of(context);
    final routeName = modalRoute?.settings.name;
    if (routeName != null && routeName.isNotEmpty) return routeName;
    final top = context.widget.runtimeType.toString();
    return '<widget:$top>';
  }

  SemanticPrincipal _principal(BuildContext? context) {
    final prefs = SharedPreferencesUtil();
    AuthenticationProvider? authProvider;
    try {
      authProvider = context?.read<AuthenticationProvider>();
    } catch (_) {
      // Provider not in scope (e.g. a hermetic journey boots only the page
      // under test). SharedPreferences identity remains the truth here.
    }
    final uid = prefs.uid;
    final email = prefs.email;
    final signedIn = authProvider?.isSignedIn() ?? uid.isNotEmpty;
    return SemanticPrincipal(
      uid: uid,
      email: email,
      signedIn: signedIn,
      requiresReauthentication: authProvider?.requiresReauthentication ?? false,
    );
  }

  SemanticCaptureState _capture(BuildContext? context) {
    CaptureProvider? capture;
    try {
      capture = context?.read<CaptureProvider>();
    } catch (_) {
      // No live capture surface in scope; replay journeys report capture
      // identity through the capture-scenario/v1 adapter instead.
    }
    if (capture == null) {
      return const SemanticCaptureState(
        activeRecordingId: null,
        activeCaptureSessionId: null,
        recordingState: 'unavailable-live',
        backlogObservability: 'unavailable-live',
      );
    }
    return SemanticCaptureState(
      activeRecordingId: capture.activeRecordingId,
      activeCaptureSessionId: capture.activeCaptureSessionId,
      recordingState: capture.recordingState.name,
      // The live WAL backlog is not globally reachable without touching the
      // capture-owned services; the replay adapter owns upload accounting.
      backlogObservability: 'via-capture-scenario-adapter',
    );
  }

  // ------------------------------------------------------------ waitReady

  bool isReady(SemanticReadiness condition) {
    switch (condition) {
      case SemanticReadiness.signedIn:
        final context = globalNavigatorKey.currentContext;
        try {
          return context?.read<AuthenticationProvider>().isSignedIn() ?? false;
        } catch (_) {
          return SharedPreferencesUtil().uid.isNotEmpty;
        }
      case SemanticReadiness.routed:
        return globalNavigatorKey.currentState?.mounted ?? false;
      case SemanticReadiness.captureIdle:
        final context = globalNavigatorKey.currentContext;
        try {
          final capture = context!.read<CaptureProvider>();
          return capture.recordingState == RecordingState.stop;
        } catch (_) {
          return true; // no live capture surface in scope
        }
    }
  }

  /// Polls a named semantic condition until true or [deadline]. Bounded
  /// semantics — no fixed sleeps masquerading as readiness: the poll interval
  /// is an implementation detail, and expiry fails loudly with the last
  /// observed state.
  Future<SemanticState> waitReady(String condition, {Duration deadline = const Duration(seconds: 30)}) {
    final SemanticReadiness parsed;
    try {
      parsed = SemanticReadiness.values.firstWhere((c) => c.name == condition);
    } on StateError {
      throw ArgumentError('unknown readiness condition "$condition"; '
          'known: ${SemanticReadiness.values.map((c) => c.name).toList()}');
    }
    final sw = Stopwatch()..start();
    return () async {
      SemanticState last = state();
      while (!(last.readiness[parsed.name] ?? false)) {
        if (sw.elapsed >= deadline) {
          throw SemanticReadinessTimeout(parsed.name, deadline.inMilliseconds, last);
        }
        await Future<void>.delayed(const Duration(milliseconds: 50));
        last = state();
      }
      return last;
    }();
  }

  // ------------------------------------------------------------- navigate

  final Map<String, WidgetBuilder> _destinations = {};

  /// Registers a named destination built from the production pages. Journeys
  /// and the app bootstrap register what they own; the control surface itself
  /// holds no page imports (keeps it testable without the whole widget graph).
  void registerDestination(String name, WidgetBuilder builder) {
    assert(semanticControlsEligible, 'destinations are a local-dev control surface');
    _destinations[name] = builder;
  }

  /// Pushes a destination through the same [MaterialPageRoute] mechanism the
  /// production UI uses. Journeys still perform at least one real UI
  /// interaction per behavior; navigation exists for setup and diagnosis,
  /// not to replace the button under test.
  bool navigate(String destination) {
    final builder = _destinations[destination];
    final navigator = globalNavigatorKey.currentState;
    if (builder == null || navigator == null || !navigator.mounted) return false;
    navigator.push(MaterialPageRoute(builder: builder));
    return true;
  }

  // ---------------------------------------------------------------- faults

  /// Arms a named journey fault. Faults mutate external I/O at declared
  /// boundaries only (HTTP egress, fixture backend behavior, replay upload
  /// scripting) — never product decisions. See [JourneyFault] for the
  /// boundary each fault owns.
  void armFault(JourneyFault fault) {
    assert(semanticControlsEligible, 'faults are a local-dev control surface');
    JourneyFaultGate.instance.arm(fault);
  }

  void clearFault(JourneyFault fault) {
    assert(semanticControlsEligible, 'faults are a local-dev control surface');
    JourneyFaultGate.instance.clear(fault);
  }

  List<JourneyFault> get armedFaults => JourneyFaultGate.instance.armed;

  void clearAllFaults() => JourneyFaultGate.instance.clearAll();
}
