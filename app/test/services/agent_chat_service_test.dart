import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/agent_chat_service.dart';

void main() {
  test('agent chat events preserve structured proxy error messages', () {
    expect(
      AgentChatEvent.textFrom({
        'type': 'error',
        'code': 'unavailable',
        'message': 'Please try again.',
      }),
      'Please try again.',
    );
  });

  test('preserves typed startup error fields', () {
    final event = AgentChatEvent.fromMessage(AgentChatEventType.error, {
      'type': 'error',
      'code': 'agent_vm_not_ready',
      'state': 'provisioning',
      'retryable': true,
      'message': 'Still starting',
    });

    expect(event.text, 'Still starting');
    expect(event.code, 'agent_vm_not_ready');
    expect(event.state, 'provisioning');
    expect(event.retryable, isTrue);
  });
}
