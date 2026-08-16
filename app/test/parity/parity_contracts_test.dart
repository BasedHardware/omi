import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/gen/action_items_folders_wire.g.dart';
import 'package:omi/pages/action_items/task_categorization.dart';
import 'package:omi/providers/conversation_provider.dart';

/// Flutter conformance suite for the shared cross-platform parity contracts
/// (contracts/parity/README.md). Runs the repo-root fixture vectors through the
/// REAL production rules: task bucketing (categorizeTasks, this platform's
/// separate_overdue model), local-day conversation keys
/// (conversationLocalDayKey, the #10198 contract), and action item wire decode
/// (GeneratedActionItemResponse.fromJson). Day-key cases execute only when the
/// fixture covers the runner's zone offset at that instant; offset 0 is always
/// present so UTC CI runs every case.
void main() {
  final root = _repoRoot();

  group('task due buckets (separate_overdue model)', () {
    final fixture = _fixture(root, 'task_due_buckets.json');
    const bucketByName = {
      'today': TaskCategory.today,
      'tomorrow': TaskCategory.tomorrow,
      'later': TaskCategory.later,
      'no_deadline': TaskCategory.noDeadline,
      'overdue': TaskCategory.overdue,
    };
    for (final raw in fixture['cases'] as List<dynamic>) {
      final c = raw as Map<String, dynamic>;
      test(c['name'] as String, () {
        final now = _localFromComponents(c['now'] as List<dynamic>);
        final due = c['due'] == null ? null : _localFromComponents(c['due'] as List<dynamic>);
        final created = c['created'] == null ? null : _localFromComponents(c['created'] as List<dynamic>);
        final item = _wireItem(due: due, created: created);

        final categorized = categorizeTasks([item], false, now: now);
        final actual = categorized.entries.where((e) => e.value.contains(item)).map((e) => e.key).toList();
        final expectedName = (c['expected'] as Map<String, dynamic>)['separate_overdue'] as String;

        expect(actual, [bucketByName[expectedName]!]);
      });
    }
  });

  group('local day keys', () {
    final fixture = _fixture(root, 'day_keys.json');
    for (final raw in fixture['cases'] as List<dynamic>) {
      final c = raw as Map<String, dynamic>;
      final instant = DateTime.parse(c['utc'] as String);
      final offsetEast = instant.toLocal().timeZoneOffset.inMinutes;
      final expected = (c['expected_by_offset'] as Map<String, dynamic>)['$offsetEast'] as String?;
      test('${c['name']} (offset $offsetEast)', () {
        final key = conversationLocalDayKey(instant);
        expect('${key.year}-${_pad(key.month)}-${_pad(key.day)}', expected);
      }, skip: expected == null ? 'fixture does not cover this zone offset' : false);
    }
  });

  group('action item wire decode (parity contract)', () {
    final fixture = _fixture(root, 'wire_action_item.json');
    for (final raw in fixture['cases'] as List<dynamic>) {
      final c = raw as Map<String, dynamic>;
      test(c['name'] as String, () {
        final byModel = c['expected_by_model'] as Map<String, dynamic>?;
        if (byModel != null) {
          // This client is the strict_decode model: a present-but-unparseable
          // due_at rejects the whole item (see the README divergence register).
          final strict = byModel['strict_decode'] as Map<String, dynamic>;
          expect(strict['parses'], isFalse);
          expect(
            () => GeneratedActionItemResponse.fromJson(c['payload'] as Map<String, dynamic>),
            throwsFormatException,
          );
          return;
        }
        final expected = c['expected'] as Map<String, dynamic>;
        final item = GeneratedActionItemResponse.fromJson(c['payload'] as Map<String, dynamic>);

        expect(expected['parses'], isTrue);
        expect(item.description, expected['description']);
        expect(item.completed, expected['completed']);
        final dueUtc = expected['due_utc'] as String?;
        if (dueUtc == null) {
          expect(item.dueAt, isNull);
        } else {
          expect(item.dueAt?.millisecondsSinceEpoch, DateTime.parse(dueUtc).millisecondsSinceEpoch);
        }
      });
    }
  });
}

/// Walk up from the package dir to the repo root (the dir holding
/// contracts/parity), so the suite works from either the app dir or repo root.
Directory _repoRoot() {
  var dir = Directory.current.absolute;
  for (var i = 0; i < 6; i++) {
    if (Directory('${dir.path}${Platform.pathSeparator}contracts${Platform.pathSeparator}parity').existsSync()) {
      return dir;
    }
    final parent = dir.parent;
    if (parent.path == dir.path) break;
    dir = parent;
  }
  throw StateError('contracts/parity not found above ${Directory.current.path}');
}

Map<String, dynamic> _fixture(Directory root, String name) {
  final file = File(
    '${root.path}${Platform.pathSeparator}contracts${Platform.pathSeparator}parity'
    '${Platform.pathSeparator}$name',
  );
  return jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
}

/// Fixture local-time components [year, month, day, hour?, minute?] in the
/// runner's zone (the contracts are calendar rules, zone-independent).
DateTime _localFromComponents(List<dynamic> c) =>
    DateTime(c[0] as int, c[1] as int, c[2] as int, c.length > 3 ? c[3] as int : 0, c.length > 4 ? c[4] as int : 0);

String _pad(int n) => n.toString().padLeft(2, '0');

/// Build the item through the production wire decode so bucket cases exercise
/// the same path a backend response takes.
GeneratedActionItemResponse _wireItem({DateTime? due, DateTime? created}) => GeneratedActionItemResponse.fromJson({
      'id': 'parity',
      'description': 'parity case',
      'completed': false,
      if (created != null) 'created_at': created.toUtc().toIso8601String(),
      if (due != null) 'due_at': due.toUtc().toIso8601String(),
    });
