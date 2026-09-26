import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/home/home_content.dart';
import 'package:omi/ui/ui.dart';

/// Home's greeting changes every two hours and fits one line with the reader's first name.
void main() {
  test('something different every two hours, in every language', () {
    for (final locale in AppLocalizations.supportedLocales) {
      final l10n = lookupAppLocalizations(locale);
      final day = [for (var hour = 0; hour < 24; hour++) HomeGreeting.forHour(l10n, hour)];
      expect(day.toSet().length, 12, reason: '$locale: twelve slots, none repeated');
      for (var hour = 0; hour < 24; hour += 2) {
        expect(day[hour + 1], day[hour], reason: '$locale: $hour:00 and ${hour + 1}:00 share a slot');
      }
    }
    final en = lookupAppLocalizations(const Locale('en'));
    expect(HomeGreeting.forHour(en, 1), 'Up late');
    expect(HomeGreeting.forHour(en, 7), 'New day');
    expect(HomeGreeting.forHour(en, 11), 'Busy morning');
    expect(HomeGreeting.forHour(en, 17), 'Home stretch');
    expect(HomeGreeting.forHour(en, 23), 'Good night');
  });

  test('the name joins the greeting only when the whole line fits', () {
    final en = lookupAppLocalizations(const Locale('en'));
    final personal = en.greetingWithName(en.greetingBusyMorning, 'Ashwin');
    expect(personal, 'Busy morning, Ashwin');
    // The test font draws every letter as a 34 pt square: 20 characters are 680 pt wide.
    bool fits(double width) =>
        HomeGreeting.fitsOneLine(personal, OmiType.largeTitle, width, TextScaler.noScaling, TextDirection.ltr);
    expect(fits(700), isTrue);
    expect(fits(600), isFalse, reason: 'a long line keeps the name under the greeting instead');
    expect(
      HomeGreeting.fitsOneLine(personal, OmiType.largeTitle, 700, const TextScaler.linear(1.3), TextDirection.ltr),
      isFalse,
      reason: 'larger text sizes count',
    );
  });
}
