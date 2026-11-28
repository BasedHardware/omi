// ux-contract §17 Outcomes, audit 2026-11-19: what the reader sees after a tap. One case per fix
// that lives in a page: D1, G2, G4, A1, P4, P5, D2, D5 and C2.
import 'dart:async';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/http/api/goals.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/action_items/widgets/goal_form_sheet.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversations/widgets/goals_widget.dart';
import 'package:omi/pages/episodes/finish_capture.dart';
import 'package:omi/pages/episodes/finished_capture_page.dart';
import 'package:omi/pages/home/firmware_mixin.dart';
import 'package:omi/pages/home/firmware_update.dart';
import 'package:omi/pages/onboarding/ai_consent_widget.dart';
import 'package:omi/pages/settings/notifications_settings_page.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/ui/ui.dart';

Widget _app(Widget home, {List<ChangeNotifierProvider> providers = const []}) {
  final app = MaterialApp(
    navigatorKey: globalNavigatorKey,
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: const [Locale('en')],
    home: home,
  );
  return providers.isEmpty ? app : MultiProvider(providers: providers, child: app);
}

Goal _goal(String id, String title) => Goal(
      id: id,
      title: title,
      goalType: 'numeric',
      targetValue: 10,
      currentValue: 3,
      minValue: 0,
      maxValue: 10,
      isActive: true,
      createdAt: DateTime.utc(2026, 9, 1),
      updatedAt: DateTime.utc(2026, 9, 1),
    );

class _HeldProgress extends GoalWrites {
  _HeldProgress();

  final saves = <(double, Completer<Goal?>)>[];

  @override
  Future<Goal?> progress(String goalId, double currentValue) {
    final answer = Completer<Goal?>();
    saves.add((currentValue, answer));
    return answer.future;
  }
}

class _DeleteFails extends GoalWrites {
  const _DeleteFails();

  @override
  Future<bool> delete(String goalId) async => false;
}

class _Device extends ChangeNotifier implements DeviceProvider {
  @override
  int get batteryLevel => 90;

  @override
  int get displayBatteryLevel => batteryLevel;

  @override
  bool get batteryReadingStuck => false;

  @override
  bool get isCharging => false;

  @override
  void setOnFirmwareUpdatePage(bool value) {}

  @override
  void resetFirmwareUpdateState() {}

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

class _Api extends NotificationSettingsApi {
  _Api({this.loads = true, this.saves = true});

  bool loads;
  bool saves;
  final List<bool?> enabledWrites = [];

  @override
  Future<DailySummarySettings?> dailySummary() async => loads ? DailySummarySettings(enabled: true, hour: 22) : null;

  @override
  Future<MentorNotificationSettings?> mentor() async => loads ? MentorNotificationSettings(frequency: 0) : null;

  @override
  Future<bool> setDailySummary({bool? enabled, int? hour}) async {
    enabledWrites.add(enabled);
    return saves;
  }

  @override
  Future<bool> setMentorFrequency(int frequency) async => saves;
}

class _GoogleCancels extends AuthenticationProvider {
  _GoogleCancels() : super(initializeListeners: false);

  @override
  bool get googleUsesNativeSheet => true;

