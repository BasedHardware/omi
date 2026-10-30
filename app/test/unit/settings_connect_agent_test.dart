import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/settings_destinations.dart';
import 'package:omi/pages/settings/settings_search_index.dart';

/// Connect an Agent is a visible Settings row (not only inside Developer Settings) that opens the
/// web developer home, the one place agent setup prompts and keys live.
void main() {
  final en = lookupAppLocalizations(const Locale('en'));
  const scope = SettingsSearchScope(deviceConnected: false, supportLinks: false, android: false);

  test('opens the web developer home', () {
    expect(developerHomeUrl.toString(), 'https://app.omi.me/developers');
  });

  test('is found by the words people search for when connecting an agent', () {
    for (final query in ['agent', 'MCP', 'Claude Code', 'Developer API']) {
      final hits = searchSettings(en, query, scope).map((e) => e.destination);
      expect(hits, contains(SettingsDestination.connectAgent), reason: query);
    }
  });
}
