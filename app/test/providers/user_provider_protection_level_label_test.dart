import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/providers/user_provider.dart';

void main() {
  group('dataProtectionLevelLabel', () {
    test('names each backend level id with its localized label', () {
      final en = lookupAppLocalizations(const Locale('en'));
      expect(dataProtectionLevelLabel(en, 'enhanced'), 'Secure Encryption');
      expect(dataProtectionLevelLabel(en, 'e2ee'), 'End-to-End Encryption');

      final de = lookupAppLocalizations(const Locale('de'));
      expect(dataProtectionLevelLabel(de, 'enhanced'), 'Sichere Verschlüsselung');

      final es = lookupAppLocalizations(const Locale('es'));
      expect(dataProtectionLevelLabel(es, 'enhanced'), 'Cifrado seguro');
    });

    test('never puts the raw id into the migration notifications', () {
      for (final locale in AppLocalizations.supportedLocales) {
        final l10n = lookupAppLocalizations(locale);
        final label = dataProtectionLevelLabel(l10n, 'enhanced');
        expect(l10n.migratingToProtection(label), isNot(contains('enhanced')), reason: '$locale');
      }
    });

    test('shows an unknown level id as-is', () {
      final en = lookupAppLocalizations(const Locale('en'));
      expect(dataProtectionLevelLabel(en, 'future_level'), 'future_level');
    });
  });
}
