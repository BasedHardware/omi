import 'dart:async';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets.dart';
import 'package:omi/pages/conversation_detail/widgets/summarized_apps_sheet.dart';
import 'package:omi/services/experiments/summary_generation_gate.dart';
import 'package:omi/ui/ui.dart';

import '../helpers/summary_fixtures.dart';

/// Records reprocess calls; each waits on [gate] when set.
class _Reprocess {
  final List<String?> appIds = [];
  final List<bool> forcedOmi = [];
  Completer<ReprocessResult>? gate;
  ReprocessResult result = const ReprocessFailed();

  Future<ReprocessResult> call(String id, {String? appId, bool requireSpeakerReceipt = false, bool forceOmi = false}) {
    appIds.add(appId);
    forcedOmi.add(forceOmi);
    return gate?.future ?? Future.value(result);
  }
}

Widget _summaryTab({VoidCallback? onOpenTranscript}) => Scaffold(
      body: CustomScrollView(slivers: [GetAppsWidgets(onOpenTranscript: onOpenTranscript)]),
    );

/// A page with a button that opens the template sheet.
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
    OmiColors.active = OmiPalette.dark;
  });
  tearDown(() {
    SummaryGenerationV2Gate.debugOverride = null;
    OmiColors.active = OmiPalette.light;
  });

  group('empty state', () {
    testWidgets('summarizes with Omi directly, without opening the sheet', (tester) async {
      final reprocess = _Reprocess()..gate = Completer();
      final provider = summaryProvider(summaryConversation(), reprocess: reprocess.call);
      addTearDown(provider.dispose);
      var openedTranscript = 0;
      await tester.pumpWidget(summaryHarness(provider, _summaryTab(onOpenTranscript: () => openedTranscript++)));
      final l10n = summaryL10n(tester);

      expect(find.text(l10n.summaryNotSummarizedYet), findsOneWidget);
      expect(find.text(l10n.summaryEmptyStateBody), findsOneWidget);
      expect(find.text(l10n.summaryUseDifferentTemplate), findsOneWidget);
      expect(find.text(l10n.noSummaryForConversation), findsNothing);
      // The first transcript line, with a way to the whole transcript.
      expect(find.textContaining("after the gas station it's the second light"), findsOneWidget);
      await tester.tap(find.byKey(const Key('summary_read_full_transcript')));
      expect(openedTranscript, 1);

      await tester.tap(find.text(l10n.summaryWithOmi));
      await tester.pump();
      expect(reprocess.appIds, [null]);
      expect(reprocess.forcedOmi, [true], reason: 'a server preferred template must not run in place of Omi');
      expect(find.text(l10n.summarySheetTitle), findsNothing);
      // One progress surface, in the tab.
      expect(find.text(l10n.summarySummarizingWith(l10n.omiAppName)), findsOneWidget);
      reprocess.gate!.complete(ReprocessSuccess(summaryConversation(overview: 'Directions to the cafe.')));
      await tester.pump();
      await tester.pump();
      expect(find.byKey(const Key('summary_generating_state')), findsNothing);
    });

    testWidgets('a saved default template names itself and runs with its app id', (tester) async {
      final reprocess = _Reprocess();
      final provider = summaryProvider(
        summaryConversation(),
        reprocess: reprocess.call,
        catalog: [summaryApp('pg', 'Paul Graham')],
      );
      addTearDown(provider.dispose);
      provider.setDefaultSummaryTemplateAppId('pg');
      await tester.pumpWidget(summaryHarness(provider, _summaryTab()));
      final l10n = summaryL10n(tester);

      expect(find.text(l10n.summaryWithTemplate('Paul Graham')), findsOneWidget);
      expect(find.text(l10n.summaryWithOmi), findsNothing);
      await tester.tap(find.text(l10n.summaryWithTemplate('Paul Graham')));
      await tester.pump();
      expect(reprocess.appIds, ['pg']);
    });

    testWidgets('with the flag off the old prompt stays', (tester) async {
      SummaryGenerationV2Gate.debugOverride = false;
      final provider = summaryProvider(summaryConversation());
      addTearDown(provider.dispose);
      await tester.pumpWidget(summaryHarness(provider, _summaryTab()));
      final l10n = summaryL10n(tester);
      expect(find.text(l10n.noSummaryForConversation), findsOneWidget);
      expect(find.text(l10n.summaryNotSummarizedYet), findsNothing);
    });

    testWidgets('"Use a Different Template" is the one way to the sheet', (tester) async {
      final provider = summaryProvider(summaryConversation());
      addTearDown(provider.dispose);
      await tester.pumpWidget(summaryHarness(provider, _summaryTab()));
      final l10n = summaryL10n(tester);
      await tester.tap(find.text(l10n.summaryUseDifferentTemplate));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      expect(find.text(l10n.summarySheetTitle), findsOneWidget);
      expect(find.byKey(const Key('summary_template_omi')), findsOneWidget);
    });
  });

  group('template sheet', () {
    testWidgets('Omi is there before any template request answers, over two visible skeleton rows', (tester) async {
      final fetches = SummaryTemplateFetches();
      final provider = summaryProvider(summaryConversation(), fetches: fetches);
      addTearDown(provider.dispose);
      await tester.pumpWidget(summaryHarness(provider, _sheetLauncher()));
      await _openSheet(tester);
      final l10n = summaryL10n(tester);

      expect(fetches.enabled, hasLength(1));
      expect(fetches.enabled.single.isCompleted, isFalse);
      expect(find.text(l10n.omiAppName), findsOneWidget);
      expect(find.text(l10n.summaryOmiTemplateSubtitle), findsOneWidget);
      expect(find.byKey(const Key('summary_template_skeleton')), findsNWidgets(2));
      expect(find.text(l10n.summaryBrowseTemplates), findsOneWidget);
      expect(find.text(l10n.summaryCreateYourOwn), findsOneWidget);
      // Suggestions show only when there are some.
      expect(find.text(l10n.summarySuggestedTemplates), findsNothing);
      final skeleton = tester.widget<Container>(find
          .descendant(of: find.byKey(const Key('summary_template_skeleton')).first, matching: find.byType(Container))
          .first);
      final color = (skeleton.decoration as BoxDecoration).color;
      expect(color, isNot(OmiColors.surface1), reason: 'skeletons must not vanish into the sheet surface');
    });

    testWidgets('a failed read says so, keeps Omi usable and retries', (tester) async {
      final fetches = SummaryTemplateFetches();
      final provider = summaryProvider(summaryConversation(), fetches: fetches);
      addTearDown(provider.dispose);
      await tester.pumpWidget(summaryHarness(provider, _sheetLauncher()));
      await _openSheet(tester);
      final l10n = summaryL10n(tester);

      fetches.enabled.single.completeError(StateError('offline'));
      await tester.pump();
      await tester.pump();
      expect(find.text(l10n.summaryTemplatesLoadFailed), findsOneWidget);
      expect(find.text(l10n.summaryNoTemplatesYet), findsNothing);
      expect(find.byKey(const Key('summary_template_omi')), findsOneWidget);

      await tester.tap(find.byKey(const Key('summary_templates_retry')));
      await tester.pump();
      expect(fetches.enabled, hasLength(2));
      fetches.enabled.last.complete([summaryApp('pg', 'Paul Graham')]);
      await tester.pump();
      await tester.pump();
      expect(find.text('Paul Graham'), findsOneWidget);
      expect(find.text(l10n.summaryTemplatesLoadFailed), findsNothing);
    });

    testWidgets('no templates says how to get some', (tester) async {
      final fetches = SummaryTemplateFetches();
      final provider = summaryProvider(summaryConversation(), fetches: fetches);
      addTearDown(provider.dispose);
      await tester.pumpWidget(summaryHarness(provider, _sheetLauncher()));
      await _openSheet(tester);
      fetches.enabled.single.complete([]);
      fetches.suggested.single.complete([]);
      await tester.pump();
      await tester.pump();
      expect(find.text(summaryL10n(tester).summaryNoTemplatesYet), findsOneWidget);
      expect(find.byKey(const Key('summary_template_skeleton')), findsNothing);
    });

    testWidgets('Omi is selected first and Summarize runs it with no app id', (tester) async {
      final fetches = SummaryTemplateFetches();
      final reprocess = _Reprocess()..gate = Completer();
      final provider = summaryProvider(summaryConversation(), fetches: fetches, reprocess: reprocess.call);
      addTearDown(provider.dispose);
      await tester.pumpWidget(summaryHarness(provider, _sheetLauncher()));
      await _openSheet(tester);
      fetches.enabled.single.complete([summaryApp('pg', 'Paul Graham')]);
      await tester.pump();
      await tester.pump();

      expect(
        tester.getSemantics(find.byKey(const Key('summary_template_omi'))).flagsCollection.isSelected,
        ui.Tristate.isTrue,
      );
      await tester.tap(find.byKey(const Key('summary_template_confirm')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      expect(reprocess.appIds, [null]);
      expect(reprocess.forcedOmi, [true]);
      expect(find.byKey(const Key('summary_template_confirm')), findsNothing, reason: 'the sheet closes');
      reprocess.gate!.complete(const ReprocessBusy());
      await tester.pump();
    });

    testWidgets('a tapped template is only selected; Summarize runs it and can save it as the default', (tester) async {
      final fetches = SummaryTemplateFetches();
      final reprocess = _Reprocess()..gate = Completer();
      final provider = summaryProvider(summaryConversation(), fetches: fetches, reprocess: reprocess.call);
      addTearDown(provider.dispose);
      await tester.pumpWidget(summaryHarness(provider, _sheetLauncher()));
      await _openSheet(tester);
      fetches.enabled.single.complete([summaryApp('pg', 'Paul Graham')]);
      await tester.pump();
      await tester.pump();

      await tester.tap(find.text('Paul Graham'));
      await tester.pump();
      expect(reprocess.appIds, isEmpty, reason: 'select first, then confirm');
      await tester.tap(find.byKey(const Key('summary_template_use_for_new')));
      await tester.pump();
      await tester.tap(find.byKey(const Key('summary_template_confirm')));
      await tester.pump();
      expect(reprocess.appIds, ['pg']);
      expect(reprocess.forcedOmi, [false]);
      expect(provider.defaultSummaryTemplateAppId, 'pg');
      expect(SharedPreferencesUtil().lastUsedSummarizationAppId, 'pg');
      reprocess.gate!.complete(const ReprocessBusy());
      await tester.pump();
    });

    testWidgets('Summarize is disabled while a summary is already being written', (tester) async {
      final reprocess = _Reprocess()..gate = Completer();
      final provider = summaryProvider(summaryConversation(), reprocess: reprocess.call);
      addTearDown(provider.dispose);
      unawaited(provider.reprocessConversation());
      await tester.pumpWidget(summaryHarness(provider, _sheetLauncher()));
      await _openSheet(tester);
      final button = tester.widget<OmiButton>(find.byKey(const Key('summary_template_confirm')));
      expect(button.onPressed, isNull);
      reprocess.gate!.complete(const ReprocessBusy());
      await tester.pump();
    });
  });

  group('generating and results', () {
    testWidgets('the tab names the template it is summarizing with', (tester) async {
      final reprocess = _Reprocess()..gate = Completer();
      final provider = summaryProvider(
        summaryConversation(overview: 'Old summary'),
        reprocess: reprocess.call,
        catalog: [summaryApp('pg', 'Paul Graham')],
      );
      addTearDown(provider.dispose);
      await tester.pumpWidget(summaryHarness(provider, _summaryTab()));
      unawaited(provider.reprocessConversation(appId: 'pg'));
      await tester.pump();
      final l10n = summaryL10n(tester);
      expect(find.text(l10n.summarySummarizingWith('Paul Graham')), findsOneWidget);
      expect(find.text('Old summary'), findsNothing, reason: 'the summary being replaced is not shown');
      reprocess.gate!.complete(const ReprocessBusy());
      await tester.pump();
    });

    testWidgets('chips list every summary and switch between them', (tester) async {
      final provider = summaryProvider(
        summaryConversation(
          overview: 'Omi overview of the drive.',
          appResults: [AppResponse('Essay about the drive.', appId: 'pg')],
        ),
        catalog: [summaryApp('pg', 'Paul Graham')],
      );
      addTearDown(provider.dispose);
      await tester.pumpWidget(summaryHarness(provider, _summaryTab()));
      expect(find.byKey(const Key('summary_source_omi')), findsOneWidget);
      expect(find.byKey(const Key('summary_source_app:pg')), findsOneWidget);
      expect(find.byKey(const Key('summary_source_add')), findsOneWidget);
      expect(find.textContaining('Essay about the drive.'), findsOneWidget);

      await tester.tap(find.byKey(const Key('summary_source_omi')));
      await tester.pump();
      expect(find.textContaining('Omi overview of the drive.'), findsOneWidget);
      expect(find.textContaining('Essay about the drive.'), findsNothing);
    });
  });

  group('failure cards', () {
    Future<ConversationDetailProvider> fail(WidgetTester tester, ReprocessResult result, {String? appId}) async {
      final reprocess = _Reprocess()..result = result;
      final provider = summaryProvider(
        summaryConversation(),
        reprocess: reprocess.call,
        catalog: [summaryApp('pg', 'Paul Graham')],
      );
      addTearDown(provider.dispose);
      await tester.pumpWidget(summaryHarness(provider, _summaryTab()));
      await provider.reprocessConversation(appId: appId);
      await tester.pump();
      return provider;
    }

    testWidgets('template failed offers Try Again and Omi instead', (tester) async {
      final provider = await fail(tester, const ReprocessFailed(statusCode: 502), appId: 'pg');
      final l10n = summaryL10n(tester);
      expect(find.text(l10n.summaryTemplateFailedTitle('Paul Graham')), findsOneWidget);
      expect(find.text(l10n.summaryTemplateFailedBody), findsOneWidget);
      expect(find.text(l10n.tryAgain), findsOneWidget);
      await tester.tap(find.text(l10n.summaryWithOmiInstead));
      await tester.pump();
      // The fake fails again; what matters is that the retry asked Omi, not the template.
      expect(provider.summaryFailure!.appId, isNull);
      expect(provider.summaryFailure!.kind, SummaryFailureKind.generic);
    });

    testWidgets('busy offers Check Again, which re-reads the conversation', (tester) async {
      final provider = await fail(tester, const ReprocessBusy());
      final l10n = summaryL10n(tester);
      expect(find.text(l10n.summaryBusyTitle), findsOneWidget);
      expect(find.text(l10n.summaryBusyBody), findsOneWidget);
      await tester.tap(find.text(l10n.summaryCheckAgain));
      await tester.pump();
      await tester.pump();
      expect(provider.summaryFailure, isNull);
      expect(find.text(l10n.summaryBusyTitle), findsNothing);
    });

    testWidgets('the rate limit is acknowledged with OK', (tester) async {
      final provider = await fail(tester, const ReprocessRateLimited());
      final l10n = summaryL10n(tester);
      expect(find.text(l10n.summaryLimitTitle), findsOneWidget);
      expect(find.text(l10n.summaryLimitBody), findsOneWidget);
      await tester.tap(find.text(l10n.ok));
      await tester.pump();
      expect(provider.summaryFailure, isNull);
    });

    testWidgets('any other failure is the generic card', (tester) async {
      await fail(tester, ReprocessSuccess(summaryConversation()));
      final l10n = summaryL10n(tester);
      expect(find.text(l10n.summaryFailedTitle), findsOneWidget);
      expect(find.text(l10n.summaryFailedBody), findsOneWidget);
    });
  });

  testWidgets('a long title ends in an ellipsis at rest instead of being cut off', (tester) async {
    final provider =
        summaryProvider(summaryConversation(title: List.filled(12, 'Turn right at the next one').join(' ')));
    addTearDown(provider.dispose);
    await tester.pumpWidget(summaryHarness(
      provider,
      Scaffold(
        body: ConversationTitleField(
          style: OmiType.title1,
          controller: provider.titleController,
          focusNode: provider.titleFocusNode,
        ),
      ),
    ));
    final text = tester.widget<Text>(find.byKey(const Key('conversation_title_at_rest')));
    expect(text.maxLines, 3);
    expect(text.overflow, TextOverflow.ellipsis);
    await tester.tap(find.byType(ConversationTitleField));
    await tester.pump();
    expect(find.byKey(const Key('conversation_title_at_rest')), findsNothing, reason: 'editing shows the field');
  });
}
