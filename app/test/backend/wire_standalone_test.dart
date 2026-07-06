/// Standalone wire decode test that imports ONLY generated types from gen/.
/// Avoids the full app compilation chain (pre-existing FaIconData errors block flutter test).
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/gen/action_items_folders_wire.g.dart' as action_items;
import 'package:omi/backend/schema/gen/api_keys_wire.g.dart' as api_keys;
import 'package:omi/backend/schema/gen/phone_calls_wire.g.dart' as phone;

void main() {
  group('ActionItem wire roundtrip', () {
    test('fromJson decodes all snake_case fields', () {
      final json = {
        'id': 'ai-1',
        'description': 'Follow up',
        'completed': false,
        'created_at': '2025-01-15T10:30:00.000Z',
        'due_at': '2025-01-20T17:00:00.000Z',
        'conversation_id': 'conv-123',
        'is_locked': false,
        'exported': true,
        'indent_level': 2,
        'sort_order': 5,
      };

      final item = action_items.GeneratedActionItemResponse.fromJson(json);
      expect(item.id, 'ai-1');
      expect(item.description, 'Follow up');
      expect(item.completed, isFalse);
      expect(item.createdAt, isNotNull);
      expect(item.dueAt, isNotNull);
      expect(item.conversationId, 'conv-123');
      expect(item.exported, isTrue);
      expect(item.indentLevel, 2);
      expect(item.sortOrder, 5);
    });

    test('toJson → fromJson roundtrip is lossless', () {
      final original = action_items.GeneratedActionItemResponse(
        id: 'ai-rt',
        description: 'Roundtrip test',
        completed: true,
        createdAt: DateTime.parse('2025-01-15T10:00:00.000Z'),
        conversationId: 'conv-rt',
        isLocked: true,
        indentLevel: 3,
        sortOrder: 10,
      );

      final encoded = original.toJson();
      final decoded = action_items.GeneratedActionItemResponse.fromJson(encoded);

      expect(decoded.id, original.id);
      expect(decoded.description, original.description);
      expect(decoded.completed, original.completed);
      expect(decoded.conversationId, original.conversationId);
      expect(decoded.isLocked, original.isLocked);
      expect(decoded.indentLevel, original.indentLevel);
      expect(decoded.sortOrder, original.sortOrder);
    });

    test('defaults applied for optional fields', () {
      final json = {'id': 'ai-min', 'description': 'Minimal', 'completed': false};

      final item = action_items.GeneratedActionItemResponse.fromJson(json);
      expect(item.indentLevel, 0);
      expect(item.sortOrder, 0);
      expect(item.isLocked, false);
      expect(item.exported, false);
      expect(item.createdAt, isNull);
    });
  });

  group('ActionItemsResponse list decode', () {
    test('decodes list with hasMore flag', () {
      final json = {
        'action_items': [
          {'id': '1', 'description': 'A', 'completed': false},
          {'id': '2', 'description': 'B', 'completed': true},
        ],
        'has_more': true,
      };

      final resp = action_items.GeneratedActionItemsResponse.fromJson(json);
      expect(resp.actionItems.length, 2);
      expect(resp.hasMore, isTrue);
      expect(resp.actionItems[1].completed, isTrue);
    });
  });

  group('DevApiKey wire roundtrip', () {
    test('fromJson → toJson roundtrip with DateTime', () {
      final json = {
        'id': 'key-1',
        'name': 'Test',
        'key_prefix': 'omi_abc',
        'created_at': '2025-06-01T08:00:00.000Z',
        'last_used_at': null,
        'scopes': ['read', 'write'],
      };

      final key = api_keys.GeneratedDevApiKey.fromJson(json);
      expect(key.id, 'key-1');
      expect(key.scopes, ['read', 'write']);
      expect(key.createdAt, isNotNull);
      expect(key.lastUsedAt, isNull);

      final encoded = key.toJson();
      final key2 = api_keys.GeneratedDevApiKey.fromJson(encoded);
      expect(key2.id, key.id);
      expect(key2.scopes, key.scopes);
    });
  });

  group('McpApiKey wire decode', () {
    test('decodes with optional appId', () {
      final json = {
        'id': 'mcp-1',
        'name': 'Agent Key',
        'key_prefix': 'mcp_def',
        'created_at': '2025-01-15T10:00:00.000Z',
        'last_used_at': null,
        'scopes': ['agent:tools'],
        'app_id': 'app-123',
      };

      final key = api_keys.GeneratedMcpApiKey.fromJson(json);
      expect(key.id, 'mcp-1');
      expect(key.appId, 'app-123');
      expect(key.scopes, ['agent:tools']);
    });
  });

  group('Folder wire decode', () {
    test('fromJson → toJson roundtrip', () {
      final json = {
        'id': 'folder-1',
        'name': 'Work',
        'description': 'Work conversations',
        'created_at': '2025-01-15T10:00:00.000Z',
        'updated_at': '2025-01-15T11:00:00.000Z',
      };

      final folder = action_items.GeneratedFolder.fromJson(json);
      expect(folder.id, 'folder-1');
      expect(folder.name, 'Work');

      final encoded = folder.toJson();
      final folder2 = action_items.GeneratedFolder.fromJson(encoded);
      expect(folder2.id, folder.id);
      expect(folder2.name, folder.name);
    });
  });

  group('PhoneNumber wire decode', () {
    test('decodes phone number response', () {
      final json = {
        'id': 'phone-1',
        'phone_number': '+1234567890',
        'verified_at': '2025-01-15T10:00:00.000Z',
        'is_primary': true,
        'friendly_name': null,
      };

      final pn = phone.GeneratedPhoneNumberResponse.fromJson(json);
      expect(pn.phoneNumber, '+1234567890');
      expect(pn.isPrimary, isTrue);
      expect(pn.verifiedAt, isNotNull);
    });
  });
}
