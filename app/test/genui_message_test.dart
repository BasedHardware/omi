import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/message.dart';
import 'package:omi/models/genui.dart';
import 'package:omi/pages/chat/widgets/genui_message_widget.dart';

void main() {
  test('parses message with genui payload', () {
    final message = ServerMessage.fromJson({
      'id': 'msg-1',
      'created_at': DateTime.utc(2024, 1, 1).toIso8601String(),
      'text': 'Fallback text',
      'sender': 'ai',
      'type': 'text',
      'plugin_id': null,
      'from_integration': false,
      'files': [],
      'files_id': [],
      'memories': [],
      'ask_for_nps': true,
      'rating': null,
      'genui': {
        'type': 'column',
        'children': [
          {'type': 'text', 'text': 'Hello'},
          {
            'type': 'button',
            'label': 'Share location',
            'action': {'type': 'share_location'},
          },
        ],
      },
    });

    expect(message.genUi, isNotNull);
    expect(message.genUi!.root.type, GenUiNodeType.column);
    expect(message.genUi!.root.children.length, 2);
  });

  testWidgets('renders genui text and button', (tester) async {
    final payload = GenUiPayload.tryParse({
      'type': 'column',
      'children': [
        {'type': 'text', 'text': 'Hello from GenUI'},
        {
          'type': 'button',
          'label': 'Share location',
          'action': {'type': 'share_location'},
        },
      ],
    });

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: GenUiMessageWidget(
            payload: payload!,
            sendMessage: (_) {},
          ),
        ),
      ),
    );

    expect(find.text('Hello from GenUI'), findsOneWidget);
    expect(find.text('Share location'), findsOneWidget);
  });
}