  @override
  Future<UserCredential?> requestGoogleCredential() async => null;
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'outcome-user'});
    await SharedPreferencesUtil.init();
  });

  testWidgets('D1: a firmware check with no answer is an error with Try Again, never "up to date"', (tester) async {
    var answer = false;
    debugLatestFirmwareLookup = ({
      required deviceModelNumber,
      required firmwareRevision,
      required hardwareRevision,
      required manufacturerName,
      serialNumber,
    }) async =>
        answer ? {'version': '3.0.0', 'min_version': '1.0.0', 'draft': false} : null;
    addTearDown(() => debugLatestFirmwareLookup = null);
    final device = BtDevice(
      id: 'd',
      name: 'Omi',
      type: DeviceType.omi,
      rssi: -40,
      modelNumber: 'Omi DevKit 2',
      firmwareRevision: '3.0.0',
      hardwareRevision: '1',
      manufacturerName: 'Based Hardware',
    );
    await tester.pumpWidget(_app(
      FirmwareUpdate(device: device),
      providers: [ChangeNotifierProvider<DeviceProvider>.value(value: _Device())],
    ));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('firmware_check_failed')), findsOneWidget);
    expect(find.text("Couldn't check for updates."), findsOneWidget);
    expect(find.text('Your device is up to date'), findsNothing);

    answer = true;
    await tester.tap(find.text('Try Again'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('firmware_check_failed')), findsNothing);
    await tester.pumpWidget(const SizedBox());
    await tester.pump();
  });

  testWidgets('G2: a goal save that fails keeps the sheet open with what was typed', (tester) async {
    var ok = false;
    await tester.pumpWidget(_app(Scaffold(
      body: Builder(
        builder: (context) => TextButton(
          onPressed: () => showGoalFormSheet(
            context,
            goal: _goal('a', 'Read books'),
            onSave: (title, current, target, emoji) async => ok,
          ),
          child: const Text('open'),
        ),
      ),
    )));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Read books'), 'Read 12 books');
    await tester.pump();

    await tester.tap(find.byKey(const Key('goal_save_button')));
    await tester.pumpAndSettle();
    expect(find.text('Edit Goal'), findsOneWidget, reason: 'the goal is not lost');
    expect(find.text('Read 12 books'), findsOneWidget);
    expect(find.text("Couldn't save your goal."), findsOneWidget);
    expect(find.byKey(const Key('goal_save_failed')), findsOneWidget,
        reason: 'said inside the sheet; a page toast would sit under the modal route');
    expect(find.byType(SnackBar), findsNothing);

    ok = true;
    await tester.tap(find.byKey(const Key('goal_save_button')));
    await tester.pumpAndSettle();
    expect(find.text('Edit Goal'), findsNothing);
  });

  testWidgets('G4: a goal delete that fails on the server says so when the goal comes back', (tester) async {
    final provider = GoalsProvider(goalsFetcher: () async => [_goal('a', 'Read')], writes: const _DeleteFails());
    addTearDown(provider.dispose);
    await provider.loadGoals();
    await tester.pumpWidget(_app(Scaffold(
      body: Builder(
        builder: (context) => TextButton(
          onPressed: () => deleteGoalWithUndo(context, provider, provider.goals.single),
          child: const Text('delete'),
        ),
      ),
    )));
    await tester.tap(find.text('delete'));
    await tester.pump();
    expect(provider.goals, isEmpty, reason: 'staged behind Undo');
    // Let the Undo toast run out (its timer starts once its entrance animation ends).
    for (var i = 0; i < 8; i++) {
      await tester.pump(const Duration(seconds: 1));
    }
    await tester.pump(const Duration(milliseconds: 500));
    expect(provider.goals.map((g) => g.id), ['a']);
    expect(find.text("Couldn't delete. Goal restored."), findsOneWidget);
    await tester.pump(const Duration(seconds: 9));
  });

  testWidgets('A1: a dirty full-page form asks before back discards it', (tester) async {
    var dirty = true;
    await tester.pumpWidget(_app(Builder(
      builder: (context) => TextButton(
        onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(
          builder: (_) => StatefulBuilder(
            builder: (context, setState) => OmiUnsavedChangesGuard(
              isDirty: dirty,
              child: const Scaffold(appBar: null, body: Text('form')),
            ),
          ),
        )),
        child: const Text('open'),
      ),
    )));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    final navigator = tester.state<NavigatorState>(find.byType(Navigator).first);
    await navigator.maybePop();
    await tester.pumpAndSettle();
    expect(find.text('Discard Changes?'), findsOneWidget);
    await tester.tap(find.text('Keep Editing'));
    await tester.pumpAndSettle();
    expect(find.text('form'), findsOneWidget);

    await navigator.maybePop();
    await tester.pumpAndSettle();
    await tester.tap(find.text('Discard'));
    await tester.pumpAndSettle();
    expect(find.text('form'), findsNothing);

    dirty = false;
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    await navigator.maybePop();
    await tester.pumpAndSettle();
    expect(find.text('Discard Changes?'), findsNothing, reason: 'a clean form just closes');
    expect(find.text('form'), findsNothing);
  });

  testWidgets('P4: settings that could not be read show an error, not defaults', (tester) async {
    final api = _Api(loads: false);
    await tester.pumpWidget(_app(NotificationsSettingsPage(api: api, showLiveActivity: false)));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('notification_settings_load_failed')), findsOneWidget);
    expect(find.byType(Switch), findsNothing);

    api.loads = true;
    await tester.tap(find.text('Try Again'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('notification_settings_load_failed')), findsNothing);
  });

  testWidgets('P5: a settings change the server refused comes back with a message', (tester) async {
    final api = _Api(saves: false);
    await tester.pumpWidget(_app(NotificationsSettingsPage(api: api, showLiveActivity: false)));
    await tester.pumpAndSettle();
    final toggle = find.byType(Switch).first;
    expect(tester.widget<Switch>(toggle).value, isTrue);

    await tester.tap(toggle);
    await tester.pumpAndSettle();
    expect(api.enabledWrites, [false]);
    expect(tester.widget<Switch>(toggle).value, isTrue, reason: 'rolled back');
    expect(find.text("Couldn't save that change."), findsOneWidget);
    expect(find.text('Try Again'), findsOneWidget);
    await tester.pump(const Duration(seconds: 9));
  });

  testWidgets('D2: closing Google\'s sheet says nothing, like cancelling Apple', (tester) async {
    await tester.pumpWidget(_app(const Scaffold(body: SizedBox())));
    final provider = _GoogleCancels();
    addTearDown(provider.dispose);
    await provider.onGoogleSignIn(() {});
    await tester.pumpAndSettle();
    expect(find.byType(SnackBar), findsNothing);
    expect(provider.loading, isFalse);
  });

  testWidgets('D5: Use a Different Account asks before it signs out and resets the phone', (tester) async {
    var signedOut = 0;
    final auth = AuthenticationProvider(initializeListeners: false);
    addTearDown(auth.dispose);
    await tester.pumpWidget(_app(
      Scaffold(body: AiConsentWidget(onAgree: () {}, onUseDifferentAccount: () => signedOut++)),
      providers: [ChangeNotifierProvider<AuthenticationProvider>.value(value: auth)],
    ));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const Key('ai_consent_use_different_account')));
    await tester.tap(find.byKey(const Key('ai_consent_use_different_account')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 600));
    expect(signedOut, 0, reason: 'one tap no longer signs out and wipes preferences');
    expect(find.text('Sign Out?'), findsOneWidget);
    await tester.tap(find.text('Sign Out').last);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 600));
    expect(signedOut, 1);
  });

  testWidgets('C2: the record button with the mic blocked offers Open Settings', (tester) async {
    await tester.pumpWidget(_app(Scaffold(
      body: Builder(
        builder: (context) => TextButton(onPressed: () => showMicBlocked(context), child: const Text('record')),
      ),
    )));
    await tester.tap(find.text('record'));
    await tester.pump();
    expect(find.text('Allow the microphone to record.'), findsOneWidget);
    expect(find.text('Open Settings'), findsOneWidget);
    expect(find.textContaining('Something went wrong'), findsNothing);
    await tester.pump(const Duration(seconds: 9));
  });

  testWidgets('C6: the processing page ends on its first read when the recording was discarded', (tester) async {
    final discarded = ServerConversation.fromJson({
      'id': 'rec-1',
      'created_at': '2026-11-19T10:00:00Z',
      'started_at': '2026-11-19T10:00:00Z',
      'finished_at': '2026-11-19T10:00:04Z',
      'status': 'completed',
      'discarded': true,
      'structured': {'title': '', 'overview': '', 'emoji': ''},
      'transcript_segments': const [],
    });
    await tester.pumpWidget(_app(FinishedCapturePage(recordingId: 'rec-1', fetch: () async => [discarded])));
    await tester.pump();
    await tester.pump();
    expect(find.byKey(const Key('finished_capture_discarded')), findsOneWidget, reason: 'no 20-minute wait');
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('P5: a late failure of an older change never rolls back a newer one', (tester) async {
    await tester.pumpWidget(_app(const Scaffold(body: SizedBox())));
    final context = tester.element(find.byType(SizedBox));
    var shown = 0;
    final first = Completer<bool>();
    final older = applyOmiSetting<int>(context,
        setting: 'freq', previous: 0, next: 1, show: (v) => shown = v, save: (_) => first.future);
    final newer = applyOmiSetting<int>(context,
        setting: 'freq', previous: 1, next: 2, show: (v) => shown = v, save: (_) async => true);
    expect(await newer, isTrue);
    first.complete(false);
    expect(await older, isFalse);
    await tester.pump();
    expect(shown, 2, reason: 'the newer choice stays');
    expect(find.text("Couldn't save that change."), findsNothing);
  });

  testWidgets('G1: a late failed save of an older drag neither resets the newer drag nor offers its retry',
      (tester) async {
    final writes = _HeldProgress();
    final goals = GoalsProvider(goalsFetcher: () async => [_goal('a', 'Read')], writes: writes);
    addTearDown(goals.dispose);
    await goals.loadGoals();
    await tester.pumpWidget(_app(const Scaffold(body: SingleChildScrollView(child: GoalsWidget())),
        providers: [ChangeNotifierProvider<GoalsProvider>.value(value: goals)]));
    await tester.pump();
    final slider = find.byType(Slider);
    expect(slider, findsOneWidget);
    await tester.drag(slider, const Offset(60, 0));
    await tester.pump();
    expect(writes.saves, hasLength(1));
    await tester.drag(slider, const Offset(-120, 0));
    await tester.pump();
    expect(writes.saves, hasLength(2));
    final newer = writes.saves[1].$1;
    expect(newer, isNot(writes.saves[0].$1));
    writes.saves[0].$2.complete(null);
    await tester.pump();
    expect(tester.widget<Slider>(slider).value, newer, reason: 'the older answer must not move the newer thumb');
    expect(find.text("Couldn't save your goal."), findsNothing, reason: 'no retry that would undo the newer choice');
    writes.saves[1].$2.complete(Goal(
        id: 'a',
        title: 'Read',
        goalType: 'numeric',
        targetValue: 10,
        currentValue: newer,
        minValue: 0,
        maxValue: 10,
        isActive: true,
        createdAt: DateTime.utc(2026, 9, 1),
        updatedAt: DateTime.utc(2026, 9, 1)));
    await tester.pump(const Duration(seconds: 5));
  });

  testWidgets('P5: two overlapping failed changes show what the server still has', (tester) async {
    await tester.pumpWidget(_app(const Scaffold(body: SizedBox())));
    final context = tester.element(find.byType(SizedBox));
    var shown = true;
    final first = Completer<bool>();
    final second = Completer<bool>();
    final off = applyOmiSetting<bool>(context,
        setting: 'daily', previous: true, next: false, show: (v) => shown = v, save: (_) => first.future);
    final on = applyOmiSetting<bool>(context,
        setting: 'daily', previous: false, next: true, show: (v) => shown = v, save: (_) => second.future);
    first.complete(false);
    expect(await off, isFalse);
    second.complete(false);
    expect(await on, isFalse);
    await tester.pump();
    expect(shown, isTrue, reason: 'neither write saved, so the server still has it on');
    await tester.pump(const Duration(seconds: 5));
  });
}
