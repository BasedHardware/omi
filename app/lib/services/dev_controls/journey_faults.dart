/// Named journey faults for the seeded acceptance journeys (C2 / SCA-488).
///
/// A fault is a deliberate, named mutation of **external I/O** at a declared
/// boundary, used to prove the journeys' oracles can reject wrong behavior:
/// arm the fault, run the journey, require a nonzero failure that names the
/// missing invariant. Faults never patch product decisions or synthesize
/// terminal product state — each one corrupts exactly the boundary it names,
/// so production behavior is untouched the moment it is cleared (or the gate
/// is not installed at all).
///
/// Boundary ownership:
/// - [suppressSend], [wrongOwnerSession] — the client HTTP egress chokepoint
///   (`HttpPoolManager.send`/`sendStreaming`): the request is dropped before
///   it leaves the app, or its bearer identity is swapped. Observable as a
///   connection failure / server-side ownership rejection.
/// - [suppressAssistantReply], [dropMemorySave] — the local fixture backend
///   (journey-owned): the deterministic endpoint closes the stream with no
///   reply chunks, or fails the persistence write.
/// - [failCaptureRecovery] — the deterministic capture-replay upload
///   scripting (capture-scenario/v1 lane): recovery uploads never succeed
///   after reconnect.
library;

import 'package:flutter/foundation.dart';

/// The named faults. `name` is the stable wire identifier used by the
/// `omi.controls.fault` VM-service extension and journey receipts.
enum JourneyFault {
  /// The chat send request never leaves the app (dropped at the HTTP
  /// chokepoint). Journey must fail: no server-visible user message, no
  /// assistant reply.
  suppressSend('suppress-send'),

  /// The assistant response stream is closed before any reply chunk reaches
  /// the parser. Journey must fail: no assistant-role message distinct from
  /// the user prompt.
  suppressAssistantReply('suppress-assistant-reply'),

  /// The memory persistence write fails. Journey must fail: the memory does
  /// not survive reload.
  dropMemorySave('drop-memory-save'),

  /// The request carries the wrong synthetic principal's bearer identity.
  /// Journey must fail: server-side ownership validation rejects the access.
  wrongOwnerSession('wrong-owner-session'),

  /// Post-reconnect recovery uploads of persisted audio never succeed.
  /// Journey must fail: persisted audio must remain recoverable.
  failCaptureRecovery('fail-capture-recovery');

  const JourneyFault(this.name);

  final String name;

  /// The invariant whose absence the armed fault must expose. Journey
  /// failures are expected to name this string.
  String get invariant => switch (this) {
        suppressSend => 'a sent user message reaches the server and is echoed into the conversation',
        suppressAssistantReply => 'a distinct assistant-role reply arrives through the real API path',
        dropMemorySave => 'a created memory persists across reload',
        wrongOwnerSession => 'records are only accessible under their owning session principal',
        failCaptureRecovery => 'persisted audio remains recoverable after reconnect',
      };
}

/// Client-side fault decisions for the HTTP egress chokepoint.
///
/// [HttpPoolManager] consults [beforeSend] on every pooled request. The gate
/// is a pure pass-through unless a fault is armed AND the semantic-controls
/// build gate is satisfied — in production-family builds `arm()` asserts, the
/// armed set stays empty, and requests are never inspected or mutated. The
/// class is dependency-free so the production chokepoint pays for it with one
/// map lookup, not an allocation.
class JourneyFaultGate {
  JourneyFaultGate._();

  static final JourneyFaultGate instance = JourneyFaultGate._();

  final Set<JourneyFault> _armed = {};

  List<JourneyFault> get armed => List.unmodifiable(_armed);

  /// True when client-egress faults may act at all. Kept separate from
  /// [arm]'s assert so release-mode callers cannot arm by mistake: the
  /// predicate is re-checked at every [beforeSend].
  bool get clientFaultsOperative =>
      kDebugMode && _armed.any((f) => f == JourneyFault.suppressSend || f == JourneyFault.wrongOwnerSession);

  void arm(JourneyFault fault) {
    assert(_gateAllowsFaults(), 'faults are a local-dev control surface');
    _armed.add(fault);
  }

  void clear(JourneyFault fault) => _armed.remove(fault);

  void clearAll() => _armed.clear();

  bool _gateAllowsFaults() {
    // Local import cycle avoidance: the eligibility predicate lives in
    // semantic_controls.dart and also imports this file. Checked lazily via
    // the environment instead.
    return _localDevDebug;
  }

  static bool get _localDevDebug {
    assert(() {
      // Debug-mode only; the profile check mirrors semanticControlsEligible
      // without importing Env here (keeps this file free of app
      // initialization order assumptions).
      return true;
    }());
    return kDebugMode;
  }

  /// Consulted by the HTTP chokepoint for every outgoing request. May mutate
  /// the bearer identity ([JourneyFault.wrongOwnerSession]); never touches
  /// anything else on the request.
  ///
  /// Returns whether the request should be dropped
  /// ([JourneyFault.suppressSend]). Throws nothing: a drop is reported as a
  /// [SocketException]-style connection failure by the caller so the app's
  /// existing transient-error classification stays the production behavior.
  ({bool drop, String? swappedBearer}) beforeSend(String method, Uri url, String? bearer) {
    if (_armed.isEmpty || !kDebugMode) return (drop: false, swappedBearer: null);

    if (_armed.contains(JourneyFault.suppressSend) && _isChatSend(method, url)) {
      return (drop: true, swappedBearer: null);
    }
    if (_armed.contains(JourneyFault.wrongOwnerSession)) {
      // Swap every authenticated request's bearer, not just chat: the fault
      // is about session ownership across the board.
      return (drop: false, swappedBearer: 'synthetic-wrong-owner-session-token');
    }
    return (drop: false, swappedBearer: null);
  }

  /// The chat send endpoint is the streaming `v2/messages` POST. Narrow by
  /// path so the fault cannot eat unrelated traffic (auth, memories).
  bool _isChatSend(String method, Uri url) {
    if (method != 'POST') return false;
    final segments = url.pathSegments;
    return segments.length >= 2 && segments[segments.length - 1] == 'messages' && segments[segments.length - 2] == 'v2';
  }
}
