import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/home/widgets/pendant_reconnect_nudge_card.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';

import '../../support/surface_render.dart';

void main() {
  const treatment = 'fixture-1';
  const otherTreatment = 'fixture-2';
  const holdout = 'fixture-0';
  const cardKey = ValueKey('pendant_reconnect_nudge');
  const eligibleName = 'Pendant Reconnect Nudge Eligible';
  const shownName = 'Pendant Reconnect Nudge Shown';
  final preferences = SharedPreferencesUtil();
  final emitted = <RegisteredEvent>[];
  var flagReads = 0;

  setUpAll(loadSurfaceRenderFonts);

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    emitted.clear();
    flagReads = 0;
    OmiColors.active = OmiPalette.dark;
    addTearDown(() => OmiColors.active = OmiPalette.light);
  });

  void seed({
    String uid = treatment,
    Duration gap = const Duration(days: 4),
    DeviceType type = DeviceType.omi,
  }) {
    preferences.uid = uid;
    preferences.btDevice = BtDevice(id: 'paired', name: 'Omi', type: type, rssi: 0);
    preferences.lastPendantConnectedAt = DateTime.now().subtract(gap).millisecondsSinceEpoch;
  }

  Future<void> pumpHome(
    WidgetTester tester, {
    String? uid = treatment,
    bool homeSelected = true,
    bool? enabled = true,
    bool unreadable = false,
  }) async {
    if (tester.binding.lifecycleState != AppLifecycleState.resumed) {
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    }
    await tester.pumpWidget(MaterialApp(
      theme: buildOmiTheme(),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(
          backgroundColor: OmiColors.surface0,
          body: Column(children: [
            if (homeSelected) const SizedBox.shrink(),
            PendantReconnectNudgeCard(
              key: const ValueKey('nudge_fixture'),
              uid: uid,
              createdAt: DateTime.now().subtract(const Duration(days: 60)),
              paying: false,
              homeSelected: homeSelected,
              pendantConnected: false,
              readFlag: (_) async {
                flagReads++;
                if (unreadable) throw StateError('flag read failed');
                return enabled;
              },
              emit: emitted.add,
              devicePage: const Scaffold(body: Text('Device settings fixture')),
            ),
            if (!homeSelected) const SizedBox.shrink(),
          ])),
    ));
    await tester.pumpAndSettle();
  }

  List<String> eventNames() => emitted.map((event) => event.wireName).toList();

  testWidgets('eligible treatment renders once, logs the same context, and dismisses on Home', (tester) async {
    if (surfaceRenderOutput.isNotEmpty) {
      await tester.binding.setSurfaceSize(const Size(390, 300));
      addTearDown(() => tester.binding.setSurfaceSize(null));
    }
    seed(type: DeviceType.friendPendant);
    await pumpHome(tester);
    expect(find.byKey(cardKey), findsOneWidget);
    expect(find.text("Your Omi hasn't connected in 3 days"), findsOneWidget);
    expect(find.text('Put it back on and reconnect so Omi keeps capturing.'), findsOneWidget);
    expect(eventNames(), [eligibleName, shownName]);
    await writeSurfaceRender(tester, '001-mobile-ios-pendant-reconnect-nudge');
    expect(emitted[1].properties, emitted[0].properties);
    expect(preferences.pendantReconnectNudgeLastShownAt, greaterThan(0));
    expect(preferences.pendantDropoffSurfaceLastDay, isNotEmpty);

    await pumpHome(tester);
    expect(eventNames(), [eligibleName, shownName]);
    expect(flagReads, 1);

    await tester.tap(find.byKey(const ValueKey('pendant_reconnect_nudge_dismiss')));
    await tester.pumpAndSettle();
    expect(find.byKey(cardKey), findsNothing);
    expect(find.text('Device settings fixture'), findsNothing);
    expect(eventNames(), [eligibleName, shownName, 'Pendant Reconnect Nudge Dismissed']);
    expect(emitted.last.properties, emitted.first.properties);
  });

  testWidgets('Reconnect logs the tap, opens device settings, and consumes the card', (tester) async {
    seed();
    await pumpHome(tester);
    await tester.tap(find.byKey(const ValueKey('pendant_reconnect_nudge_action')));
    await tester.pumpAndSettle();
    expect(find.text('Device settings fixture'), findsOneWidget);
    expect(eventNames(), [eligibleName, shownName, 'Pendant Reconnect Nudge Tapped']);
    expect(emitted.last.properties, emitted.first.properties);
    Navigator.of(tester.element(find.text('Device settings fixture'))).pop();
    await tester.pumpAndSettle();
    expect(find.byKey(cardKey), findsNothing);
  });

  testWidgets('holdout enrolls once per cooldown and sees no card on a later resume', (tester) async {
    seed(uid: holdout);
    await pumpHome(tester, uid: holdout, homeSelected: false);
    expect(flagReads, 0);
    await pumpHome(tester, uid: holdout);
    expect(find.byKey(cardKey), findsNothing);
    expect(eventNames(), [eligibleName]);
    expect(emitted.single.properties['arm'], 'holdout');
    await pumpHome(tester, uid: holdout);
    expect(eventNames(), [eligibleName]);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pumpAndSettle();
    expect(eventNames(), [eligibleName]);
    expect(flagReads, 1);
    expect(preferences.pendantReconnectNudgeLastEnrolledAt, greaterThan(0));
    expect(preferences.pendantReconnectNudgeLastShownAt, 0);
    expect(preferences.pendantDropoffSurfaceLastDay, isEmpty);
  });

  testWidgets('a gap under 72 hours is silent', (tester) async {
    seed(gap: const Duration(hours: 71));
    await pumpHome(tester);
    expect(find.byKey(cardKey), findsNothing);
    expect(emitted, isEmpty);
    expect(flagReads, 0);
  });

  testWidgets('a pending card survives switching away from and back to Home', (tester) async {
    seed();
    await pumpHome(tester);
    expect(find.byKey(cardKey), findsOneWidget);
    final shownAt = preferences.pendantReconnectNudgeLastShownAt;

    await pumpHome(tester, homeSelected: false);
    expect(find.byKey(cardKey), findsNothing);
    await pumpHome(tester);
    expect(find.byKey(cardKey), findsOneWidget);
    expect(eventNames(), [eligibleName, shownName]);
    expect(preferences.pendantReconnectNudgeLastShownAt, shownAt);
    expect(flagReads, 1);
  });

  testWidgets('a pending card survives app resume and can still be dismissed', (tester) async {
    seed();
    await pumpHome(tester);
    expect(find.byKey(cardKey), findsOneWidget);
    final shownAt = preferences.pendantReconnectNudgeLastShownAt;

    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pumpAndSettle();
    expect(find.byKey(cardKey), findsOneWidget);
    expect(eventNames(), [eligibleName, shownName]);
    expect(preferences.pendantReconnectNudgeLastShownAt, shownAt);
    expect(flagReads, 1);

    await tester.tap(find.byKey(const ValueKey('pendant_reconnect_nudge_dismiss')));
    await tester.pumpAndSettle();
    expect(find.byKey(cardKey), findsNothing);
    expect(eventNames(), [eligibleName, shownName, 'Pendant Reconnect Nudge Dismissed']);
    expect(flagReads, 1);
  });

  testWidgets('reselecting Home evaluates a gap that crossed 72 hours on another tab', (tester) async {
    seed(gap: const Duration(hours: 71));
    await pumpHome(tester);
    expect(find.byKey(cardKey), findsNothing);
    expect(flagReads, 0);

    await pumpHome(tester, homeSelected: false);
    preferences.lastPendantConnectedAt = DateTime.now().subtract(const Duration(hours: 73)).millisecondsSinceEpoch;
    await pumpHome(tester);
    expect(find.byKey(cardKey), findsOneWidget);
    expect(eventNames(), [eligibleName, shownName]);
    expect(flagReads, 1);
  });

  testWidgets('returning to the Home route reevaluates eligibility', (tester) async {
    seed(gap: const Duration(hours: 71));
    await pumpHome(tester);
    expect(find.byKey(cardKey), findsNothing);
    expect(flagReads, 0);

    final navigator = Navigator.of(tester.element(find.byType(PendantReconnectNudgeCard)));
    final routeClosed =
        navigator.push<void>(MaterialPageRoute(builder: (_) => const Scaffold(body: Text('Other route'))));
    await tester.pumpAndSettle();
    preferences.lastPendantConnectedAt = DateTime.now().subtract(const Duration(hours: 73)).millisecondsSinceEpoch;
    navigator.pop();
    await tester.pumpAndSettle();
    await routeClosed;
    expect(find.byKey(cardKey), findsOneWidget);
    expect(eventNames(), [eligibleName, shownName]);
    expect(flagReads, 1);
  });

  testWidgets('the persisted cap suppresses treatment on Home', (tester) async {
    seed();
    preferences.pendantReconnectNudgeLastShownAt =
        DateTime.now().subtract(const Duration(days: 29)).millisecondsSinceEpoch;
    await pumpHome(tester);
    expect(find.byKey(cardKey), findsNothing);
    expect(emitted, isEmpty);
    expect(flagReads, 0);
  });

  testWidgets('a second account on the installation shares the shown cooldown', (tester) async {
    seed();
    await pumpHome(tester);
    final shownAt = preferences.pendantReconnectNudgeLastShownAt;
    expect(shownAt, greaterThan(0));

    seed(uid: otherTreatment);
    preferences.pendantDropoffSurfaceLastDay = '';
    expect(preferences.pendantReconnectNudgeLastEnrolledAt, 0);
    await pumpHome(tester, uid: otherTreatment);
    expect(find.byKey(cardKey), findsNothing);
    expect(preferences.pendantReconnectNudgeLastShownAt, shownAt);
    expect(eventNames(), [eligibleName, shownName]);
    expect(flagReads, 1);
  });

  testWidgets('a missing pendant skips the flag and a saved pairing reevaluates Home', (tester) async {
    preferences.uid = treatment;
    preferences.lastPendantConnectedAt = DateTime.now().subtract(const Duration(days: 4)).millisecondsSinceEpoch;
    await pumpHome(tester);
    expect(flagReads, 0);

    preferences.btDevice = BtDevice(id: 'paired', name: 'Omi', type: DeviceType.omi, rssi: 0);
    await tester.pumpAndSettle();
    expect(find.byKey(cardKey), findsOneWidget);
    expect(flagReads, 1);
  });

  testWidgets('same-day suppression skips the flag', (tester) async {
    seed();
    preferences.pendantDropoffSurfaceLastDay = DateTime.now().toIso8601String().split('T').first;
    await pumpHome(tester);
    expect(find.byKey(cardKey), findsNothing);
    expect(emitted, isEmpty);
    expect(flagReads, 0);
  });

  testWidgets('a definitive off answer is silent and throttles immediate resumes', (tester) async {
    seed();
    await pumpHome(tester, enabled: false);
    expect(find.byKey(cardKey), findsNothing);
    expect(emitted, isEmpty);
    expect(flagReads, 1);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await pumpHome(tester, enabled: false);
    expect(find.byKey(cardKey), findsNothing);
    expect(emitted, isEmpty);
    expect(preferences.pendantReconnectNudgeLastShownAt, 0);
    expect(flagReads, 1);
  });

  testWidgets('an unavailable flag retries once after identity can settle', (tester) async {
    seed();
    await pumpHome(tester, enabled: null);
    expect(emitted, isEmpty);
    expect(flagReads, 1);
    await pumpHome(tester);
    await tester.pump(const Duration(seconds: 1));
    await tester.pumpAndSettle();
    expect(eventNames(), [eligibleName, shownName]);
    expect(flagReads, 2);
  });

  testWidgets('an unreadable flag fails closed after the bounded retry', (tester) async {
    seed();
    await pumpHome(tester, unreadable: true);
    await tester.pump(const Duration(seconds: 1));
    await tester.pumpAndSettle();
    await pumpHome(tester);
    expect(find.byKey(cardKey), findsNothing);
    expect(emitted, isEmpty);
    expect(flagReads, 2);
  });

  testWidgets('signed-out Home never reads the flag or emits', (tester) async {
    seed();
    await pumpHome(tester, uid: null);
    expect(flagReads, 0);
    expect(find.byKey(cardKey), findsNothing);
    expect(emitted, isEmpty);
  });
}
