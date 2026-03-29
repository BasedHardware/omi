import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/message.dart';

void main() {
  group('GenUiBlock', () {
    test('parses action_buttons blocks from server JSON', () {
      final block = GenUiBlock.fromJson({
        'type': 'action_buttons',
        'props': {
          'title': 'Quick actions',
          'buttons': ['Share location', 'Find nearby coffee'],
        },
      });

      expect(block.type, GenUiBlockType.actionButtons);
      expect(block.props['title'], 'Quick actions');
      expect(block.props['buttons'], ['Share location', 'Find nearby coffee']);
    });

    test('serializes actionButtons blocks back to snake_case wire format', () {
      final block = GenUiBlock(
        type: GenUiBlockType.actionButtons,
        props: {
          'title': 'Quick actions',
          'buttons': ['Share location'],
        },
      );

      expect(block.toJson(), {
        'type': 'action_buttons',
        'props': {
          'title': 'Quick actions',
          'buttons': ['Share location'],
        },
      });
    });
  });

  group('ServerMessage', () {
    test('hydrates uiBlocks from chat payload JSON', () {
      final message = ServerMessage.fromJson({
        'id': 'msg-1',
        'created_at': '2026-03-29T13:00:00Z',
        'text': 'Here you go',
        'sender': 'ai',
        'type': 'text',
        'plugin_id': null,
        'from_integration': false,
        'files': [],
        'files_id': [],
        'memories': [],
        'ask_for_nps': false,
        'ui_blocks': [
          {
            'type': 'map',
            'props': {
              'latitude': 40.7128,
              'longitude': -74.0060,
              'title': 'New York',
            },
          },
          {
            'type': 'action_buttons',
            'props': {
              'title': 'Quick actions',
              'buttons': ['Share location'],
            },
          },
        ],
      });

      expect(message.uiBlocks, hasLength(2));
      expect(message.uiBlocks.first.type, GenUiBlockType.map);
      expect(message.uiBlocks.last.type, GenUiBlockType.actionButtons);
      expect(message.uiBlocks.last.props['buttons'], ['Share location']);
    });
  });
}
