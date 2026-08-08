/// Cached cutover control for offline-queue decisions and bootstrap gates.
///
/// LIFECYCLE: permanent
library;

import 'package:flutter/foundation.dart';

import 'package:omi/services/account_cutover/account_cutover_control.dart';
import 'package:omi/services/account_cutover/account_cutover_gate.dart';

class AccountCutoverRuntime extends ChangeNotifier {
  AccountCutoverRuntime._();
  static final AccountCutoverRuntime instance = AccountCutoverRuntime._();

  final AccountCutoverGate _gate = const AccountCutoverGate();
  AccountCutoverControl _control = AccountCutoverControl.legacyDefault();

  AccountCutoverControl get control => _control;
  AccountCutoverGateDecision get decision => _gate.decide(_control);

  void apply(AccountCutoverControl control) {
    _control = control;
    notifyListeners();
  }

  bool get allowsOfflineQueueUpload => _gate.shouldUploadOfflineQueues(_control);
  bool get quarantinesOfflineQueues => _gate.shouldQuarantineOfflineQueues(_control);
}
