import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/agent_chat_service.dart';

void main() {
  test('agent websocket headers carry the device timezone when available', () {
    expect(buildAgentWebSocketHeaders(token: 'firebase-token', timeZone: ' America/New_York '), {
      'Authorization': 'Bearer firebase-token',
      'X-Timezone': 'America/New_York',
    });
  });

  test('agent websocket headers omit an unavailable timezone', () {
    expect(buildAgentWebSocketHeaders(token: 'firebase-token'), {'Authorization': 'Bearer firebase-token'});
  });

  test('agent query messages carry the current per-query timezone', () {
    expect(buildAgentQueryMessage(prompt: 'What year is it?', timeZone: ' America/Los_Angeles '), {
      'type': 'query',
      'prompt': 'What year is it?',
      'time_zone': 'America/Los_Angeles',
    });
  });

  test('agent query messages explicitly select UTC when timezone lookup fails', () {
    expect(buildAgentQueryMessage(prompt: 'What year is it?'), {
      'type': 'query',
      'prompt': 'What year is it?',
      'time_zone': '',
    });
  });

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
