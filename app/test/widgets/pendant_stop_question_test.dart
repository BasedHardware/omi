import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
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
  late bool eligible;
  late bool blocked;
  late PromptQueue queue;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    events = [];
    notes = [];
    absence = PendantAbsence();
    eligible = true;
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
      isCurrentUser: () => true,
      eligibleDays: () => eligible ? 4 : null,
      plan: () => PendantStopQuestionAnsweredPlan.paid,
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
      final field = find.byType(TextField);
      await tester.ensureVisible(field);
      await tester.enterText(field, '  My note.  ');
      await tester.pumpAndSettle();
      final action = find.text(chooseReason ? 'A device problem' : 'Send note');
      await tester.ensureVisible(action);
      await tester.tap(action);
      await tester.pumpAndSettle();

      final reason =
          chooseReason ? PendantStopQuestionAnsweredReason.deviceProblem : PendantStopQuestionAnsweredReason.other;
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

  testWidgets('a reconnect while waiting in the queue suppresses presentation', (tester) async {
    await mount(tester);
    blocked = true;
    enqueue();
    await tester.pumpAndSettle();
    eligible = false;
    blocked = false;
    queue.pump();
    await tester.pumpAndSettle();

    expect(find.text(title), findsNothing);
    expect(events, isEmpty);
    expect(absence.questionShown(uid), isFalse);
  });
}
