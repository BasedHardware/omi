import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversation_detail/widgets/summarized_apps_sheet.dart';
import 'package:omi/services/experiments/summary_generation_gate.dart';
import 'package:omi/ui/ui.dart';

import '../helpers/summary_fixtures.dart';

/// Records reprocess calls; the outcome is always the typed failure so the sheet's flow is the
/// thing under test, not the result handling.
class _RecordingReprocess {
  final List<String?> appIds = [];

  Future<ReprocessResult> call(String id, {String? appId, bool requireSpeakerReceipt = false, bool forceOmi = false}) {
    appIds.add(appId);
    return Future.value(const ReprocessFailed());
  }
}

Widget _sheetLauncher() => Scaffold(
      body: Builder(
        builder: (context) => Center(
          child: TextButton(onPressed: () => showSummarizedAppsSheet(context), child: const Text('open')),
        ),
      ),
    );

Future<void> _openSheet(WidgetTester tester) async {
  await tester.tap(find.text('open'));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 500));
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SummaryGenerationV2Gate.debugOverride = true;
  });
  tearDown(() {
    SummaryGenerationV2Gate.debugOverride = null;
  });

  group('template sheet selection', () {
    testWidgets('an inherited selection the settled lists cannot back falls back to Omi', (tester) async {
      // The displayed summary came from a template that has since been deleted: no enabled or
      // suggested row carries it, and the durable catalog does not know it either.
      final fetches = SummaryTemplateFetches();
      final reprocess = _RecordingReprocess();
      final provider = summaryProvider(
        summaryConversation(overview: 'Template wrote this', appResults: [AppResponse('Gone template', appId: 'gone')]),
        reprocess: reprocess.call,
        fetches: fetches,
      );
      addTearDown(provider.dispose);

      await tester.pumpWidget(summaryHarness(provider, _sheetLauncher()));
      await _openSheet(tester);
      // Lists still loading: the selection is not proven yet, so Summarize waits.
      final button = tester.widget<OmiButton>(find.byKey(const Key('summary_template_confirm')));
      expect(button.onPressed, isNull);

      fetches.enabled.single.complete(const []);
      fetches.suggested.single.complete(const []);
      await tester.pump();
      await tester.pump();

      // Nothing backs the inherited id, so the sheet shows Omi selected and Summarize runs Omi.
      expect(find.byKey(const Key('summary_template_app_gone')), findsNothing);
      final settled = tester.widget<OmiButton>(find.byKey(const Key('summary_template_confirm')));
      expect(settled.onPressed, isNotNull);
      await tester.tap(find.byKey(const Key('summary_template_confirm')));
      await tester.pump();
      expect(reprocess.appIds, [null]);
    });

    testWidgets('an inherited selection the lists back is kept and runs with its app id', (tester) async {
      final fetches = SummaryTemplateFetches();
      final reprocess = _RecordingReprocess();
      final provider = summaryProvider(
        summaryConversation(overview: 'Old', appResults: [AppResponse('Template text', appId: 'pg')]),
        reprocess: reprocess.call,
        fetches: fetches,
        catalog: [summaryApp('pg', 'Paul Graham')],
      );
      addTearDown(provider.dispose);

      await tester.pumpWidget(summaryHarness(provider, _sheetLauncher()));
      await _openSheet(tester);

      fetches.enabled.single.complete([summaryApp('pg', 'Paul Graham')]);
      fetches.suggested.single.complete(const []);
      await tester.pump();
      await tester.pump();

      final button = tester.widget<OmiButton>(find.byKey(const Key('summary_template_confirm')));
      expect(button.onPressed, isNotNull, reason: 'the offered template row backs the selection');
      await tester.tap(find.byKey(const Key('summary_template_confirm')));
      await tester.pump();
      expect(reprocess.appIds, ['pg']);
    });

    testWidgets('a selection backed by a suggested row survives the load and installs-then-runs', (tester) async {
      final fetches = SummaryTemplateFetches();
      final reprocess = _RecordingReprocess();
      final provider = summaryProvider(
        summaryConversation(overview: 'Old', appResults: [AppResponse('Template text', appId: 'pg')]),
        reprocess: reprocess.call,
        fetches: fetches,
        catalog: [summaryApp('pg', 'Paul Graham')],
      );
      addTearDown(provider.dispose);

      await tester.pumpWidget(summaryHarness(provider, _sheetLauncher()));
      await _openSheet(tester);

      // Not installed, but offered as a suggestion: the sheet keeps it selected and Summarize
      // first enables it, then runs the reprocess with its id.
      fetches.enabled.single.complete(const []);
      fetches.suggested.single.complete([summaryApp('pg', 'Paul Graham')]);
      await tester.pump();
      await tester.pump();

      final button = tester.widget<OmiButton>(find.byKey(const Key('summary_template_confirm')));
      expect(button.onPressed, isNotNull);
    });
  });
}
