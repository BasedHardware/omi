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

/// Why this client does not ask for local preview on a socket: per-session
/// stable conditions under which its routing could not journal pendant audio,
/// so an admitted session would stream to the cloud anyway. Closed set.
enum LocalPreviewClientRefusal {
  killSwitch('kill_switch'),
  deviceUnsupported('device_unsupported'),
  codecUnsupported('codec_unsupported'),
  autoSyncOff('auto_sync_off'),
  transcribeLater('transcribe_later'),
  customStt('custom_stt'),
  keptOnPhone('kept_on_phone'),
  onboarding('onboarding'),
  noJournal('no_journal');

  const LocalPreviewClientRefusal(this.wireName);
  final String wireName;
}

/// Mirrors MobileStandardBatch's ordinary refusals (route() and the
/// realtime-consumer clauses): an Omi pendant on an Opus codec, auto-sync on,
/// no Transcribe Later, no custom STT, not kept on the phone, no onboarding,
/// and a batch journal installed. Transient refusals (disk, journal failure)
/// are not here; they keep the WAL+socket carve-out.
LocalPreviewClientRefusal? localPreviewClientRefusal({
  required bool omiPendant,
  required bool opusCodec,
  required bool autoSyncOfflineRecordings,
  required bool batchModeEnabled,
  required bool customStt,
  required bool keptOnPhone,
  required bool onboarding,
  required bool journalInstalled,
}) {
  if (!omiPendant) return LocalPreviewClientRefusal.deviceUnsupported;
  if (!opusCodec) return LocalPreviewClientRefusal.codecUnsupported;
  if (!journalInstalled) return LocalPreviewClientRefusal.noJournal;
  if (batchModeEnabled) return LocalPreviewClientRefusal.transcribeLater;
  if (!autoSyncOfflineRecordings) return LocalPreviewClientRefusal.autoSyncOff;
  if (customStt) return LocalPreviewClientRefusal.customStt;
  if (keptOnPhone) return LocalPreviewClientRefusal.keptOnPhone;
  if (onboarding) return LocalPreviewClientRefusal.onboarding;
  return null;
}

/// How a socket that declared local preview was settled. Closed set.
enum LocalPreviewVerdictOutcome {
  granted('granted'),
  refused('refused'),
  timeout('timeout'),
  overflow('overflow'),
  socketClosed('socket_closed');

  const LocalPreviewVerdictOutcome(this.wireName);
  final String wireName;
}

/// One measurement per declaring socket (observational only).
class LocalPreviewVerdictReport {
  const LocalPreviewVerdictReport({
    required this.outcome,
    required this.verdictLatencyMs,
    required this.holdDurationMs,
    required this.heldFrames,
    required this.holdTimeoutReplayed,
  });

  final LocalPreviewVerdictOutcome outcome;

  /// Socket published (request sent) to its settlement.
  final int verdictLatencyMs;

  /// First frame held on this socket to its settlement; 0 when none was held.
  final int holdDurationMs;

  /// Frames held on this socket (carried-over frames are counted by their own socket).
  final int heldFrames;

  /// The timeout or overflow forced the held frames to be replayed to the socket.
  final bool holdTimeoutReplayed;
}

/// Capture's socket-scoped local-preview state: whether the server admitted
/// this socket, and which pendant frames must not reach it yet.
class LocalPreviewAdmission {
  LocalPreviewAdmission({required this.now, required this.onChanged, this.onVerdictReport});

  /// Observational hook; defaults to the preview controller's telemetry.
  final void Function(LocalPreviewVerdictReport report)? onVerdictReport;

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

  /// This socket is settled as refused (hold timed out or overflowed and its
  /// frames already streamed, or a client gate flipped mid-session): a later
  /// grant on the same socket never admits it.
  bool _refusedForSocket = false;
  bool get refusedForSocketForTesting => _refusedForSocket;
  DateTime? _verdictPendingSince;

  // Per-socket verdict measurement (telemetry only; never changes routing).
  DateTime? _socketDeclaredAt;
  DateTime? _firstHeldAt;
  int _heldThisSocket = 0;

