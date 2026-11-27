import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posthog_flutter/posthog_flutter.dart' show PostHogMaskWidget;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/home/widgets/pendant_stop_question.dart';
import 'package:omi/services/experiments/pendant_absence.dart';
import 'package:omi/ui/prompts/prompt_queue.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';

void main() {
  const title = 'Why did you stop wearing your pendant?';
  const uid = 'person';
  late List<RegisteredEvent> events;
  late List<(String, PendantStopQuestionAnsweredReason, String, int)> notes;
  late PendantAbsence absence;
  final pendant = BtDevice(id: 'paired', name: 'Omi', type: DeviceType.omi, rssi: 0);
  late DateTime now;
  late bool connected;
  late bool foreground;
  late bool onboarded;
  late bool currentUser;
  late PlanType? plan;
  late bool blocked;
  late PromptQueue queue;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    events = [];
    notes = [];
    now = DateTime(2026, 11, 1);
    absence = PendantAbsence(now: () => now);
    absence.observeAbsence(uid);
    now = now.add(const Duration(days: 4));
    connected = false;
    foreground = true;
    onboarded = true;
    currentUser = true;
    plan = PlanType.plus;
    blocked = false;
  });

  Future<void> mount(WidgetTester tester) async {
    final navigator = GlobalKey<NavigatorState>();
    queue = PromptQueue(contextProvider: () => navigator.currentState?.overlay?.context)..blocked = () => blocked;
    await tester.pumpWidget(MaterialApp(
      navigatorKey: navigator,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: const Scaffold(body: SizedBox()),
    ));
  }

  void enqueue({bool killed = false}) {
    PendantStopQuestion.enqueue(
      queue: queue,
      absence: absence,
      uid: uid,
      isCurrentUser: () => currentUser,
      isOnboarded: () => onboarded,
      isForeground: () => foreground,
      paired: () => pendant,
      connected: () => connected,
      readPlan: () => plan,
      disabled: () async => killed,
      emit: events.add,
      sendNote: (uid, reason, note, days) async {
        notes.add((uid, reason, note, days));
        throw StateError('storage unavailable');
      },
    );
  }

  testWidgets('one tap answers immediately without a note request', (tester) async {
    await mount(tester);
    enqueue();
    await tester.pumpAndSettle();
    await tester.tap(find.text('Charging is a hassle'));
    await tester.pumpAndSettle();

    expect(find.text(title), findsNothing);
    expect(find.text('Thanks for sharing your feedback'), findsOneWidget);
    expect(events.first, isA<PendantStopQuestionShown>());
    final answer = events.last as PendantStopQuestionAnswered;
    expect(answer.reason, PendantStopQuestionAnsweredReason.chargingIsAHassle);
    expect(answer.daysWithoutConnection, 4);
    expect(answer.plan, PendantStopQuestionAnsweredPlan.paid);
    expect(answer.noteProvided, isFalse);
    expect(notes, isEmpty);
  });

  for (final chooseReason in [true, false]) {
    testWidgets('a note can be sent ${chooseReason ? 'with a reason' : 'on its own'}', (tester) async {
      await mount(tester);
      enqueue();
      await tester.pumpAndSettle();
      final field = find.descendant(of: find.byType(PostHogMaskWidget), matching: find.byType(TextField));
      expect(field, findsOneWidget);
      await tester.ensureVisible(field);
      await tester.enterText(field, '  My note.  ');
      await tester.pumpAndSettle();
      final action = find.text(chooseReason ? 'A device problem' : 'Send note');
      await tester.ensureVisible(action);
      await tester.tap(action);
      await tester.pumpAndSettle();

      final reason =
          chooseReason ? PendantStopQuestionAnsweredReason.deviceProblem : PendantStopQuestionAnsweredReason.noteOnly;
      final answer = events.last as PendantStopQuestionAnswered;
      expect(answer.reason, reason);
      expect(answer.noteProvided, isTrue);
      expect(answer.properties.values, isNot(contains('My note.')));
      expect(notes.single, (uid, reason, 'My note.', 4));
      expect(find.text('Thanks for sharing your feedback'), findsOneWidget);
    });
  }

  testWidgets('a dismissal consumes the single opportunity', (tester) async {
    await mount(tester);
    enqueue();
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip(MaterialLocalizations.of(tester.element(find.text(title))).closeButtonTooltip));
    await tester.pumpAndSettle();
    enqueue();
    await tester.pumpAndSettle();

    expect(find.text(title), findsNothing);
    expect(events, [isA<PendantStopQuestionShown>(), isA<PendantStopQuestionDismissed>()]);
  });

  testWidgets('kill switch leaves the opportunity unclaimed', (tester) async {
    await mount(tester);
    enqueue(killed: true);
    await tester.pumpAndSettle();

    expect(find.text(title), findsNothing);
    expect(events, isEmpty);
    expect(absence.questionShown(uid), isFalse);
    expect(absence.surfaceShownToday, isFalse);
  });

  testWidgets('Home entry waits for the current onboarded foreground account and a disconnected pendant',
      (tester) async {
    await mount(tester);
    foreground = false;
    onboarded = false;
    currentUser = false;
    connected = true;
    for (final allowNext in <void Function()>[
      () => foreground = true,
      () => onboarded = true,
      () => currentUser = true,
      () => connected = false,
    ]) {
      enqueue();
      await tester.pumpAndSettle();
      expect(find.text(title), findsNothing);
      expect(absence.questionShown(uid), isFalse);
      allowNext();
    }
    enqueue();
    await tester.pumpAndSettle();
    expect(find.text(title), findsOneWidget);
  });

  for (final (source, expected) in [
    (PlanType.basic, PendantStopQuestionAnsweredPlan.free),
    (null, PendantStopQuestionAnsweredPlan.unknown),
    (PlanType.unknown('future-plan'), PendantStopQuestionAnsweredPlan.unknown),
  ]) {
    testWidgets('Home entry maps $source to $expected', (tester) async {
      await mount(tester);
      plan = source;
      enqueue();
      await tester.pumpAndSettle();
      await tester.tap(find.text('Other'));
      await tester.pumpAndSettle();
      final answer = events.last as PendantStopQuestionAnswered;
      expect(answer.plan, expected);
      expect(answer.reason, PendantStopQuestionAnsweredReason.other);
    });
  }

  testWidgets('a reconnect while waiting in the queue suppresses presentation', (tester) async {
    await mount(tester);
    blocked = true;
    enqueue();
    await tester.pumpAndSettle();
    connected = true;
    blocked = false;
    queue.pump();
    await tester.pumpAndSettle();

    expect(find.text(title), findsNothing);
    expect(events, isEmpty);
    expect(absence.questionShown(uid), isFalse);
  });
}
