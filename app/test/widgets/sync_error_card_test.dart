import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/sync_error_card.dart';

/// Regression coverage for the truncated-error bug: the sync error banner used
/// to clamp its message to `maxLines: 2` + ellipsis, so a long recovery message
/// ("…Pendant's storage is full and i…") was cut off — worst at large iOS
/// accessibility text scales, where it hid the instruction the user needs to
/// recover. The banner must reflow the full message.
const _longMessage = "Your Pendant's storage is full and it's still in recording mode, so its stored audio can't be "
    "transferred. Press the Pendant's button to stop recording, then sync again.";

Future<void> _pump(WidgetTester tester, {required double textScale}) async {
  await tester.pumpWidget(
    MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(
        body: MediaQuery(
          data: MediaQueryData(textScaler: TextScaler.linear(textScale)),
          // A realistic phone content width so a long message genuinely wraps.
          child: Center(
            child: SizedBox(
              width: 360,
              child: SyncErrorCard(message: _longMessage, onRetry: () {}),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('error message is never clamped to a fixed line count', (tester) async {
    await _pump(tester, textScale: 1.0);

    final text = tester.widget<Text>(find.text(_longMessage));
    expect(text.maxLines, isNull, reason: 'the recovery message must reflow, not clamp to N lines');
    expect(text.overflow, isNot(TextOverflow.ellipsis), reason: 'must not ellipsize the recovery instruction');
  });

  testWidgets('full message stays visible and does not overflow at a large accessibility scale', (tester) async {
    await _pump(tester, textScale: 2.0);

    // The full message widget is present (wrapped across many lines, not cut).
    expect(find.text(_longMessage), findsOneWidget);
    // A clamped/oversized Row would throw a RenderFlex overflow during layout.
    expect(tester.takeException(), isNull);
  });
}
