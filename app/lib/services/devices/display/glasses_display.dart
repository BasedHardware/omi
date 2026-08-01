import 'hud_content.dart';

/// The display surface a connector exposes when its device can render.
///
/// Capability-keyed, never device-type-keyed: a connector reports this because
/// its SDK says the connected hardware has a display, not because of which
/// vendor it is. Meta's DAT sources it from `Device.supportsDisplay()`.
abstract class GlassesDisplay {
  Future<void> attach();

  Future<void> detach();

  Future<void> send(HudScreen screen);

  Future<void> clear();

  Stream<String> get actionTaps;

  Stream<GlassesDisplayState> get stateStream;

  GlassesDisplayState get state;
}

enum GlassesDisplayState { unavailable, detached, attaching, ready, error }

/// Gate for the HUD feature as a whole.
///
/// Two independent conditions, deliberately separate: the device must actually
/// have a display, and the user must have opted in. Neither implies the other,
/// and a device without a display can never be turned on by the flag.
class GlassesDisplayGate {
  final bool deviceSupportsDisplay;
  final bool userEnabled;

  const GlassesDisplayGate({
    required this.deviceSupportsDisplay,
    required this.userEnabled,
  });

  bool get isOpen => deviceSupportsDisplay && userEnabled;

  String get closedReason {
    if (!deviceSupportsDisplay) return 'device_has_no_display';
    if (!userEnabled) return 'user_disabled';
    return '';
  }
}
