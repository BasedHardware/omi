import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/account_cutover/account_cutover_control.dart';
import 'package:omi/services/account_cutover/account_cutover_control_client.dart';
import 'package:omi/services/account_cutover/account_cutover_gate.dart';
import 'package:omi/services/account_cutover/account_cutover_runtime.dart';

Map<String, dynamic> _validControlJson({
  String state = 'legacy',
  int accountGeneration = 0,
  String clientAction = 'none',
  String offlineQueueInstruction = 'none',
  bool productTrafficAllowed = true,
  bool legacyWritesAllowed = true,
  bool authBootstrapReachable = true,
  bool strandedNewData = false,
}) {
  return {
    'state': state,
    'account_generation': accountGeneration,
    'ui_generation': accountGeneration,
    'api_generation': accountGeneration,
    'client_action': clientAction,
    'offline_queue_instruction': offlineQueueInstruction,
    'product_traffic_allowed': productTrafficAllowed,
    'legacy_writes_allowed': legacyWritesAllowed,
    'auth_bootstrap_reachable': authBootstrapReachable,
    'stranded_new_data': strandedNewData,
  };
}

class _CutoverTestEnv implements EnvFields {
  @override
  String? get apiBaseUrl => 'https://api.omi.me/';

  @override
  String? get googleClientId => null;

  @override
  String? get googleClientSecret => null;

  @override
  String? get googleMapsApiKey => null;

  @override
  String? get intercomAppId => null;

  @override
  String? get intercomIOSApiKey => null;

  @override
  String? get intercomAndroidApiKey => null;

  @override
  String? get posthogApiKey => null;

  @override
  bool? get useAuthCustomToken => false;

  @override
  bool? get useWebAuth => false;
}

