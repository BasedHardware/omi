import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/agent_chat_service.dart';

void main() {
  test('agent chat events preserve structured proxy error messages', () {
    expect(
      AgentChatEvent.textFrom({'type': 'error', 'code': 'unavailable', 'message': 'Please try again.'}),
      'Please try again.',
    );
  });
}
