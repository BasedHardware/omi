import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/home/widgets/battery_info_widget.dart';
import 'package:omi/pages/phone_calls/phone_calls_feature.dart';

// Phone calls are hidden from the mobile app for now. The pendant "one source at a time" sheet
// offers a call only when given one; callers pass null while PhoneCallsFeature.visible is false.
void main() {
  Future<void> pump(WidgetTester tester, {VoidCallback? onPhoneCall}) => tester.pumpWidget(MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: PendantListeningSheet(onRecordWithPhone: () {}, onPhoneCall: onPhoneCall, onKeepPendant: () {}),
        ),
      ));

  test('phone calls are switched off', () => expect(PhoneCallsFeature.visible, isFalse));

  testWidgets('pendant sheet hides the phone-call option without a callback', (tester) async {
    await pump(tester);
    final en = lookupAppLocalizations(const Locale('en'));
    expect(find.text(en.phoneCall), findsNothing);
    expect(find.text(en.recordWithPhoneInstead), findsOneWidget);
    expect(find.text(en.keepUsingPendant), findsOneWidget);
  });

  testWidgets('pendant sheet still offers a call when one is given', (tester) async {
    await pump(tester, onPhoneCall: () {});
    final en = lookupAppLocalizations(const Locale('en'));
    expect(find.text(en.phoneCall), findsOneWidget);
  });
}
