import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/merge_action_bar.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/ui/ui.dart';

class _Selection extends ChangeNotifier implements ConversationProvider {
  _Selection(int count) : selectedConversationIds = {for (var i = 0; i < count; i++) '$i'};

  @override
  bool isSelectionModeActive = true;
  @override
  final Set<String> selectedConversationIds;
  @override
  bool get canMerge => selectedConversationIds.length >= 2;

  @override
  void exitSelectionMode() {
    isSelectionModeActive = false;
    selectedConversationIds.clear();
    notifyListeners();
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  for (final scenario in [
    (width: 402.0, scale: 1.0, locale: 'en'),
    (width: 402.0, scale: 3.2, locale: 'en'),
    (width: 320.0, scale: 3.2, locale: 'en'),
    (width: 320.0, scale: 3.2, locale: 'de'),
  ]) {
    testWidgets('selection count and targets fit $scenario', (tester) async {
      tester.view.physicalSize = Size(scenario.width, 874);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      for (final count in [0, 1, 2]) {
        final selection = _Selection(count);
        await tester.pumpWidget(ChangeNotifierProvider<ConversationProvider>.value(
          value: selection,
          child: MaterialApp(
            locale: Locale(scenario.locale),
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            builder: (context, child) => MediaQuery(
              data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(scenario.scale)),
              child: child!,
            ),
            home: const Scaffold(
              body: Stack(children: [Positioned(left: 0, right: 0, bottom: 0, child: MergeActionBar())]),
            ),
          ),
        ));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull, reason: 'No toolbar overflow');

        final context = tester.element(find.byType(MergeActionBar));
        final l10n = AppLocalizations.of(context);
        final labels = [l10n.cancel, l10n.selectedCount(count), l10n.merge];
        for (final label in labels) {
          final text = find.text(label);
          final paragraph = tester.renderObject<RenderParagraph>(text);
          expect(paragraph.didExceedMaxLines, isFalse, reason: 'Full label: $label');
          final rect = tester.getRect(text);
          expect(rect.left, greaterThanOrEqualTo(0));
          expect(rect.right, lessThanOrEqualTo(scenario.width));
        }

        final targets = [
          find.widgetWithText(OmiButton, l10n.cancel),
          find.byKey(const Key('selection_bar_move')),
          find.byKey(const Key('selection_bar_delete')),
          find.byKey(const Key('selection_bar_merge')),
        ];
        final rects = targets.map(tester.getRect).toList();
        for (final rect in rects) {
          expect(rect.width, greaterThanOrEqualTo(44));
          expect(rect.height, greaterThanOrEqualTo(44));
          expect(rect.left, greaterThanOrEqualTo(0));
          expect(rect.right, lessThanOrEqualTo(scenario.width));
          expect(rect.top, greaterThanOrEqualTo(0));
          expect(rect.bottom, lessThanOrEqualTo(874));
        }
        for (var i = 0; i < rects.length; i++) {
          for (var j = i + 1; j < rects.length; j++) {
            expect(rects[i].overlaps(rects[j]), isFalse, reason: 'Separate action targets');
          }
        }
        expect(tester.widget<OmiButton>(targets.last).onPressed != null, count >= 2);
        expect(tester.widget<OmiIconButton>(targets[1]).onPressed != null, count > 0);
        expect(tester.widget<OmiIconButton>(targets[2]).onPressed != null, count > 0);
        await tester.tap(targets.first);
        await tester.pump();
        expect(selection.isSelectionModeActive, isFalse);
        expect(selection.selectedConversationIds, isEmpty);
        // Keep the outgoing surface until its slide finishes, then remove its paint/semantics.
        expect(find.byKey(const Key('selection_bar_merge')), findsOneWidget);
        await tester.pumpAndSettle();
        expect(find.byKey(const Key('selection_bar_merge')), findsNothing);
        await tester.pumpWidget(const SizedBox.shrink());
        selection.dispose();
      }
    });
  }
}
