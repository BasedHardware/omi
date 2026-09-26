/// Cached cutover control for offline-queue decisions and bootstrap gates.
///
/// LIFECYCLE: permanent
library;

import 'package:flutter/foundation.dart';

import 'package:omi/services/account_cutover/account_cutover_control.dart';
import 'package:omi/services/account_cutover/account_cutover_control_client.dart';
import 'package:omi/services/account_cutover/account_cutover_gate.dart';

/// Why product traffic is currently fenced.
///
/// This is deliberately separate from [AccountCutoverGateDecision]. The gate
/// decision owns access policy; this reason owns what the client may truthfully
/// tell the user. A failed or pending control fetch is not evidence that an
/// account is migrating, even when both conditions must fail closed.
enum AccountCutoverBlockingReason {
  none,
  forceUpgrade,
  confirmedMigration,
  checkingStatus,
  connectionUnavailable,
  controlUnavailable,
}

class AccountCutoverRuntime extends ChangeNotifier {
  AccountCutoverRuntime._();
  static final AccountCutoverRuntime instance = AccountCutoverRuntime._();

  /// Test seam for the blocking screen's own retry loop, which calls the
  /// parameterless [refresh]. Production code never assigns this.
  @visibleForTesting
  static AccountCutoverControlClient? controlClientOverrideForTesting;

  final AccountCutoverGate _gate = const AccountCutoverGate();
  AccountCutoverControl _control = AccountCutoverControl.legacyDefault();
  bool _hasAuthoritative = false;
  AccountCutoverControl? _lastAuthoritativeControl;
  String? _ownerUid;
  int _refreshEpoch = 0;
  bool _resolvedForOwner = true;
  AccountCutoverBlockingReason _blockingReason = AccountCutoverBlockingReason.none;

  AccountCutoverControl get control => _control;
  bool get hasAuthoritativeControl => _hasAuthoritative;
  String? get ownerUid => _ownerUid;
  bool get isResolvedForOwner => _resolvedForOwner;
  AccountCutoverBlockingReason get blockingReason => _blockingReason;

  AccountCutoverBlockingReason _reasonForAuthoritativeControl(AccountCutoverControl control) {
    switch (_gate.decide(control)) {
      case AccountCutoverGateDecision.allowProductTraffic:
        return AccountCutoverBlockingReason.none;
      case AccountCutoverGateDecision.forceUpgrade:
        return AccountCutoverBlockingReason.forceUpgrade;
      case AccountCutoverGateDecision.migrationMaintenance:
        return AccountCutoverBlockingReason.confirmedMigration;
    }
  }

  /// The only projection [skipUnresolvedFence] may return to: the last
  /// AUTHORITATIVE projection for this owner, and only while that projection
  /// allowed product traffic.
  ///
  /// Null when the server has never allowed this owner — nothing authoritative
  /// has arrived yet, or the last authoritative word was itself a fence. Then
  /// the fence holds and only a fresh server answer can lift it, so a fence is
  /// never traded for a legacy projection the server never sent.
  AccountCutoverControl? get _lastAuthoritativeAllow {
    final last = _lastAuthoritativeControl;
    if (last == null) return null;
    if (_gate.decide(last) != AccountCutoverGateDecision.allowProductTraffic) return null;
    return last;
  }

  /// True while the fence currently on screen was synthesized by this client
  /// after an unavailable or malformed control response, and the server had
  /// previously allowed this owner. Only such a fence is skippable.
  ///
  /// This is the distinction the `hasAuthoritativeControl` gate got wrong:
  /// after one successful "legacy/allow" fetch, a single blown refresh
  /// produced a maintenance fence with no exit at all — the server never
  /// actually said "migrating", but the skip affordance was hidden because
  /// SOME authoritative projection had been seen.
  bool get canSkipUnresolvedFence => _lastAuthoritativeAllow != null;

  AccountCutoverGateDecision get decision {
    // Owner transitions fail closed until the matching refresh settles so a
    // prior account's allow decision cannot leak into the new session.
    if (!_resolvedForOwner) {
      return AccountCutoverGateDecision.migrationMaintenance;
    }
    return _gate.decide(_control);
  }

  /// Test / bootstrap helper that applies a known-good projection directly.
  void apply(AccountCutoverControl control, {bool authoritative = true}) {
    _control = control;
    _hasAuthoritative = authoritative;
    if (authoritative) {
      _lastAuthoritativeControl = control;
      _blockingReason = _reasonForAuthoritativeControl(control);
    } else {
      _blockingReason = _gate.decide(control) == AccountCutoverGateDecision.allowProductTraffic
          ? AccountCutoverBlockingReason.none
          : AccountCutoverBlockingReason.controlUnavailable;
    }
    _resolvedForOwner = true;
    notifyListeners();
  }

  void resetForTesting() {
    _control = AccountCutoverControl.legacyDefault();
    _hasAuthoritative = false;
    _lastAuthoritativeControl = null;
    _ownerUid = null;
    _refreshEpoch = 0;
    _resolvedForOwner = true;
    _blockingReason = AccountCutoverBlockingReason.none;
    controlClientOverrideForTesting = null;
  }

