import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/widgets/profile_settings_tile.dart';

// Regression for #12898: the Profile page's "Transcribe Later" row (title +
// BETA tag + "Off" chip) painted RIGHT OVERFLOWED stripes, and "Voice
// response" broke mid-word next to its "Headphones only" chip, once system
// text was enlarged. The tile must lay out without overflow at narrow widths
// and large text scales, keep the chip from crowding out the title, and
// still show every part.

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
          child: SizedBox(width: width, child: child),
        ),
      ),
    ),
  );
}

ProfileSettingsTile _transcribeLater() => ProfileSettingsTile(
      title: 'Transcribe Later',
      icon: const Icon(Icons.save),
      showBetaTag: true,
      chipValue: 'Off',
      onTap: () {},
    );

void main() {
  testWidgets('title, BETA tag and chip fit a narrow row at 1.6x text without overflow', (tester) async {
    await tester.pumpWidget(_app(_transcribeLater(), textScale: 1.6));
    await tester.pump();

    expect(tester.takeException(), isNull);
    expect(find.text('Transcribe Later'), findsOneWidget);
    expect(find.text('BETA'), findsOneWidget);
    expect(find.text('Off'), findsOneWidget);
  });

  testWidgets('a wide chip is capped so the title keeps at least its share of the row', (tester) async {
    const width = 360.0;
    await tester.pumpWidget(
      _app(
        ProfileSettingsTile(
          title: 'Voice response',
          icon: const Icon(Icons.volume_up),
          chipValue: 'Headphones only, and a much longer value than any row should hold',
          onTap: () {},
          useInkWell: true,
        ),
        textScale: 1.3,
        width: width,
      ),
    );
    await tester.pump();

    expect(tester.takeException(), isNull);
    final chipTextFinder = find.textContaining('Headphones only');
    expect(tester.widget<Text>(chipTextFinder).overflow, TextOverflow.ellipsis);

    // The row's content area is the tile width minus its horizontal padding.
    const contentWidth = width - 32;
    final chipMax = ProfileSettingsTile.chipMaxWidth(contentWidth, showChevron: true);
    final chipBox = tester.getSize(find.ancestor(of: chipTextFinder, matching: find.byType(ConstrainedBox)).first);
    expect(chipBox.width, lessThanOrEqualTo(chipMax + 0.01));

    // The title gets everything the chip cannot take: it sits left of the
    // chip with at least the complementary share of the shared width.
    final titleRect = tester.getRect(find.text('Voice response'));
    final chipRect = tester.getRect(chipTextFinder);
    expect(titleRect.right, lessThanOrEqualTo(chipRect.left));
    final sharedWidth = chipMax / ProfileSettingsTile.chipMaxWidthFraction;
    expect(titleRect.width, greaterThanOrEqualTo(sharedWidth * (1 - ProfileSettingsTile.chipMaxWidthFraction) - 0.01));
  });

  testWidgets('subtitle shows only without a chip, and the chevron can be hidden', (tester) async {
    await tester.pumpWidget(
      _app(
        ProfileSettingsTile(
          title: 'User ID',
          subtitle: 'Tap to copy',
          icon: const Icon(Icons.badge),
          onTap: () {},
          showChevron: false,
        ),
      ),
    );
    await tester.pump();

    expect(tester.takeException(), isNull);
    expect(find.text('Tap to copy'), findsOneWidget);
    expect(find.byIcon(Icons.chevron_right), findsNothing);
  });
}
