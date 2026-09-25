import 'dart:convert';
import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/settings_search_index.dart';

/// chat-apps-settings #3: the Settings search index must only point at rows that exist. Each entry
/// names the file that draws its row and the l10n key of the row's title; this test reads those
/// source files, so deleting or renaming a row without updating the index fails here.
void main() {
  final en = lookupAppLocalizations(const Locale('en'));
  final enArb = jsonDecode(File('lib/l10n/app_en.arb').readAsStringSync()) as Map<String, dynamic>;

  test('every entry names a real l10n key whose English text is the title it shows', () {
    for (final entry in settingsSearchEntries) {
      expect(enArb.containsKey(entry.key), isTrue, reason: '${entry.key} is not an l10n key');
      expect(entry.title(en), enArb[entry.key], reason: '${entry.key}: title getter and key disagree');
    }
  });

  test('every entry\'s row exists: its row file draws the title with that key', () {
    for (final entry in settingsSearchEntries) {
      final file = File(entry.rowFile);
      expect(file.existsSync(), isTrue, reason: '${entry.key}: ${entry.rowFile} does not exist');
      final source = file.readAsStringSync();
      expect(
        RegExp('l10n\\.${RegExp.escape(entry.key)}\\b').hasMatch(source),
        isTrue,
        reason: '${entry.key}: no row titled l10n.${entry.key} in ${entry.rowFile}',
      );
    }
  });

  test('every Settings row in the sheet opens a destination and is searchable', () {
    final drawer = File('lib/pages/settings/settings_drawer.dart').readAsStringSync();
    final rowDestinations =
        RegExp(r'_row\(\s*SettingsDestination\.(\w+)').allMatches(drawer).map((m) => m.group(1)!).toSet();
    expect(rowDestinations, isNotEmpty);
    final searchable = settingsSearchEntries.map((e) => e.destination.name).toSet();
    for (final destination in rowDestinations) {
      expect(searchable, contains(destination), reason: 'Settings row $destination has no search entry');
    }
  });

  test('entries are unique and none points at a removed orphan', () {
    final keys = settingsSearchEntries.map((e) => e.key).toList();
    expect(keys.toSet().length, keys.length, reason: 'duplicate search entries');
    // No visible row is titled "API Keys" or "API Environment" (the old orphans).
    expect(keys, isNot(contains('apiKeys')));
    expect(keys, isNot(contains('apiEnvironment')));
    expect(keys, isNot(contains('sdCardSync')));
  });

  test('search honours the rows on screen', () {
    const connected = SettingsSearchScope(deviceConnected: true, supportLinks: true, android: true);
    const disconnected = SettingsSearchScope(deviceConnected: false, supportLinks: false, android: false);

    expect(searchSettings(en, '', connected), isEmpty);
    expect(searchSettings(en, en.micGain, connected).map((e) => e.key), contains('micGain'));
    expect(searchSettings(en, en.micGain, disconnected), isEmpty);
    expect(searchSettings(en, en.backgroundModeTitle, disconnected), isEmpty);

    // Everyday settings are found at the top level (D4), not only inside Developer Settings.
    final transcription = searchSettings(en, en.transcription, disconnected);
    expect(transcription.first.destination, SettingsDestination.transcription);
    expect(searchSettings(en, en.exportAllData, disconnected).single.destination, SettingsDestination.exportData);
    expect(searchSettings(en, en.phoneCalls, disconnected).first.destination, SettingsDestination.phoneCalls);

    // Rows inside a page open that row's page, not the top of Profile.
    expect(searchSettings(en, en.language, disconnected).first.destination, SettingsDestination.language);
    expect(
      searchSettings(en, en.deleteAccountTitle, disconnected).single.destination,
      SettingsDestination.deleteAccount,
    );
  });

  test('"Profile" still finds the Account row (its old name) and Voice Profile', () {
    const scope = SettingsSearchScope(deviceConnected: false, supportLinks: false, android: false);
    final results = searchSettings(en, 'profile', scope);
    expect(results.map((e) => e.destination),
        containsAll([SettingsDestination.profile, SettingsDestination.voiceProfile]));
    expect(results.firstWhere((e) => e.destination == SettingsDestination.profile).title(en), 'Account');
  });
}
