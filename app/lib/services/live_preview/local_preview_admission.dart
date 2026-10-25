import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/audio_sources/audio_source.dart';
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

/// One pendant frame bound for the socket: its payload and, when the safety WAL
/// positioned it, the evidence frame that carries the same bytes.
class HeldPendantFrame {
  const HeldPendantFrame(this.payload, [this.positioned]);

  final List<int> payload;
  final WalFrame? positioned;
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

  /// Ten seconds of 20 ms Opus frames. Beyond it holding stops: the held
  /// frames are flushed and streaming resumes.
  static const maxHeldFrames = 500;

  /// In-memory copy of the frames held during the verdict window, oldest
  /// first. A refusal sends them before any newer frame, so a session that is
  /// not admitted keeps its whole live transcript; a grant drops them (the
  /// safety WAL already holds every one).
  final List<HeldPendantFrame> _held = [];
  int get heldFramesForTesting => _held.length;

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
    // Frames held for a replaced socket cannot reach it; the WAL keeps them,
    // exactly as for any frame captured while a socket is down.
    _held.clear();
    _verdictPendingSince = declared ? now() : null;
  }

  /// `ready` / `mobile_batch_admission`. Returns the effective grant: only a
  /// socket that asked for it, with a preview installed, is admitted. A
  /// refusal [send]s every held frame, in order, before this returns.
  bool verdict({
    required bool granted,
    required bool socketDeclared,
    required void Function(HeldPendantFrame frame) send,
  }) {
    final effective = granted && socketDeclared && preview != null;
    _verdictPendingSince = null;
    if (effective) {
      _held.clear();
    } else {
      _flush(send);
    }
    if (effective != admitted) _set(effective);
    return effective;
  }

  /// Socket closed or reconnecting: lines are kept for a quick re-grant. Held
  /// frames have no socket to go to; the safety WAL already has them.
  void revoke() {
    _verdictPendingSince = null;
    _held.clear();
    _set(false);
  }

  /// Capture ended (stop, account change, dispose): the preview is dropped.
  void end() {
    admitted = false;
    _verdictPendingSince = null;
    _held.clear();
    preview?.endCapture();
  }

  /// Routes one pendant frame for a connected socket. Every frame has already
  /// gone to the safety WAL; this decides only whether it reaches the socket
  /// now, later (held in memory until a refusal) or never (admitted).
  void routePendant(
    HeldPendantFrame frame, {
    required bool socketDeclared,
    required bool journalWarmingUp,
    required void Function(HeldPendantFrame frame) send,
  }) {
    if (socketDeclared && _holdingForVerdict()) {
      if (_held.length < maxHeldFrames) {
        _held.add(frame);
        return;
      }
      // Overflow: stop holding, stream everything in order from here on.
      _verdictPendingSince = null;
    }
    if (socketDeclared && admitted && journalWarmingUp) {
      // Admitted only, so never a cloud-transcript loss: the frame is in the
      // WAL and the batch path; it must just not open the cloud stream.
      assert(_held.isEmpty);
      return;
    }
    _flush(send);
    send(frame);
  }

  bool _holdingForVerdict() {
    final pendingSince = _verdictPendingSince;
    if (pendingSince == null) return false;
    if (now().difference(pendingSince) < verdictHold) return true;
    _verdictPendingSince = null; // Timed out: treated as a refusal.
    return false;
  }

  void _flush(void Function(HeldPendantFrame frame) send) {
    if (_held.isEmpty) return;
    final held = List.of(_held);
    _held.clear();
    held.forEach(send);
  }
}
