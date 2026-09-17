import 'dart:async';

import 'package:omi/services/auth_service.dart';
import 'package:omi/services/connectivity_service.dart';

/// Controllable external boundaries for the capture pipeline.
///
/// CaptureController and the phone WAL resolve real I/O through these narrow
/// constructor-injected seams; every default below reproduces the previous
/// global-singleton behavior exactly. Deterministic capture/recovery scenarios
/// substitute scripted implementations so the production decision path runs
/// against controlled time, connectivity, scheduling, and auth — never a wall
/// clock or a live socket.
///
/// This is deliberately NOT a service locator: each seam covers one external
/// effect and is injected where the effect is consumed.

/// Timer creation boundary.
///
/// Scenarios substitute a manual scheduler so periodic work (socket keep-alive,
/// WAL chunk/flush, cooldowns) advances only when the scenario advances virtual
/// time, and so cleanup can assert no timer is left pending.
abstract class CaptureScheduling {
  Timer once(Duration delay, void Function() callback);

  Timer periodic(Duration interval, void Function(Timer timer) callback);
}

/// Production [CaptureScheduling]: the dart:async timer factories.
class WallClockCaptureScheduling implements CaptureScheduling {
  const WallClockCaptureScheduling();

  @override
  Timer once(Duration delay, void Function() callback) => Timer(delay, callback);

  @override
  Timer periodic(Duration interval, void Function(Timer timer) callback) => Timer.periodic(interval, callback);
}

/// Auth identity boundary for the capture pipeline.
///
/// Covers the two production reads of [AuthService] on the recovery path:
/// whether a reconnect may run, and the bounded refresh after the server
/// rejects a token (websocket close code 4001).
class CaptureAuthBoundary {
  const CaptureAuthBoundary({required this.isSignedIn, required this.refreshIdToken});

  final bool Function() isSignedIn;
  final Future<Object?> Function() refreshIdToken;

  /// The production boundary over the shared [AuthService] singleton.
  static const CaptureAuthBoundary production = CaptureAuthBoundary(
    isSignedIn: _productionIsSignedIn,
    refreshIdToken: _productionRefreshIdToken,
  );

  static bool _productionIsSignedIn() => AuthService.instance.isSignedIn();

  static Future<Object?> _productionRefreshIdToken() => AuthService.instance.refreshIdToken();
}

/// Connectivity boundary.
///
/// Production reads the shared [ConnectivityService]; scenarios substitute a
/// controlled initial state, change stream, and probe so network loss/reconnect
/// schedules are deterministic.
class CaptureConnectivityBoundary {
  CaptureConnectivityBoundary({
    required bool initiallyConnected,
    required Stream<bool> changes,
    required bool Function() isConnected,
  })  : _initiallyConnected = initiallyConnected,
        _changes = changes,
        _isConnected = isConnected;

  final bool _initiallyConnected;
  final Stream<bool> _changes;
  final bool Function() _isConnected;

  bool get isConnected => _isConnected();

  /// The production boundary over the shared [ConnectivityService].
  CaptureConnectivityBoundary.production()
      : _initiallyConnected = ConnectivityService().isConnected,
        _changes = ConnectivityService().onConnectionChange,
        _isConnected = _productionProbe;

  static bool _productionProbe() => ConnectivityService().isConnected;

  Stream<bool> get changes => _changes;
  bool get initiallyConnected => _initiallyConnected;
}
