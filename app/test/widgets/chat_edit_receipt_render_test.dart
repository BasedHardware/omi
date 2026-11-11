import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api/chat_receipts.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/chat_content_block.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/chat/widgets/content_blocks/edit_receipt_block.dart';
import 'package:omi/ui/ui.dart';
import '../helpers/sfpro_font_fixtures.dart';

/// Renders every receipt state on one iPhone-width screen. With
/// `--dart-define=OMI_EDIT_RECEIPT_UI_EVIDENCE_DIR=<dir>` it also loads the
/// bundled product fonts and writes PNG evidence there.
void main() {
  EditReceiptContentBlock block(String id, String kind, String action, String summary,
      {bool undoable = true, String? undoneAt}) {
    return ChatContentBlock.tryDecode({
      'type': 'editReceipt',
      'id': id,
      'receiptId': 'r-$id',
      'targetKind': kind,
      'action': action,
      'targetId': 't-$id',
      'summary': summary,
      'undoable': undoable,
      'undoneAt': undoneAt,
    }) as EditReceiptContentBlock;
  }

  for (final brightness in Brightness.values) {
    testWidgets('edit receipts render in the ${brightness.name} chat', (tester) async {
      EditReceiptBlock.resetSessionState();
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      tester.view.physicalSize = const Size(393, 760);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final previousPalette = OmiColors.active;
      OmiColors.active = brightness == Brightness.dark ? OmiPalette.dark : OmiPalette.light;
      addTearDown(() => OmiColors.active = previousPalette);
      final base = buildOmiTheme(brightness: brightness);
      final theme = base.copyWith(
        platform: TargetPlatform.iOS,
        textTheme: base.textTheme.apply(fontFamily: 'SF Pro Display'),
      );

      const evidence = String.fromEnvironment('OMI_EDIT_RECEIPT_UI_EVIDENCE_DIR');
      if (evidence.isNotEmpty) {
        await tester.runAsync(() async {
          final fonts = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List<dynamic>;
          for (final entry in fonts) {
            final loader = FontLoader(entry['family'] as String);
            for (final font in entry['fonts'] as List<dynamic>) {
              loader.addFont(rootBundle.load(font['asset'] as String));
            }
            await loader.load();
          }
          // Components that name a system family (iOS buttons) otherwise draw as boxes.
          for (final family in const [
            'Roboto',
            'CupertinoSystemText',
            'CupertinoSystemDisplay',
            '.SF UI Text',
            '.SF UI Display',
            'SF Pro Display',
            'FlutterTest'
          ]) {
            final loader = FontLoader(family)
              ..addFont(sfProFont('SFPRODISPLAYMEDIUM.OTF'))
              ..addFont(sfProFont('SFPRODISPLAYREGULAR.OTF'));
            await loader.load();
          }
        });
      }

      Future<ApiResult<EditReceiptUndoResult>> undo(String _) async =>
          const ApiSuccess(EditReceiptUndoResult(undoneAt: '2026-10-11T10:00:00Z'));
      Future<bool> open(BuildContext _, EditReceiptContentBlock __) async => true;
      Widget receipt(EditReceiptContentBlock b) => Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: EditReceiptBlock(block: b, undo: undo, openTarget: open),
          );

      const boundaryKey = ValueKey('edit-receipt-evidence');
      await tester.pumpWidget(RepaintBoundary(
        key: boundaryKey,
        child: MaterialApp(
          locale: const Locale('en'),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          theme: theme,
          debugShowCheckedModeBanner: false,
          home: Scaffold(
            body: SafeArea(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Done. I renamed the task and cleaned up two memories.', style: theme.textTheme.bodyLarge),
                    const SizedBox(height: 12),
                    receipt(block('1', 'task', 'renamed', 'Renamed the task to "Send the Q4 deck to Priya"')),
                    receipt(block('2', 'task', 'completed', 'Marked "Book flights to Lisbon" done')),
                    receipt(block('3', 'memory', 'deleted', 'Deleted the memory "Prefers window seats"',
                        undoneAt: '2026-10-11T09:00:00Z')),
                    receipt(block('4', 'conversation', 'renamed', 'Renamed the conversation to "Pricing sync"')),
                    receipt(block('5', 'person', 'renamed', 'Renamed Speaker 2 to Priya', undoable: false)),
                    receipt(block('6', 'calendar_event', 'moved', 'Moved the standup to 10:30')),
                  ],
                ),
              ),
            ),
          ),
        ),
      ));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.text('Undo'), findsNWidgets(4));
      expect(find.text('Undone'), findsOneWidget);

      if (evidence.isNotEmpty) {
        Future<void> capture(String name) => tester.runAsync(() async {
              final boundary = tester.renderObject<RenderRepaintBoundary>(find.byKey(boundaryKey));
              final image = await boundary.toImage(pixelRatio: 3);
              final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
              final dir = await Directory(evidence).create(recursive: true);
              await File('${dir.path}/$name').writeAsBytes(bytes!.buffer.asUint8List());
              image.dispose();
            });
        await capture('edit-receipts-${brightness.name}.png');
        // After tapping Undo on the first receipt.
        await tester.tap(find.byKey(const Key('chat-block-editReceipt-1-undo')));
        await tester.pumpAndSettle();
        expect(find.text('Undone'), findsNWidgets(2));
        await capture('edit-receipts-${brightness.name}-after-undo.png');
      }
      await tester.pumpWidget(const SizedBox.shrink());
      debugDefaultTargetPlatformOverride = null;
    });
  }
}
