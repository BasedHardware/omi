/// Account cutover control projection (server-authoritative).
///
/// LIFECYCLE: permanent
library;

enum AccountCutoverState {
  legacy,
  migrating,
  neu, // "new" is reserved in Dart contexts; wire value remains "new"
  rolledBackStranded,
}

enum AccountCutoverClientAction {
  none,
  forceUpgrade,
  migrationMaintenance,
}

enum OfflineQueueInstruction {
  none,
  drain,
  quarantine,
}

AccountCutoverState parseAccountCutoverState(String? raw) {
  switch (raw) {
    case 'migrating':
      return AccountCutoverState.migrating;
    case 'new':
      return AccountCutoverState.neu;
    case 'rolled_back_stranded':
      return AccountCutoverState.rolledBackStranded;
    case 'legacy':
    default:
      return AccountCutoverState.legacy;
  }
}

AccountCutoverClientAction parseAccountCutoverClientAction(String? raw) {
  switch (raw) {
    case 'force_upgrade':
      return AccountCutoverClientAction.forceUpgrade;
    case 'migration_maintenance':
      return AccountCutoverClientAction.migrationMaintenance;
    case 'none':
    default:
      return AccountCutoverClientAction.none;
  }
}

OfflineQueueInstruction parseOfflineQueueInstruction(String? raw) {
  switch (raw) {
    case 'drain':
      return OfflineQueueInstruction.drain;
    case 'quarantine':
      return OfflineQueueInstruction.quarantine;
    case 'none':
    default:
      return OfflineQueueInstruction.none;
  }
}

class AccountCutoverControl {
  const AccountCutoverControl({
    required this.state,
    required this.accountGeneration,
    required this.uiGeneration,
    required this.apiGeneration,
    required this.clientAction,
    required this.offlineQueueInstruction,
    required this.strandedNewData,
    required this.legacyWritesAllowed,
    required this.productTrafficAllowed,
    required this.authBootstrapReachable,
  });

  final AccountCutoverState state;
  final int accountGeneration;
  final int uiGeneration;
  final int apiGeneration;
  final AccountCutoverClientAction clientAction;
  final OfflineQueueInstruction offlineQueueInstruction;
  final bool strandedNewData;
  final bool legacyWritesAllowed;
  final bool productTrafficAllowed;
  final bool authBootstrapReachable;

  factory AccountCutoverControl.legacyDefault() => const AccountCutoverControl(
        state: AccountCutoverState.legacy,
        accountGeneration: 0,
        uiGeneration: 0,
        apiGeneration: 0,
        clientAction: AccountCutoverClientAction.none,
        offlineQueueInstruction: OfflineQueueInstruction.none,
        strandedNewData: false,
        legacyWritesAllowed: true,
        productTrafficAllowed: true,
        authBootstrapReachable: true,
      );

  factory AccountCutoverControl.fromJson(Map<String, dynamic> json) {
    return AccountCutoverControl(
      state: parseAccountCutoverState(json['state'] as String?),
      accountGeneration: (json['account_generation'] as num?)?.toInt() ?? 0,
      uiGeneration: (json['ui_generation'] as num?)?.toInt() ?? 0,
      apiGeneration: (json['api_generation'] as num?)?.toInt() ?? 0,
      clientAction: parseAccountCutoverClientAction(json['client_action'] as String?),
      offlineQueueInstruction: parseOfflineQueueInstruction(json['offline_queue_instruction'] as String?),
      strandedNewData: json['stranded_new_data'] == true,
      legacyWritesAllowed: json['legacy_writes_allowed'] != false,
      productTrafficAllowed: json['product_traffic_allowed'] != false,
      authBootstrapReachable: json['auth_bootstrap_reachable'] != false,
    );
  }

  bool get blocksProductTraffic => clientAction != AccountCutoverClientAction.none || productTrafficAllowed == false;
}
