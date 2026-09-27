import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/services/siri_integration.dart';

void main() {
  group('MemoryLayer decode', () {
    test('Siri accepts absent and null legacy tiers but excludes archive', () {
      final base = <String, dynamic>{
        'id': 'legacy-1',
        'uid': 'user-1',
        'content': 'Legacy memory',
        'category': 'interesting',
        'created_at': '2026-06-21T10:00:00.000Z',
        'updated_at': '2026-06-21T10:05:00.000Z',
        'visibility': 'private',
      };
      final now = DateTime.utc(2026, 6, 22);
      for (final (name, tier, expected, explicit) in <(String, Object?, bool, bool)>[
        ('absent', null, true, false),
        ('null', null, true, false),
        ('short_term', 'short_term', true, true),
        ('long_term', 'long_term', true, true),
        ('archive', 'archive', false, true),
      ]) {
        final json = {...base};
        if (name != 'absent') json['memory_tier'] = tier;
        final row = Memory.fromJson(json);
        expect(row.layerIsExplicit, explicit, reason: name);
        expect(siriMemoryIsIndexable(row, now, owner: 'user-1'), expected, reason: name);
      }
    });

    test('unknown explicit tier is rejected like the backend enum', () {
      final row = <String, dynamic>{
        'id': 'legacy-1',
        'uid': 'user-1',
        'content': 'Legacy memory',
        'category': 'interesting',
        'created_at': '2026-06-21T10:00:00.000Z',
        'updated_at': '2026-06-21T10:05:00.000Z',
        'visibility': 'private',
        'memory_tier': 'future_tier',
      };
      expect(() => Memory.fromJson(row), throwsA(isA<FormatException>()));
    });

    test('unknown legacy alias is ignored like the backend extra field', () {
      final row = Memory.fromJson({
        'id': 'legacy-1',
        'uid': 'user-1',
        'content': 'Legacy memory',
        'category': 'interesting',
        'created_at': '2026-06-21T10:00:00.000Z',
        'updated_at': '2026-06-21T10:05:00.000Z',
        'layer': 'future_tier',
      });
      expect(row.layer, MemoryLayer.longTerm);
      expect(row.layerIsExplicit, false);
      expect(siriMemoryIsIndexable(row, DateTime.utc(2026, 6, 22), owner: 'user-1'), true);
    });

    test('conflicting aliases cannot override an archived canonical tier', () {
      final row = <String, dynamic>{
        'id': 'archive-1',
        'uid': 'user-1',
        'content': 'Archived memory',
        'category': 'interesting',
        'created_at': '2026-06-21T10:00:00.000Z',
        'updated_at': '2026-06-21T10:05:00.000Z',
        'layer': 'long_term',
        'memory_tier': 'archive',
      };
      expect(() => Memory.fromJson(row), throwsA(isA<FormatException>()));
    });
    test('layer field only sets explicit layer', () {
      final memory = Memory.fromJson({
        'id': 'mem-layer-1',
        'uid': 'user-1',
        'content': 'Short-term fact',
        'category': 'system',
        'layer': 'short_term',
        'created_at': '2026-06-21T10:00:00.000Z',
        'updated_at': '2026-06-21T10:05:00.000Z',
        'visibility': 'private',
      });

      expect(memory.layer, MemoryLayer.shortTerm);
      expect(memory.layerIsExplicit, isTrue);
    });

    test('memory_tier alias decodes to layer', () {
      final memory = Memory.fromJson({
        'id': 'mem-archive-1',
        'uid': 'user-1',
        'content': 'Archived fact',
        'category': 'manual',
        'memory_tier': 'archive',
        'created_at': '2026-06-21T10:00:00.000Z',
        'updated_at': '2026-06-21T10:05:00.000Z',
        'visibility': 'private',
      });

      expect(memory.layer, MemoryLayer.archive);
      expect(memory.layerIsExplicit, isTrue);
    });

    test('missing layer defaults to long term without explicit flag', () {
      final memory = Memory.fromJson({
        'id': 'legacy-1',
        'uid': 'user-1',
        'content': 'Legacy memory',
        'category': 'interesting',
        'created_at': '2026-06-21T10:00:00.000Z',
        'updated_at': '2026-06-21T10:05:00.000Z',
        'visibility': 'private',
      });

      expect(memory.layer, MemoryLayer.longTerm);
      expect(memory.layerIsExplicit, isFalse);
    });

    test('conflicting legacy tier aliases fail closed', () {
      final row = <String, dynamic>{
        'id': 'mem-priority',
        'uid': 'user-1',
        'content': 'Priority test',
        'category': 'system',
        'layer': 'short_term',
        'tier': 'long_term',
        'created_at': '2026-06-21T10:00:00.000Z',
        'updated_at': '2026-06-21T10:05:00.000Z',
        'visibility': 'private',
      };
      expect(() => Memory.fromJson(row), throwsA(isA<FormatException>()));
    });
  });
}
