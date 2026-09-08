import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/memory.dart';

void main() {
  group('MemoryLayer decode', () {
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

    test('layer preferred over tier alias when both present', () {
      final memory = Memory.fromJson({
        'id': 'mem-priority',
        'uid': 'user-1',
        'content': 'Priority test',
        'category': 'system',
        'layer': 'short_term',
        'tier': 'long_term',
        'created_at': '2026-06-21T10:00:00.000Z',
        'updated_at': '2026-06-21T10:05:00.000Z',
        'visibility': 'private',
      });

      expect(memory.layer, MemoryLayer.shortTerm);
      expect(memory.layerIsExplicit, isTrue);
    });
  });
}
