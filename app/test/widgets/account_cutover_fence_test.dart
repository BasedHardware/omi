import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/services/account_cutover/account_cutover_blocking_gate.dart';
import 'package:omi/services/account_cutover/account_cutover_control.dart';
import 'package:omi/services/account_cutover/account_cutover_control_client.dart';
import 'package:omi/services/account_cutover/account_cutover_gate.dart';
import 'package:omi/services/account_cutover/account_cutover_runtime.dart';

AccountCutoverControl _control({
  String state = 'legacy',
  int accountGeneration = 0,
  String clientAction = 'none',
  bool productTrafficAllowed = true,
  bool legacyWritesAllowed = true,
}) {
  return AccountCutoverControl.fromJson({
    'state': state,
    'account_generation': accountGeneration,
    'ui_generation': accountGeneration,
    'api_generation': accountGeneration,
    'client_action': clientAction,
    'offline_queue_instruction': productTrafficAllowed ? 'none' : 'quarantine',
    'product_traffic_allowed': productTrafficAllowed,
    'legacy_writes_allowed': legacyWritesAllowed,
    'auth_bootstrap_reachable': true,
    'stranded_new_data': false,
  });
}

Future<void> _pumpGate(WidgetTester tester) async {
  await tester.pumpWidget(
    const MaterialApp(
      localizationsDelegates: [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: AppLocalizations.supportedLocales,
      home: AccountCutoverBlockingGate(child: Text('product')),
    ),
  );
  await tester.pump();
}

void main() {
  setUp(() {
    AccountCutoverRuntime.instance.resetForTesting();
  });

  tearDown(() {
    AccountCutoverRuntime.instance.resetForTesting();
  });

  testWidgets('a fence the server never confirmed keeps a working escape hatch', (tester) async {
    final runtime = AccountCutoverRuntime.instance;
    // The server authoritatively allowed product traffic, then a single
    // refresh failed closed (control-plane 503 / unparseable body).
    runtime.apply(_control(accountGeneration: 5));
    runtime.applyFetchResult(const AccountCutoverFetchResult.unavailable());

    await _pumpGate(tester);

    // The fence is correct — it fails closed — but the server never asked for
    // a migration, so say that control is unavailable instead of claiming one.
    expect(find.text('product'), findsNothing);
    expect(find.text('Connection Error'), findsOneWidget);
    expect(find.text('Migration in Progress'), findsNothing);
    expect(find.text('Retry'), findsOneWidget);
    expect(find.text('Continue'), findsOneWidget);
    expect(find.byType(TextButton), findsOneWidget);

    await tester.tap(find.byType(TextButton));
    await tester.pump();

    expect(find.text('product'), findsOneWidget);
    // Skip restores the last projection the server actually sent, not a blank
    // legacy default that would forget the account generation.
    expect(runtime.control.accountGeneration, 5);

    // Unmount so the gate cancels its fence-refresh timer.
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('the escape hatch is hidden only while the server itself confirms the fence', (tester) async {
    final runtime = AccountCutoverRuntime.instance;
    // A migration the server authoritatively declared: no way around it.
    runtime.apply(
      _control(
        state: 'migrating',
        accountGeneration: 9,
        clientAction: 'migration_maintenance',
        productTrafficAllowed: false,
        legacyWritesAllowed: false,
      ),
    );

    await _pumpGate(tester);

    expect(find.text('product'), findsNothing);
    expect(find.text('Migration in Progress'), findsOneWidget);
    expect(find.text('Connection Error'), findsNothing);
    expect(find.byType(TextButton), findsNothing);

    // Same widget, same screen, different cause: the server answers "allow"
    // for this owner and a later refresh then fails closed. That fence was
    // synthesized by the client, so the escape hatch must come back.
    var fetches = 0;
    final client = AccountCutoverControlClient(
      fetch: () async {
        fetches++;
        if (fetches == 1) return AccountCutoverFetchResult.success(_control(accountGeneration: 5));
        return const AccountCutoverFetchResult.unavailable();
      },
    );

    await runtime.bindAuthenticatedOwner('owner-a', client: client);
    await tester.pump();
    expect(find.text('product'), findsOneWidget);

    await runtime.refresh(client: client);
    await tester.pump();

    expect(find.text('product'), findsNothing);
    expect(find.text('Connection Error'), findsOneWidget);
    expect(find.text('Migration in Progress'), findsNothing);
    expect(find.text('Retry'), findsOneWidget);
    expect(find.text('Continue'), findsOneWidget);
    expect(find.byType(TextButton), findsOneWidget);

    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('the fence re-fetches control every 30s and lifts itself when the server recovers', (tester) async {
    final runtime = AccountCutoverRuntime.instance;
    var fetches = 0;
    final client = AccountCutoverControlClient(
      fetch: () async {
        fetches++;
        // Two failed control fetches, then the control plane comes back.
        if (fetches <= 2) return const AccountCutoverFetchResult.unavailable();
        return AccountCutoverFetchResult.success(_control());
      },
    );
    // The gate's retry loop calls the parameterless refresh(); point that at
    // the scripted client instead of the network.
    AccountCutoverRuntime.controlClientOverrideForTesting = client;

    await runtime.bindAuthenticatedOwner('owner-a');
    expect(fetches, 1);
    expect(runtime.decision, AccountCutoverGateDecision.migrationMaintenance);
    expect(runtime.blockingReason, AccountCutoverBlockingReason.controlUnavailable);

    await _pumpGate(tester);
    expect(find.text('product'), findsNothing);
    expect(find.text('Connection Error'), findsOneWidget);
    expect(find.text('Migration in Progress'), findsNothing);
    // The server has never allowed this owner, so there is no escape hatch to
    // fall back on: retrying is the only way this screen can ever clear.
    expect(find.byType(TextButton), findsNothing);

    await tester.tap(find.text('Retry'));
    await tester.pump();
    expect(fetches, 2);
    expect(find.text('product'), findsNothing);

    // Nothing else in the app re-fetches control while product traffic is
    // blocked, so the fence can only lift if the gate retries by itself.
    await tester.pump(const Duration(seconds: 29));
    expect(fetches, 2);
    expect(find.text('product'), findsNothing);

    await tester.pump(const Duration(seconds: 1));
    await tester.pump();
    expect(fetches, 3);
    expect(find.text('product'), findsOneWidget);

    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('retry and the periodic refresh never overlap control requests', (tester) async {
    final runtime = AccountCutoverRuntime.instance;
    final pendingRetry = Completer<AccountCutoverFetchResult>();
    var fetches = 0;
    final client = AccountCutoverControlClient(
      fetch: () {
        fetches++;
        if (fetches == 1) return Future.value(const AccountCutoverFetchResult.unavailable());
        return pendingRetry.future;
      },
    );
    AccountCutoverRuntime.controlClientOverrideForTesting = client;

    await runtime.bindAuthenticatedOwner('owner-a');
    await _pumpGate(tester);

    await tester.tap(find.text('Retry'));
    await tester.pump();
    expect(fetches, 2);

    await tester.tap(find.text('Retry'));
    await tester.pump(const Duration(seconds: 30));
    expect(fetches, 2);

    pendingRetry.complete(AccountCutoverFetchResult.success(_control()));
    await tester.pump();
    expect(find.text('product'), findsOneWidget);

    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('an offline owner switch shows a connection fence, never a migration claim', (tester) async {
    final runtime = AccountCutoverRuntime.instance;
    await runtime.bindAuthenticatedOwner(
      'owner-a',
      client: AccountCutoverControlClient(fetch: () async => AccountCutoverFetchResult.success(_control())),
    );
    await runtime.bindAuthenticatedOwner(
      'owner-b',
      client: AccountCutoverControlClient(fetch: () async => const AccountCutoverFetchResult.transportFailure()),
    );

    expect(runtime.decision, AccountCutoverGateDecision.migrationMaintenance);
    expect(runtime.blockingReason, AccountCutoverBlockingReason.connectionUnavailable);

    await _pumpGate(tester);

    expect(find.text('product'), findsNothing);
    expect(find.text('No internet connection'), findsOneWidget);
    expect(find.text('Migration in Progress'), findsNothing);
    expect(find.text('Retry'), findsOneWidget);

    await tester.pumpWidget(const SizedBox.shrink());
  });
}