void main() {
  const gate = AccountCutoverGate();

  setUpAll(() {
    Env.init(_CutoverTestEnv());
  });

  setUp(() {
    AccountCutoverRuntime.instance.resetForTesting();
  });

  test('legacy default allows product traffic and uploads', () {
    final control = AccountCutoverControl.legacyDefault();
    expect(gate.decide(control), AccountCutoverGateDecision.allowProductTraffic);
    expect(gate.shouldUploadOfflineQueues(control), isTrue);
    expect(gate.shouldQuarantineOfflineQueues(control), isFalse);
  });

  test('force upgrade fails closed before product traffic', () {
    final control = AccountCutoverControl.fromJson(
      _validControlJson(clientAction: 'force_upgrade', productTrafficAllowed: false, legacyWritesAllowed: false),
    );
    expect(gate.decide(control), AccountCutoverGateDecision.forceUpgrade);
    expect(gate.shouldUploadOfflineQueues(control), isFalse);
  });

  test('migration maintenance quarantines offline queues', () {
    final control = AccountCutoverControl.fromJson(
      _validControlJson(
        state: 'migrating',
        accountGeneration: 2,
        clientAction: 'migration_maintenance',
        offlineQueueInstruction: 'quarantine',
        productTrafficAllowed: false,
        legacyWritesAllowed: false,
      ),
    );
    expect(gate.decide(control), AccountCutoverGateDecision.migrationMaintenance);
    expect(gate.shouldUploadOfflineQueues(control), isFalse);
    expect(gate.shouldQuarantineOfflineQueues(control), isTrue);
  });

  test('drain only while product traffic remains allowed', () {
    final drainLegacy = AccountCutoverControl.fromJson(_validControlJson(offlineQueueInstruction: 'drain'));
    expect(gate.shouldUploadOfflineQueues(drainLegacy), isTrue);

    final drainWhileBlocked = AccountCutoverControl.fromJson(
      _validControlJson(
        state: 'migrating',
        accountGeneration: 2,
        clientAction: 'migration_maintenance',
        offlineQueueInstruction: 'drain',
        productTrafficAllowed: false,
        legacyWritesAllowed: false,
      ),
    );
    expect(gate.shouldUploadOfflineQueues(drainWhileBlocked), isFalse);
  });

  test('quarantine instruction blocks offline uploads', () {
    final control = AccountCutoverControl.fromJson(
      _validControlJson(
        state: 'new',
        accountGeneration: 3,
        offlineQueueInstruction: 'quarantine',
        productTrafficAllowed: false,
        legacyWritesAllowed: false,
      ),
    );
    expect(gate.shouldQuarantineOfflineQueues(control), isTrue);
    expect(gate.shouldUploadOfflineQueues(control), isFalse);
  });

  test('rolled_back_stranded remains observable', () {
    final control = AccountCutoverControl.fromJson(
      _validControlJson(
        state: 'rolled_back_stranded',
        accountGeneration: 4,
        clientAction: 'migration_maintenance',
        offlineQueueInstruction: 'quarantine',
        strandedNewData: true,
        productTrafficAllowed: false,
      ),
    );
    expect(control.state, AccountCutoverState.rolledBackStranded);
    expect(control.strandedNewData, isTrue);
    expect(gate.decide(control), AccountCutoverGateDecision.migrationMaintenance);
  });

  test('unknown wire enums and non-boolean safety flags are rejected', () {
    expect(
      () => AccountCutoverControl.fromJson(_validControlJson(state: 'future_state')),
      throwsA(isA<AccountCutoverControlParseException>()),
    );
    expect(
      () => AccountCutoverControl.fromJson({..._validControlJson(), 'product_traffic_allowed': 'yes'}),
      throwsA(isA<AccountCutoverControlParseException>()),
    );
    expect(
      () => AccountCutoverControl.fromJson({..._validControlJson()..remove('product_traffic_allowed')}),
      throwsA(isA<AccountCutoverControlParseException>()),
    );
  });

  test('503 and malformed control responses classify as unavailable', () {
    expect(
      AccountCutoverControlClient.interpretControlResponse(http.Response('{}', 503)).kind,
      AccountCutoverFetchKind.unavailable,
    );
    expect(
      AccountCutoverControlClient.interpretControlResponse(
        http.Response('{"state":"legacy","client_action":"none"}', 200),
      ).kind,
      AccountCutoverFetchKind.unavailable,
    );
  });

  test('runtime retains generation across failed refresh and blocks product traffic', () async {
    final runtime = AccountCutoverRuntime.instance;
    final migrating = AccountCutoverControl.fromJson(
      _validControlJson(
        state: 'migrating',
        accountGeneration: 9,
        clientAction: 'migration_maintenance',
        offlineQueueInstruction: 'quarantine',
        productTrafficAllowed: false,
        legacyWritesAllowed: false,
      ),
    );

    var fetches = 0;
    final client = AccountCutoverControlClient(
      fetch: () async {
        fetches++;
        if (fetches == 1) {
          return AccountCutoverFetchResult.success(migrating);
        }
        return const AccountCutoverFetchResult.transportFailure();
      },
    );

    await runtime.bindAuthenticatedOwner('owner-a', client: client);
    expect(runtime.control.accountGeneration, 9);
    expect(runtime.decision, AccountCutoverGateDecision.migrationMaintenance);

    await runtime.refresh(client: client);
    expect(runtime.control.accountGeneration, 9);
    expect(runtime.control.productTrafficAllowed, isFalse);
    expect(runtime.decision, AccountCutoverGateDecision.migrationMaintenance);
    expect(runtime.allowsOfflineQueueUpload, isFalse);
  });

  test('first bind of a fresh runtime recovers to legacy-compatible after a transport failure', () async {
    final runtime = AccountCutoverRuntime.instance;
    final client = AccountCutoverControlClient(fetch: () async => const AccountCutoverFetchResult.transportFailure());

    await runtime.bindAuthenticatedOwner('owner-a', client: client);

    expect(runtime.isResolvedForOwner, isTrue);
    expect(runtime.hasAuthoritativeControl, isFalse);
    expect(runtime.decision, AccountCutoverGateDecision.allowProductTraffic);
  });

  test('a genuine owner switch stays fenced across a transport failure (no leaked prior allow)', () async {
    final runtime = AccountCutoverRuntime.instance;
    final ownerAControl = AccountCutoverControl.fromJson(_validControlJson(accountGeneration: 7));
    await runtime.bindAuthenticatedOwner(
      'owner-a',
      client: AccountCutoverControlClient(fetch: () async => AccountCutoverFetchResult.success(ownerAControl)),
    );
    expect(runtime.decision, AccountCutoverGateDecision.allowProductTraffic);

    final failingClient = AccountCutoverControlClient(
      fetch: () async => const AccountCutoverFetchResult.transportFailure(),
    );
    await runtime.bindAuthenticatedOwner('owner-b', client: failingClient);

    expect(runtime.isResolvedForOwner, isTrue);
    expect(runtime.hasAuthoritativeControl, isFalse);
    expect(runtime.decision, AccountCutoverGateDecision.migrationMaintenance);

    // The owner change discarded owner-a's projection, so there is nothing the
    // server ever allowed for owner-b to fall back to: no escape hatch, and
    // owner-a's allow can never be reached through one.
    expect(runtime.canSkipUnresolvedFence, isFalse);
    expect(runtime.skipUnresolvedFence(), isFalse);
    expect(runtime.decision, AccountCutoverGateDecision.migrationMaintenance);
  });

  test('the escape hatch never invents an allow the server has not given', () async {
    final runtime = AccountCutoverRuntime.instance;
    final pending = Completer<AccountCutoverFetchResult>();
    unawaited(
      runtime.bindAuthenticatedOwner('owner-a', client: AccountCutoverControlClient(fetch: () => pending.future)),
    );

    // The owner's first fetch has not landed, so the fence has no
    // server-allowed projection to fall back to: it must hold.
    expect(runtime.decision, AccountCutoverGateDecision.migrationMaintenance);
    expect(runtime.canSkipUnresolvedFence, isFalse);
    expect(runtime.skipUnresolvedFence(), isFalse);
    expect(runtime.decision, AccountCutoverGateDecision.migrationMaintenance);

    // Same once the server answers with a fence of its own.
    final fenced = AccountCutoverControl.fromJson(
      _validControlJson(state: 'migrating', clientAction: 'migration_maintenance', productTrafficAllowed: false),
    );
    pending.complete(AccountCutoverFetchResult.success(fenced));
    await Future<void>.delayed(Duration.zero);
    expect(runtime.decision, AccountCutoverGateDecision.migrationMaintenance);
    expect(runtime.canSkipUnresolvedFence, isFalse);
    expect(runtime.skipUnresolvedFence(), isFalse);
    expect(runtime.decision, AccountCutoverGateDecision.migrationMaintenance);
  });

  test('a transport blip after an authoritative allow does NOT fence (stays on last-known-good)', () async {
    final runtime = AccountCutoverRuntime.instance;
    final legacy = AccountCutoverControl.fromJson(_validControlJson(accountGeneration: 5));
    var fetches = 0;
    final client = AccountCutoverControlClient(
      fetch: () async {
        fetches++;
        if (fetches == 1) return AccountCutoverFetchResult.success(legacy);
        return const AccountCutoverFetchResult.transportFailure();
      },
    );

    await runtime.bindAuthenticatedOwner('owner-a', client: client);
    expect(runtime.decision, AccountCutoverGateDecision.allowProductTraffic);

    // Regression: one timed-out control refresh used to synthesize a
    // maintenance fence with no exit, while the server kept answering
    // legacy/none the whole time.
    await runtime.refresh(client: client);
    expect(runtime.decision, AccountCutoverGateDecision.allowProductTraffic);
    expect(runtime.control.accountGeneration, 5);
    expect(runtime.canSkipUnresolvedFence, isTrue);
  });

  test('an explicit 503 after an authoritative allow fences but keeps the escape hatch', () async {
    final runtime = AccountCutoverRuntime.instance;
    final legacy = AccountCutoverControl.fromJson(_validControlJson(accountGeneration: 5));
    var fetches = 0;
    final client = AccountCutoverControlClient(
      fetch: () async {
        fetches++;
        if (fetches == 1) return AccountCutoverFetchResult.success(legacy);
        return const AccountCutoverFetchResult.unavailable();
      },
    );

    await runtime.bindAuthenticatedOwner('owner-a', client: client);
    await runtime.refresh(client: client);

    // The server explicitly failed closed — respect the fence...
    expect(runtime.decision, AccountCutoverGateDecision.migrationMaintenance);
    // ...but it never authoritatively said "migrating", so the fence is
    // unconfirmed and the user can skip back to the last-known-good state.
    expect(runtime.canSkipUnresolvedFence, isTrue);
    expect(runtime.skipUnresolvedFence(), isTrue);
    expect(runtime.decision, AccountCutoverGateDecision.allowProductTraffic);
    expect(runtime.control.accountGeneration, 5);
  });

  test('a server-confirmed fence refuses the escape hatch across outages', () async {
    final runtime = AccountCutoverRuntime.instance;
    final migrating = AccountCutoverControl.fromJson(
      _validControlJson(
        state: 'migrating',
        accountGeneration: 9,
        clientAction: 'migration_maintenance',
        offlineQueueInstruction: 'quarantine',
        productTrafficAllowed: false,
        legacyWritesAllowed: false,
      ),
    );
    var fetches = 0;
    final client = AccountCutoverControlClient(
      fetch: () async {
        fetches++;
        if (fetches == 1) return AccountCutoverFetchResult.success(migrating);
        return const AccountCutoverFetchResult.transportFailure();
      },
    );

    await runtime.bindAuthenticatedOwner('owner-a', client: client);
    await runtime.refresh(client: client);

    expect(runtime.decision, AccountCutoverGateDecision.migrationMaintenance);
    expect(runtime.canSkipUnresolvedFence, isFalse);
    expect(runtime.skipUnresolvedFence(), isFalse);
    expect(runtime.decision, AccountCutoverGateDecision.migrationMaintenance);
  });

  test('owner transition clears prior account state and ignores stale in-flight results', () async {
    final runtime = AccountCutoverRuntime.instance;
    final pendingFirst = Completer<AccountCutoverFetchResult>();
    final first = AccountCutoverControlClient(fetch: () => pendingFirst.future);

    final firstBind = runtime.bindAuthenticatedOwner('owner-a', client: first);
    expect(runtime.isResolvedForOwner, isFalse);
    expect(runtime.decision, AccountCutoverGateDecision.migrationMaintenance);

    final secondControl = AccountCutoverControl.fromJson(
      _validControlJson(
        state: 'new',
        accountGeneration: 3,
        productTrafficAllowed: false,
        legacyWritesAllowed: false,
        offlineQueueInstruction: 'quarantine',
      ),
    );
    await runtime.bindAuthenticatedOwner(
      'owner-b',
      client: AccountCutoverControlClient(fetch: () async => AccountCutoverFetchResult.success(secondControl)),
    );
    expect(runtime.ownerUid, 'owner-b');
    expect(runtime.control.accountGeneration, 3);

    // Stale owner-a success must not clobber owner-b.
    pendingFirst.complete(
      AccountCutoverFetchResult.success(
        AccountCutoverControl.fromJson(_validControlJson(accountGeneration: 99, state: 'legacy')),
      ),
    );
    await firstBind;
    expect(runtime.ownerUid, 'owner-b');
    expect(runtime.control.accountGeneration, 3);
  });

  test('account generation header attaches only to authenticated Omi API mutations', () {
    expect(
      shouldAttachAccountGenerationHeader(
        url: 'https://api.omi.me/v1/conversations',
        method: 'POST',
        requireAuthCheck: true,
      ),
      isTrue,
    );
    expect(
      shouldAttachAccountGenerationHeader(
        url: 'https://api.omi.me/v1/conversations',
        method: 'GET',
        requireAuthCheck: true,
      ),
      isFalse,
    );
    expect(
      shouldAttachAccountGenerationHeader(
        url: 'https://cdn.example.com/firmware.zip',
        method: 'GET',
        requireAuthCheck: false,
      ),
      isFalse,
    );
    expect(
      shouldAttachAccountGenerationHeader(
        url: 'https://cdn.example.com/firmware.zip',
        method: 'POST',
        requireAuthCheck: true,
      ),
      isFalse,
    );
  });

  test('account generation header attaches to authenticated Omi product WebSockets', () {
    expect(
      shouldAttachAccountGenerationHeader(
        url: 'wss://api.omi.me/v4/listen',
        requireAuthCheck: true,
        forWebSocket: true,
      ),
      isTrue,
    );
    expect(
      shouldAttachAccountGenerationHeader(
        url: 'wss://cdn.example.com/stream',
        requireAuthCheck: true,
        forWebSocket: true,
      ),
      isFalse,
    );
    expect(shouldAttachAccountGenerationHeader(url: 'wss://api.omi.me/v4/listen', requireAuthCheck: true), isFalse);
  });

  test('omi API host match is scheme-neutral for https and wss', () {
    expect(
      normalizeOmiApiUrlForHostMatch('https://api.omi.me/v1/x'),
      normalizeOmiApiUrlForHostMatch('wss://api.omi.me/v1/x'),
    );
  });
}
