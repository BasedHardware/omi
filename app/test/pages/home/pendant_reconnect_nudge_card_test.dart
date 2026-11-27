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
    bool enabled = true,
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
            PendantReconnectNudgeCard(
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

  testWidgets('holdout logs Eligible once per foreground evaluation and sees no card', (tester) async {
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
    expect(eventNames(), [eligibleName, eligibleName]);
    expect(preferences.pendantReconnectNudgeLastShownAt, 0);
    expect(preferences.pendantDropoffSurfaceLastDay, isEmpty);
  });

  testWidgets('a gap under 72 hours is silent', (tester) async {
    seed(gap: const Duration(hours: 71));
    await pumpHome(tester);
    expect(find.byKey(cardKey), findsNothing);
    expect(emitted, isEmpty);
  });

  testWidgets('the persisted cap suppresses treatment on Home', (tester) async {
    seed();
    preferences.pendantReconnectNudgeLastShownAt =
        DateTime.now().subtract(const Duration(days: 29)).millisecondsSinceEpoch;
    await pumpHome(tester);
    expect(find.byKey(cardKey), findsNothing);
    expect(emitted, isEmpty);
  });

  testWidgets('disabled and unreadable flags are silent', (tester) async {
    seed();
    await pumpHome(tester, enabled: false);
    expect(find.byKey(cardKey), findsNothing);
    expect(emitted, isEmpty);
    expect(flagReads, 1);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await pumpHome(tester, unreadable: true);
    expect(find.byKey(cardKey), findsNothing);
    expect(emitted, isEmpty);
    expect(preferences.pendantReconnectNudgeLastShownAt, 0);
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
