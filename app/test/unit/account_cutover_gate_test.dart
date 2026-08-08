import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/account_cutover/account_cutover_control.dart';
import 'package:omi/services/account_cutover/account_cutover_gate.dart';

void main() {
  const gate = AccountCutoverGate();

  test('legacy default allows product traffic and uploads', () {
    final control = AccountCutoverControl.legacyDefault();
    expect(gate.decide(control), AccountCutoverGateDecision.allowProductTraffic);
    expect(gate.shouldUploadOfflineQueues(control), isTrue);
    expect(gate.shouldQuarantineOfflineQueues(control), isFalse);
  });

  test('force upgrade fails closed before product traffic', () {
    final control = AccountCutoverControl.fromJson({
      'state': 'legacy',
      'account_generation': 0,
      'client_action': 'force_upgrade',
      'offline_queue_instruction': 'none',
      'product_traffic_allowed': false,
      'legacy_writes_allowed': false,
      'auth_bootstrap_reachable': true,
    });
    expect(gate.decide(control), AccountCutoverGateDecision.forceUpgrade);
    expect(gate.shouldUploadOfflineQueues(control), isFalse);
  });

  test('migration maintenance quarantines offline queues', () {
    final control = AccountCutoverControl.fromJson({
      'state': 'migrating',
      'account_generation': 2,
      'client_action': 'migration_maintenance',
      'offline_queue_instruction': 'quarantine',
      'product_traffic_allowed': false,
      'legacy_writes_allowed': false,
      'auth_bootstrap_reachable': true,
    });
    expect(gate.decide(control), AccountCutoverGateDecision.migrationMaintenance);
    expect(gate.shouldUploadOfflineQueues(control), isFalse);
    expect(gate.shouldQuarantineOfflineQueues(control), isTrue);
  });

  test('drain only while product traffic remains allowed', () {
    final drainLegacy = AccountCutoverControl.fromJson({
      'state': 'legacy',
      'account_generation': 0,
      'client_action': 'none',
      'offline_queue_instruction': 'drain',
      'product_traffic_allowed': true,
      'legacy_writes_allowed': true,
      'auth_bootstrap_reachable': true,
    });
    expect(gate.shouldUploadOfflineQueues(drainLegacy), isTrue);

    final drainWhileBlocked = AccountCutoverControl.fromJson({
      'state': 'migrating',
      'account_generation': 2,
      'client_action': 'migration_maintenance',
      'offline_queue_instruction': 'drain',
      'product_traffic_allowed': false,
      'legacy_writes_allowed': false,
      'auth_bootstrap_reachable': true,
    });
    expect(gate.shouldUploadOfflineQueues(drainWhileBlocked), isFalse);
  });

  test('quarantine instruction blocks offline uploads', () {
    final control = AccountCutoverControl.fromJson({
      'state': 'new',
      'account_generation': 3,
      'client_action': 'none',
      'offline_queue_instruction': 'quarantine',
      'product_traffic_allowed': false,
      'legacy_writes_allowed': false,
      'auth_bootstrap_reachable': true,
      'stranded_new_data': false,
    });
    expect(gate.shouldQuarantineOfflineQueues(control), isTrue);
    expect(gate.shouldUploadOfflineQueues(control), isFalse);
  });

  test('rolled_back_stranded remains observable', () {
    final control = AccountCutoverControl.fromJson({
      'state': 'rolled_back_stranded',
      'account_generation': 4,
      'client_action': 'migration_maintenance',
      'offline_queue_instruction': 'quarantine',
      'stranded_new_data': true,
      'product_traffic_allowed': false,
      'legacy_writes_allowed': true,
      'auth_bootstrap_reachable': true,
    });
    expect(control.state, AccountCutoverState.rolledBackStranded);
    expect(control.strandedNewData, isTrue);
    expect(gate.decide(control), AccountCutoverGateDecision.migrationMaintenance);
  });
}
