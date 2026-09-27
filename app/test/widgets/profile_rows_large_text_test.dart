import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/ui/ui.dart';

// Regression for #12898, carried over from the retired ProfileSettingsTile: the Profile page's
// "Transcribe Later" and "Voice response" rows must lay out without overflow at narrow widths and
// large text scales. Profile now draws them with OmiSettingsRow (Transcribe Later is an inline
// switch, chat-apps-settings #6), so the regression is pinned on those rows.

const double _narrowWidth = 320;

Widget _app(Widget child, {double textScale = 1.0, double width = _narrowWidth}) {
  return MaterialApp(
    localizationsDelegates: const [
      AppLocalizations.delegate,
      GlobalMaterialLocalizations.delegate,
      GlobalWidgetsLocalizations.delegate,
      GlobalCupertinoLocalizations.delegate,
    ],
    supportedLocales: AppLocalizations.supportedLocales,
    home: MediaQuery(
      data: MediaQueryData(textScaler: TextScaler.linear(textScale)),
      child: Scaffold(
        body: Align(
          alignment: Alignment.topLeft,
          child: SizedBox(width: width, child: OmiSettingsGroup(children: [child])),
        ),
      ),
    ),
  );
}

void main() {
  testWidgets('an inline switch row with a subtitle fits a narrow row at 1.6x text', (tester) async {
    var value = false;
    await tester.pumpWidget(
      _app(
        StatefulBuilder(
          builder: (context, setState) => OmiSettingsRow.toggle(
            leading: const Icon(Icons.save),
            title: 'Transcribe Later',
            subtitle: 'Record now and transcribe when you are back online',
            value: value,
            onChanged: (v) => setState(() => value = v),
          ),
        ),
        textScale: 1.6,
      ),
    );
    await tester.pump();

    expect(tester.takeException(), isNull);
    expect(find.text('Transcribe Later'), findsOneWidget);

    // The whole row is the target: tapping the title flips the switch.
    await tester.tap(find.text('Transcribe Later'));
    await tester.pump();
    expect(value, isTrue);
  });

  testWidgets('a long value is ellipsized and never pushes the title off the row', (tester) async {
    const width = 360.0;
    await tester.pumpWidget(
      _app(
        OmiSettingsRow(
          leading: const Icon(Icons.volume_up),
          title: 'Voice response',
          value: 'Headphones only, and a much longer value than any row should hold',
          onTap: () {},
        ),
        textScale: 1.3,
        width: width,
      ),
    );
    await tester.pump();

    expect(tester.takeException(), isNull);
    final valueFinder = find.textContaining('Headphones only');
    expect(tester.widget<Text>(valueFinder).overflow, TextOverflow.ellipsis);
    final titleRect = tester.getRect(find.text('Voice response'));
    final valueRect = tester.getRect(valueFinder);
    expect(titleRect.right, lessThanOrEqualTo(valueRect.left));
    expect(find.byIcon(Icons.chevron_right), findsOneWidget);
  });
}
