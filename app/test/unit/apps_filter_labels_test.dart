import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations_en.dart';

void main() {
  group('apps filter labels', () {
    test('authorship and possession filters stay visually distinct', () {
      final ln = AppLocalizationsEn();

      expect(
        ln.myApps,
        isNot(ln.installedApps),
        reason: 'The authorship filter must not read the same as the '
            'possession filter, or "My Apps" looks broken next to '
            '"Installed Apps".',
      );
      expect(ln.myApps, isNotEmpty);
      expect(ln.installedApps, isNotEmpty);
    });

    test('authorship label no longer reads as a generic "My Apps"', () {
      final ln = AppLocalizationsEn();

      expect(
        ln.myApps.toLowerCase(),
        isNot(equals('my apps')),
        reason: 'The authorship filter used to say "My Apps", which reads '
            'as the apps a user has rather than the apps they created.',
      );
    });
  });
}
