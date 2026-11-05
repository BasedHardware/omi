// Static content check for the iOS permission purpose strings (#17853).
//
// iOS shows these strings verbatim in its permission prompts. They had drifted
// to describe Instabug bug reporting, which the app no longer ships, instead of
// the features that request the permissions today. This pins the base plist,
// the dev plist and every localized InfoPlist.strings override to non-empty
// copy without that retired wording.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

const _runnerDir = 'ios/Runner';

/// Retired copy: Instabug bug reports and the generic calendar line.
final _staleWording = <RegExp>[
  RegExp('instabug', caseSensitive: false),
  RegExp(r'\bbugs?\b', caseSensitive: false),
  RegExp('report issues', caseSensitive: false),
  RegExp('most functions', caseSensitive: false),
  RegExp('不具合'),
  RegExp('カレンダー機能の大部分'),
];

final _purposeKeyTag = RegExp(r'<key>(NS\w+UsageDescription)</key>');
final _purposeEntry = RegExp(r'<key>(NS\w+UsageDescription)</key>\s*<string(?:>([^<]*)</string>|\s*/>)');
final _stringsEntry = RegExp(r'"(\w+)"\s*=\s*"((?:[^"\\]|\\.)*)"\s*;');

String _unescapeXml(String value) => value
    .replaceAll('&lt;', '<')
    .replaceAll('&gt;', '>')
    .replaceAll('&quot;', '"')
    .replaceAll('&apos;', "'")
    .replaceAll('&amp;', '&');

/// `NS*UsageDescription` keys of an XML plist mapped to their string values.
Map<String, String> _plistPurposeStrings(String path) {
  final source = File(path).readAsStringSync();
  final entries = <String, String>{};
  for (final match in _purposeEntry.allMatches(source)) {
    entries[match.group(1)!] = _unescapeXml(match.group(2) ?? '');
  }
  expect(entries.length, _purposeKeyTag.allMatches(source).length,
      reason: '$path: every purpose key must have a <string> value');
  return entries;
}

/// `NS*UsageDescription` overrides of an InfoPlist.strings file.
Map<String, String> _stringsPurposeStrings(String path) {
  final source = File(path).readAsStringSync();
  return {
    for (final match in _stringsEntry.allMatches(source))
      if (match.group(1)!.endsWith('UsageDescription')) match.group(1)!: match.group(2)!,
  };
}

List<String> _localizedStringsFiles() {
  return Directory(_runnerDir)
      .listSync()
      .whereType<Directory>()
      .where((dir) => dir.path.endsWith('.lproj'))
      .map((dir) => File('${dir.path}/InfoPlist.strings'))
      .where((file) => file.existsSync())
      .map((file) => file.path)
      .toList()
    ..sort();
}

void _expectCurrentCopy(String source, Map<String, String> entries) {
  for (final entry in entries.entries) {
    expect(entry.value.trim(), isNotEmpty, reason: '$source ${entry.key} is empty');
    for (final stale in _staleWording) {
      expect(stale.hasMatch(entry.value), isFalse,
          reason: '$source ${entry.key} still uses retired copy "${stale.pattern}": ${entry.value}');
    }
  }
}

void main() {
  late Map<String, String> base;

  setUpAll(() {
    base = _plistPurposeStrings('$_runnerDir/Info.plist');
  });

  test('base Info.plist purpose strings are non-empty and describe current features', () {
    expect(base, isNotEmpty);
    _expectCurrentCopy('Info.plist', base);
  });

  test('Info-Dev.plist carries the same purpose strings as Info.plist', () {
    expect(_plistPurposeStrings('$_runnerDir/Info-Dev.plist'), equals(base));
  });

  test('localized InfoPlist.strings overrides only base purpose keys with current copy', () {
    final files = _localizedStringsFiles();
    expect(files, isNotEmpty, reason: 'expected at least ja.lproj/InfoPlist.strings');
    for (final path in files) {
      final localized = _stringsPurposeStrings(path);
      expect(localized, isNotEmpty, reason: path);
      final unknown = localized.keys.toSet().difference(base.keys.toSet());
      expect(unknown, isEmpty, reason: '$path overrides purpose keys that Info.plist does not declare');
      _expectCurrentCopy(path, localized);
    }
  });
}
