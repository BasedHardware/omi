import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/empty_conversations.dart';
import 'package:omi/pages/conversations/widgets/offline_sync_storage_sheet.dart';
import 'package:omi/ui/ui.dart';

double contrast(Color foreground, Color background) {
  final opaque = Color.alphaBlend(foreground, background);
  final a = opaque.computeLuminance();
  final b = background.computeLuminance();
  return (math.max(a, b) + .05) / (math.min(a, b) + .05);
}

void main() {
  for (final brightness in Brightness.values) {
    testWidgets('Offline Sync storage labels are readable in $brightness', (tester) async {
      final previous = OmiColors.active;
      OmiColors.active = OmiColors.forBrightness(brightness);
      addTearDown(() => OmiColors.active = previous);
      await tester.pumpWidget(MaterialApp(
        theme: buildOmiTheme(brightness: brightness),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Scaffold(
            body: OfflineSyncStorageSheet(
          syncedCount: 0,
          pendingCount: 0,
          totalCount: 0,
          onClearSynced: () => fail('zero count must not offer clearing'),
          onClearPending: () => fail('zero count must not offer clearing'),
          onClearAll: () => fail('zero total must not offer clearing'),
        )),
      ));
      await tester.pumpAndSettle();
      for (final label in ['Synced', 'Pending', 'Conversations created', 'Not yet synced to your phone']) {
        final text = find.text(label);
        expect(text, findsOneWidget);
        final cards = tester
            .widgetList<Container>(find.ancestor(of: text, matching: find.byType(Container)))
            .where((w) => w.decoration is BoxDecoration && (w.decoration! as BoxDecoration).color != null);
        final background = (cards.first.decoration! as BoxDecoration).color!;
        final foreground = tester.widget<Text>(text).style!.color!;
        expect(contrast(foreground, background), greaterThanOrEqualTo(4.5), reason: '$label in $brightness');
      }
      final count = find.text('0');
      expect(count, findsNWidgets(2));
      for (final element in count.evaluate()) {
        final text = element.widget as Text;
        final badge = element.findAncestorWidgetOfExactType<Container>()!;
        final fill = (badge.decoration! as BoxDecoration).color!;
        final background = Color.alphaBlend(fill, OmiColors.surface2);
        expect(contrast(text.style!.color!, background), greaterThanOrEqualTo(4.5));
      }
      expect(find.text('Clear'), findsNothing);
      expect(find.text('Clear All'), findsNothing);
      expect(tester.takeException(), isNull);
    });
    testWidgets('Home empty state stays visible in $brightness', (tester) async {
      final previous = OmiColors.active;
      OmiColors.active = OmiColors.forBrightness(brightness);
      addTearDown(() => OmiColors.active = previous);
      await tester.pumpWidget(MaterialApp(
        theme: buildOmiTheme(brightness: brightness),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: const Scaffold(body: Center(child: NoConversationsHero())),
      ));
      await tester.pumpAndSettle();
      final title = find.text('No conversations yet');
      expect(title.hitTestable(), findsOneWidget);
      expect(contrast(tester.widget<Text>(title).style!.color!, OmiColors.surface0), greaterThanOrEqualTo(4.5));
      expect(find.byIcon(Icons.forum_rounded), findsOneWidget);
    });
  }
  testWidgets('nonzero counts retain category and clear-all callbacks', (tester) async {
    final calls = <String>[];
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: const [Locale('en')],
      home: Scaffold(
          body: OfflineSyncStorageSheet(
        syncedCount: 2,
        pendingCount: 3,
        totalCount: 5,
        onClearSynced: () => calls.add('synced'),
        onClearPending: () => calls.add('pending'),
        onClearAll: () => calls.add('all'),
      )),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Clear').first);
    await tester.tap(find.text('Clear').last);
    await tester.tap(find.text('Clear All'));
    expect(calls, ['synced', 'pending', 'all']);
  });
}
