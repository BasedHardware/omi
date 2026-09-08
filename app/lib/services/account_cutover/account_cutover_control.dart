/// Account cutover control projection (server-authoritative).
///
/// LIFECYCLE: permanent
library;

class AccountCutoverControlParseException implements Exception {
  const AccountCutoverControlParseException(this.message);
  final String message;

  @override
  String toString() => 'AccountCutoverControlParseException: $message';
}

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
      return AccountCutoverState.legacy;
    default:
      throw AccountCutoverControlParseException('unsupported cutover state: $raw');
  }
}

AccountCutoverClientAction parseAccountCutoverClientAction(String? raw) {
  switch (raw) {
    case 'force_upgrade':
      return AccountCutoverClientAction.forceUpgrade;
    case 'migration_maintenance':
      return AccountCutoverClientAction.migrationMaintenance;
    case 'none':
      return AccountCutoverClientAction.none;
    default:
      throw AccountCutoverControlParseException('unsupported client_action: $raw');
  }
}

OfflineQueueInstruction parseOfflineQueueInstruction(String? raw) {
  switch (raw) {
    case 'drain':
      return OfflineQueueInstruction.drain;
    case 'quarantine':
      return OfflineQueueInstruction.quarantine;
    case 'none':
      return OfflineQueueInstruction.none;
    default:
      throw AccountCutoverControlParseException('unsupported offline_queue_instruction: $raw');
  }
}

bool _requireBool(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is bool) return value;
  throw AccountCutoverControlParseException('expected boolean for $key, got ${value.runtimeType}');
}

String _requireString(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is String) return value;
  throw AccountCutoverControlParseException('expected string for $key, got ${value.runtimeType}');
}

int _requireNonNegativeInt(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is num && value == value.roundToDouble() && value >= 0) {
    return value.toInt();
  }
  throw AccountCutoverControlParseException('expected non-negative int for $key, got $value');
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

  /// Fail-closed maintenance projection used when control is unavailable,
  /// malformed, or a refresh fails after an authoritative projection was seen.
  /// Retains generation fields from [retaining] so mutations keep presenting
  /// the last known `X-Account-Generation`.
  factory AccountCutoverControl.unavailable({AccountCutoverControl? retaining}) {
    return AccountCutoverControl(
      state: retaining?.state ?? AccountCutoverState.migrating,
      accountGeneration: retaining?.accountGeneration ?? 0,
      uiGeneration: retaining?.uiGeneration ?? 0,
      apiGeneration: retaining?.apiGeneration ?? 0,
      clientAction: AccountCutoverClientAction.migrationMaintenance,
      offlineQueueInstruction: OfflineQueueInstruction.quarantine,
      strandedNewData: retaining?.strandedNewData ?? false,
      legacyWritesAllowed: false,
      productTrafficAllowed: false,
      authBootstrapReachable: true,
    );
  }

  factory AccountCutoverControl.fromJson(Map<String, dynamic> json) {
    if (!json.containsKey('state') ||
        !json.containsKey('client_action') ||
        !json.containsKey('offline_queue_instruction') ||
        !json.containsKey('account_generation') ||
        !json.containsKey('product_traffic_allowed') ||
        !json.containsKey('legacy_writes_allowed') ||
        !json.containsKey('auth_bootstrap_reachable')) {
      throw const AccountCutoverControlParseException('incomplete cutover control projection');
    }

    return AccountCutoverControl(
      state: parseAccountCutoverState(_requireString(json, 'state')),
      accountGeneration: _requireNonNegativeInt(json, 'account_generation'),
      uiGeneration: json.containsKey('ui_generation') ? _requireNonNegativeInt(json, 'ui_generation') : 0,
      apiGeneration: json.containsKey('api_generation') ? _requireNonNegativeInt(json, 'api_generation') : 0,
      clientAction: parseAccountCutoverClientAction(_requireString(json, 'client_action')),
      offlineQueueInstruction: parseOfflineQueueInstruction(_requireString(json, 'offline_queue_instruction')),
      strandedNewData: json.containsKey('stranded_new_data') ? _requireBool(json, 'stranded_new_data') : false,
      legacyWritesAllowed: _requireBool(json, 'legacy_writes_allowed'),
      productTrafficAllowed: _requireBool(json, 'product_traffic_allowed'),
      authBootstrapReachable: _requireBool(json, 'auth_bootstrap_reachable'),
    );
  }
}