  void _report(LocalPreviewVerdictOutcome outcome) {
    final declaredAt = _socketDeclaredAt;
    if (declaredAt == null) return; // Not a declaring socket, or already reported.
    _socketDeclaredAt = null;
    final at = now();
    int ms(DateTime from) => at.difference(from).inMilliseconds.clamp(0, 1 << 31);
    final report = LocalPreviewVerdictReport(
      outcome: outcome,
      verdictLatencyMs: ms(declaredAt),
      holdDurationMs: _firstHeldAt == null ? 0 : ms(_firstHeldAt!),
      heldFrames: _heldThisSocket,
      holdTimeoutReplayed:
          (outcome == LocalPreviewVerdictOutcome.timeout || outcome == LocalPreviewVerdictOutcome.overflow) &&
              _held.isNotEmpty,
    );
    _firstHeldAt = null;
    _heldThisSocket = 0;
    final hook = onVerdictReport ?? preview?.reportVerdict;
    try {
      hook?.call(report);
    } catch (_) {
      // Telemetry never affects capture.
    }
  }

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
  /// Frames still held from an unresolved earlier socket carry over and are
  /// resolved against this socket's verdict; a socket that did not ask is a
  /// refusal, so they are [send] to it now, before any newer frame.
  void socketPublished({required bool declared, required void Function(HeldPendantFrame frame) send}) {
    if (admitted) _set(false);
    _report(LocalPreviewVerdictOutcome.socketClosed); // An unsettled predecessor.
    _refusedForSocket = !declared;
    if (declared) {
      _verdictPendingSince = now();
      _socketDeclaredAt = _verdictPendingSince;
    } else {
      _verdictPendingSince = null;
      _flush(send);
    }
  }

  /// `ready` / `mobile_batch_admission`. Returns the effective grant: only a
  /// socket that asked for it, with a preview installed, is admitted. A
  /// refusal [send]s every held frame, in order, before this returns.
  bool verdict({
    required bool granted,
    required bool socketDeclared,
    required void Function(HeldPendantFrame frame) send,
  }) {
    final effective = granted && socketDeclared && preview != null && !_refusedForSocket;
    _report(effective ? LocalPreviewVerdictOutcome.granted : LocalPreviewVerdictOutcome.refused);
    _verdictPendingSince = null;
    if (effective) {
      _held.clear();
    } else {
      _flush(send);
    }
    if (effective != admitted) _set(effective);
    return effective;
  }

  /// A client gate flipped to refusing mid-session (auto-sync turned off,
  /// Transcribe Later, kept on the phone…): this socket now streams like any
  /// other, so the preview hides and no later grant on it re-admits. Returns
  /// whether an admission was dropped.
  bool refuseForSocket({required void Function(HeldPendantFrame frame) send}) {
    _refusedForSocket = true;
    _verdictPendingSince = null;
    _flush(send);
    if (!admitted) return false;
    _set(false);
    return true;
  }

  /// Socket closed or reconnecting: lines are kept for a quick re-grant. Held
  /// frames stay queued for the replacement socket's verdict (bounded); only
  /// capture end or an account change discards them.
  void revoke() {
    _report(LocalPreviewVerdictOutcome.socketClosed);
    _verdictPendingSince = null;
    _set(false);
  }

  /// Capture ended (stop, account change, dispose): the preview and any held
  /// frames are dropped (the safety WAL has every one).
  void end() {
    _report(LocalPreviewVerdictOutcome.socketClosed);
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
        _firstHeldAt ??= now();
        _heldThisSocket++;
        _held.add(frame);
        return;
      }
      // Overflow: stop holding, stream everything in order from here on. The
      // socket is refused for good: a late grant must not claim it.
      _report(LocalPreviewVerdictOutcome.overflow);
      _verdictPendingSince = null;
      _refusedForSocket = true;
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
    // Timed out: a refusal for this socket, latched like an overflow.
    _report(LocalPreviewVerdictOutcome.timeout);
    _verdictPendingSince = null;
    _refusedForSocket = true;
    return false;
  }

  void _flush(void Function(HeldPendantFrame frame) send) {
    if (_held.isEmpty) return;
    final held = List.of(_held);
    _held.clear();
    held.forEach(send);
  }
}
