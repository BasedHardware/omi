import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

final _repoRoot = Directory.current.parent;
final _envLikeToken = RegExp(r'\b[A-Z][A-Z0-9_]{2,}\b');

String _read(String relativePath) => File('${_repoRoot.path}/$relativePath').readAsStringSync();

Iterable<File> _trackedFilesUnder(String relativePath, {Set<String>? extensions}) sync* {
  final result = Process.runSync('git', ['ls-files', relativePath], workingDirectory: _repoRoot.path);
  expect(result.exitCode, 0, reason: result.stderr.toString());
  for (final line in const LineSplitter().convert(result.stdout.toString())) {
    if (line.isEmpty) continue;
    final file = File('${_repoRoot.path}/$line');
    if (extensions != null && !extensions.any((extension) => file.path.endsWith(extension))) continue;
    yield file;
  }
}

void main() {
  final policy = jsonDecode(_read('app/config/client_env_policy.yaml')) as Map<String, dynamic>;
  final allowed = Set<String>.from((policy['public_client_env'] as Map<String, dynamic>)['allowed'] as List);
  final denied = Set<String>.from((policy['server_secret_env'] as Map<String, dynamic>)['denied_exact'] as List);
  final deniedPatterns = ((policy['server_secret_env'] as Map<String, dynamic>)['denied_name_patterns'] as List)
      .map((pattern) => RegExp(pattern as String))
      .toList();

  bool isDeniedName(String name) =>
      !allowed.contains(name) && (denied.contains(name) || deniedPatterns.any((pattern) => pattern.hasMatch(name)));

  test('mobile env source cannot expose server-only variables', () {
    final files = [
      'app/lib/env/env.dart',
      'app/lib/env/prod_env.dart',
      'app/lib/env/dev_env.dart',
      'app/.env.template',
      'app/.client.env.example',
    ];

    for (final relativePath in files) {
      final text = _read(relativePath);
      for (final name in denied) {
        expect(text, isNot(contains(name)), reason: '$relativePath must not expose $name to public client builds');
      }
      for (final match in _envLikeToken.allMatches(text)) {
        final token = match.group(0)!;
        expect(isDeniedName(token), isFalse, reason: '$relativePath must not expose $token to public client builds');
      }
    }
  });

  test('public client env policy documents restricted public keys', () {
    final restricted = policy['restricted_public_client_keys'] as Map<String, dynamic>;

    for (final entry in restricted.entries) {
      expect(allowed, contains(entry.key));
      final metadata = entry.value as Map<String, dynamic>;
      for (final field in ['owner', 'purpose', 'restriction', 'revocation']) {
        final value = metadata[field];
        expect(value, isA<String>(), reason: '${entry.key} is missing $field');
        expect((value as String).trim(), isNotEmpty, reason: '${entry.key} is missing $field');
      }
    }
  });

  test('Codemagic app builds use the public config generator', () {
    final codemagic = _read('codemagic.yaml');
    expect(codemagic, isNot(contains('Set up App .env')));
    expect(codemagic, isNot(contains('OPENAI_API_KEY=\$OPENAI_API_KEY >> .env')));
    expect(codemagic, isNot(contains('GOOGLE_CLIENT_SECRET=\$GOOGLE_CLIENT_SECRET >> .env')));
    expect(codemagic, contains('create-public-client-env.sh'));
    expect(codemagic, contains('scan-public-artifact-secrets.py'));
  });

  test('app source does not expose denied server env names', () {
    for (final file in _trackedFilesUnder('app/lib', extensions: {'.dart'})) {
      final text = file.readAsStringSync();
      for (final name in denied) {
        expect(text, isNot(contains(name)), reason: '${file.path} must not expose $name');
      }
      for (final match in _envLikeToken.allMatches(text)) {
        final token = match.group(0)!;
        expect(isDeniedName(token), isFalse, reason: '${file.path} must not expose $token');
      }
    }
  });
}
