import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/utils/logger.dart';

/// Extra listeners on a capture audio tap. The capture's single nullable slot
/// stays its existing owner's (onboarding); listeners get the same snapshot
/// after it, and a failing listener never reaches the capture path.
class AudioTapListeners {
  final List<void Function(List<int> bytes)> _listeners = [];

  void add(void Function(List<int> bytes) listener) => _listeners.add(listener);
  void remove(void Function(List<int> bytes) listener) => _listeners.remove(listener);

  void emit(List<int> bytes, void Function(List<int> bytes)? primary) {
    primary?.call(bytes);
    for (final listener in List.of(_listeners)) {
      try {
        listener(bytes);
      } catch (e) {
        Logger.debug('[CaptureProvider] audio tap listener failed: $e');
      }
    }
  }
}

/// Capture's socket-scoped local-preview state: whether the server admitted
/// this socket, and which pendant frames must not reach it yet.
class LocalPreviewAdmission {
  LocalPreviewAdmission({required this.now, required this.onChanged});

  final DateTime Function() now;
  final void Function() onChanged;

  /// Pendant frames on a socket that declared local preview stay WAL-only until
  /// the verdict, at most this long: any audio reaching an admitted socket opens
  /// the deferred cloud stream.
  static const verdictHold = Duration(seconds: 10);

  LivePreviewController? preview;
  bool admitted = false;
  DateTime? _verdictPendingSince;
  String language = 'multi';
  BleAudioCodec pendantCodec = BleAudioCodec.opus;

  /// Wires [live] to both taps. Returns the matching teardown.
  void Function() install(LivePreviewController live, AudioTapListeners device, AudioTapListeners phone) {
    preview = live;
    void onPendant(List<int> packet) => live.onPendantPacket(packet, pendantCodec);
    device.add(onPendant);
    phone.add(live.onPhonePcm);
    return () {
      device.remove(onPendant);
      phone.remove(live.onPhonePcm);
      if (identical(preview, live)) preview = null;
      live.dispose();
    };
  }

  void _set(bool value) {
    final changed = admitted != value;
    admitted = value;
    if (changed) onChanged();
    final live = preview;
    if (live == null) return;
    value ? live.admit(language: language) : live.revoke();
  }

  /// A new socket replaced the old one; its grant is pending if it asked.
  void socketPublished({required bool declared}) {
    if (admitted) _set(false);
    _verdictPendingSince = declared ? now() : null;
  }

  /// `ready` / `mobile_batch_admission`. Returns the effective grant: only a
  /// socket that asked for it, with a preview installed, is admitted.
  bool verdict({required bool granted, required bool socketDeclared}) {
    final effective = granted && socketDeclared && preview != null;
    _verdictPendingSince = null;
    if (effective != admitted) _set(effective);
    return effective;
  }

  /// Socket closed or reconnecting: lines are kept for a quick re-grant.
  void revoke() {
    _verdictPendingSince = null;
    _set(false);
  }

  /// Capture ended (stop, account change, dispose): the preview is dropped.
  void end() {
    admitted = false;
    _verdictPendingSince = null;
    preview?.endCapture();
  }

  /// Frames still go to the safety WAL; they only skip the socket: during the
  /// bounded verdict window and while the batch journal warms up.
  bool holdPendant({required bool socketDeclared, required bool journalWarmingUp}) {
    if (!socketDeclared) return false;
    final pendingSince = _verdictPendingSince;
    if (pendingSince != null) {
      if (now().difference(pendingSince) < verdictHold) return true;
      _verdictPendingSince = null;
      return false;
    }
    return admitted && journalWarmingUp;
  }
}
