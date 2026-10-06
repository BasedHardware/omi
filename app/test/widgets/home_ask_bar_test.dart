/// Home's Ask anything bar: one glass bar beside the record button.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/widgets/home_bottom_bar.dart';

void main() {
  testWidgets('Ask anything opens chat to type, and its mic opens it listening, on one glass bar', (tester) async {
    var typed = 0, voiced = 0;
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(
        body: OmiCanvas(
          child: Center(child: HomeAskOmiButton(onTap: () => typed++, onVoice: () => voiced++)),
        ),
      ),
    ));
    final label = tester.widget<Text>(find.text('Ask anything'));
    expect(label.style!.fontSize, OmiType.callout.fontSize);
    expect(label.style!.fontWeight, FontWeight.w500, reason: 'medium, as in Omi v8');
    expect(label.maxLines, 1);
    expect(find.descendant(of: find.byType(HomeAskOmiButton), matching: find.byType(OmiGlass)), findsOneWidget);
    final mic = find.descendant(of: find.byType(HomeAskOmiButton), matching: find.byType(OmiLineIcon));
    expect(tester.widget<OmiLineIcon>(mic).glyph, OmiLineGlyph.voice, reason: 'a plain mic, no inner detail');

    await tester.tap(find.text('Ask anything'));
    await tester.tap(find.byKey(const ValueKey('home_ask_omi_voice')));
    expect((typed, voiced), (1, 1));

    // A near miss at the rounded end still talks: the mic owns the bar's full height there.
    final bar = tester.getRect(find.byType(HomeAskOmiButton));
    await tester.tapAt(Offset(bar.right - 3, bar.top + 3));
    expect(voiced, 2);
  });
}
