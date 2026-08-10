/// Fail-closed gate derived from the account cutover control projection.
///
/// LIFECYCLE: permanent
library;

import 'package:omi/services/account_cutover/account_cutover_control.dart';

enum AccountCutoverGateDecision {
  allowProductTraffic,
  forceUpgrade,
  migrationMaintenance,
}

class AccountCutoverGate {
  const AccountCutoverGate();

  AccountCutoverGateDecision decide(AccountCutoverControl control) {
    if (control.clientAction == AccountCutoverClientAction.forceUpgrade) {
      return AccountCutoverGateDecision.forceUpgrade;
    }
    if (control.clientAction == AccountCutoverClientAction.migrationMaintenance ||
        control.productTrafficAllowed == false) {
      return AccountCutoverGateDecision.migrationMaintenance;
    }
    return AccountCutoverGateDecision.allowProductTraffic;
  }

  /// Offline WAL / sync queues: drain only while product traffic is still
  /// allowed (pre-migration fence). Quarantine always blocks uploads.
  bool shouldUploadOfflineQueues(AccountCutoverControl control) {
    switch (control.offlineQueueInstruction) {
      case OfflineQueueInstruction.quarantine:
        return false;
      case OfflineQueueInstruction.drain:
        return decide(control) == AccountCutoverGateDecision.allowProductTraffic;
      case OfflineQueueInstruction.none:
        return decide(control) == AccountCutoverGateDecision.allowProductTraffic;
    }
  }

  bool shouldQuarantineOfflineQueues(AccountCutoverControl control) {
    return control.offlineQueueInstruction == OfflineQueueInstruction.quarantine;
  }
}