  /// Bind runtime state to the authenticated owner and refresh control.
  ///
  /// A null/empty [uid] clears to legacy defaults. Owner changes immediately
  /// clear prior-account state and block product traffic until the in-flight
  /// refresh for that owner completes. Stale in-flight results are discarded.
  Future<void> bindAuthenticatedOwner(String? uid, {AccountCutoverControlClient? client}) async {
    final epoch = ++_refreshEpoch;
    final normalized = (uid == null || uid.isEmpty) ? null : uid;

    if (normalized == null) {
      _ownerUid = null;
      _control = AccountCutoverControl.legacyDefault();
      _hasAuthoritative = false;
      _lastAuthoritativeControl = null;
      _resolvedForOwner = true;
      _blockingReason = AccountCutoverBlockingReason.none;
      notifyListeners();
      return;
    }

    if (normalized != _ownerUid) {
      // Only a genuine switch between two real accounts on this device needs
      // the synchronous fence: it stops account A's stale allow decision
      // from leaking into account B's session while B's fetch is in flight.
      // The very first bind of a fresh runtime (no prior owner in memory,
      // e.g. cold app start) has no prior decision to leak, so leave
      // `_control` at its legacy-compatible default — a transport failure on
      // this bind can then fall back to it in `applyFetchResult` instead of
      // being permanently stuck behind a fence it never needed.
      final isGenuineOwnerSwitch = _ownerUid != null;
      _ownerUid = normalized;
      _hasAuthoritative = false;
      // The prior owner's projection must not survive an owner change in any
      // form — including as the "last known good" a skip could restore.
      _lastAuthoritativeControl = null;
      _resolvedForOwner = false;
      _blockingReason = AccountCutoverBlockingReason.checkingStatus;
      if (isGenuineOwnerSwitch) {
        _control = AccountCutoverControl.unavailable();
      }
      notifyListeners();
    }

    final fetchClient = client ?? controlClientOverrideForTesting ?? AccountCutoverControlClient();
    final result = await fetchClient.fetchControl();
    if (epoch != _refreshEpoch || _ownerUid != normalized) {
      return;
    }

    applyFetchResult(result);
    _resolvedForOwner = true;
    notifyListeners();
  }

  /// Refresh for the current owner without clearing state first.
  Future<void> refresh({AccountCutoverControlClient? client}) async {
    final owner = _ownerUid;
    if (owner == null) return;
    await bindAuthenticatedOwner(owner, client: client);
  }

  @visibleForTesting
  void applyFetchResult(AccountCutoverFetchResult result) {
    final lastAuthAllow = _lastAuthoritativeAllow;
    switch (result.kind) {
      case AccountCutoverFetchKind.success:
        _control = result.control!;
        _hasAuthoritative = true;
        _lastAuthoritativeControl = result.control;
        _blockingReason = _reasonForAuthoritativeControl(result.control!);
        break;
      case AccountCutoverFetchKind.unavailable:
        // The server explicitly failed closed — respect it and fence. When the
        // last authoritative word was "allow", this fence is the client's own:
        // the blocking screen offers skip and keeps retrying (see
        // canSkipUnresolvedFence).
        _control = AccountCutoverControl.unavailable(retaining: _hasAuthoritative ? _control : null);
        final lastAuthoritative = _lastAuthoritativeControl;
        _blockingReason = lastAuthoritative != null &&
                _gate.decide(lastAuthoritative) != AccountCutoverGateDecision.allowProductTraffic
            ? _reasonForAuthoritativeControl(lastAuthoritative)
            : AccountCutoverBlockingReason.controlUnavailable;
        break;
      case AccountCutoverFetchKind.transportFailure:
        if (lastAuthAllow != null) {
          // The control plane is unreachable, but its last authoritative word
          // for this owner was "allow". A transport blip is not evidence of a
          // migration — stay on the last-known-good projection instead of
          // synthesizing a maintenance fence with no exit. Without this, a
          // single timed-out refresh on a flaky connection could block the
          // whole app while the server kept answering legacy/none.
          _control = lastAuthAllow;
          _blockingReason = AccountCutoverBlockingReason.none;
        } else if (_hasAuthoritative) {
          // Last authoritative state was itself a fence (migrating/new/...):
          // keep failing closed across the outage.
          _control = AccountCutoverControl.unavailable(retaining: _control);
          _blockingReason = _reasonForAuthoritativeControl(_lastAuthoritativeControl!);
        } else if (_gate.decide(_control) == AccountCutoverGateDecision.allowProductTraffic) {
          // No authoritative projection yet (bridge rollout): stay legacy-compatible.
          _control = AccountCutoverControl.legacyDefault();
          _blockingReason = AccountCutoverBlockingReason.none;
        } else {
          _blockingReason = AccountCutoverBlockingReason.connectionUnavailable;
        }
        // If already blocked (e.g. owner-change unavailable), keep that fence.
        break;
    }
  }

  /// Escape hatch for a fence this client synthesized after the server had
  /// allowed the owner: returns to that last authoritative projection.
  ///
  /// A no-op — the fence holds — whenever there is nothing the server itself
  /// allowed to go back to: a confirmed migrating/new/rolled_back_stranded
  /// state, an unavailable or malformed document before any allow, or an owner
  /// whose first fetch has not landed yet. It can never synthesize a legacy
  /// projection of its own.
  bool skipUnresolvedFence() {
    final lastGood = _lastAuthoritativeAllow;
    if (lastGood == null) return false;
    _control = lastGood;
    _resolvedForOwner = true;
    _blockingReason = AccountCutoverBlockingReason.none;
    notifyListeners();
    return true;
  }

  bool get allowsOfflineQueueUpload {
    if (!_resolvedForOwner) return false;
    return _gate.shouldUploadOfflineQueues(_control);
  }

  bool get quarantinesOfflineQueues {
    if (!_resolvedForOwner) return true;
    return _gate.shouldQuarantineOfflineQueues(_control);
  }
}
