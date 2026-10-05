import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/device_tools/device_tool_surface.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const channel = MethodChannel('com.omi.device_tools');
  late List<MethodCall> calls;
  late Map<String, Object?> nextResponse;

  setUp(() {
    calls = [];
    nextResponse = {'ok': true};
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      channel,
      (call) async {
        calls.add(call);
        return nextResponse;
      },
    );
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel, null);
  });

  // `supported` is injected so these run identically on a desktop test host and
  // on a real device.
  DeviceToolSurface supportedSurface() => DeviceToolSurface(channel: channel, supported: true);
  DeviceToolSurface unsupportedSurface() => DeviceToolSurface(channel: channel, supported: false);

  group('tool descriptors', () {
    test('advertises no tools on an unsupported platform', () {
      expect(unsupportedSurface().tools, isEmpty);
    });

    test('advertises exactly the three mobile tools', () {
      expect(
        supportedSurface().tools.map((tool) => tool.name),
        [
          DeviceToolSurface.searchContactsTool,
          DeviceToolSurface.proposeMessageTool,
          DeviceToolSurface.requestPermissionTool,
        ],
      );
    });

    test('withholds propose_message on a device that cannot send text', () async {
      // A simulator, an iPod touch, or an iPad with no messaging service. The
      // model should never be offered a tool whose only possible answer is
      // messaging_unavailable.
      nextResponse = {'ok': true, 'can_send_text': false};

      final available = await supportedSurface().availableTools();

      expect(
        available.map((tool) => tool.name),
        [DeviceToolSurface.searchContactsTool, DeviceToolSurface.requestPermissionTool],
      );
    });

    test('offers all tools on a device that can send text', () async {
      nextResponse = {'ok': true, 'can_send_text': true};

      final available = await supportedSurface().availableTools();

      expect(
        available.map((tool) => tool.name),
        [
          DeviceToolSurface.searchContactsTool,
          DeviceToolSurface.proposeMessageTool,
          DeviceToolSurface.requestPermissionTool,
        ],
      );
    });

    test('advertises nothing on an unsupported platform without touching the channel', () async {
      expect(await unsupportedSurface().availableTools(), isEmpty);
      expect(calls, isEmpty);
    });

    test('marks propose_message as platform-confirmed and search_contacts as not', () {
      final tools = {for (final tool in supportedSurface().tools) tool.name: tool};

      expect(tools[DeviceToolSurface.proposeMessageTool]!.requiresUserConfirmation, isTrue);
      expect(tools[DeviceToolSurface.searchContactsTool]!.requiresUserConfirmation, isFalse);
    });

    test('describes propose_message as not sending on its own', () {
      final propose = supportedSurface().tools.firstWhere((tool) => tool.name == DeviceToolSurface.proposeMessageTool);

      expect(propose.description, contains('does not send on its own'));
      expect(propose.toJson()['input_schema'], containsPair('required', ['to', 'text']));
    });
  });

  group('execute', () {
    test('fails closed on an unsupported platform without touching the channel', () async {
      final result = await unsupportedSurface().execute('propose_message', {
        'to': ['+15550100'],
        'text': 'hi',
      });

      expect(result.ok, isFalse);
      expect(result.reason, 'unsupported_platform');
      expect(calls, isEmpty);
    });

    test('rejects a desktop-only tool instead of failing silently', () async {
      final result = await supportedSurface().execute('run_applescript', {'script': 'beep'});

      expect(result.ok, isFalse);
      expect(result.reason, 'unknown_tool');
      expect(calls, isEmpty);
    });

    test('rejects an empty recipient list before reaching the platform', () async {
      final result = await supportedSurface().execute('propose_message', {'to': <String>[], 'text': 'hi'});

      expect(result.ok, isFalse);
      expect(result.reason, 'empty_recipient');
      expect(calls, isEmpty);
    });

    test('rejects an empty body before reaching the platform', () async {
      final result = await supportedSurface().execute('propose_message', {
        'to': ['+15550100'],
        'text': '   ',
      });

      expect(result.ok, isFalse);
      expect(result.reason, 'empty_body');
      expect(calls, isEmpty);
    });

    test('normalizes a single-string recipient into a list', () async {
      nextResponse = {'ok': true, 'status': 'sent'};

      await supportedSurface().execute('propose_message', {'to': '+15550100', 'text': 'hi'});

      expect(calls.single.method, 'proposeMessage');
      expect(calls.single.arguments['to'], ['+15550100']);
    });

    test('drops blank entries from a recipient list', () async {
      nextResponse = {'ok': true, 'status': 'sent'};

      await supportedSurface().execute('propose_message', {
        'to': ['+15550100', '  ', ''],
        'text': 'hi',
      });

      expect(calls.single.arguments['to'], ['+15550100']);
    });

    test('reports a cancelled compose sheet as not ok', () async {
      nextResponse = {'ok': false, 'status': 'cancelled'};

      final result = await supportedSurface().execute('propose_message', {
        'to': ['+15550100'],
        'text': 'hi',
      });

      expect(result.ok, isFalse);
      expect(result.payload['status'], 'cancelled');
    });

    test('passes a trimmed contacts query through to the platform', () async {
      nextResponse = {'ok': true, 'contacts': <dynamic>[]};

      await supportedSurface().execute('search_contacts', {'query': '  Ada  ', 'limit': 5});

      expect(calls.single.method, 'searchContacts');
      expect(calls.single.arguments['query'], 'Ada');
      expect(calls.single.arguments['limit'], 5);
    });

    test('routes a contacts permission request to the native prompt', () async {
      nextResponse = {'ok': true, 'status': 'granted'};

      final result = await supportedSurface().execute('request_permission', {'type': 'contacts'});

      expect(calls.single.method, 'requestContactsPermission');
      expect(result.ok, isTrue);
      expect(result.payload['status'], 'granted');
    });

    test('rejects a permission type iOS cannot prompt for', () async {
      final result = await supportedSurface().execute('request_permission', {'type': 'calendars'});

      expect(result.ok, isFalse);
      expect(result.reason, 'unsupported_permission');
      expect(calls, isEmpty);
    });

    test('surfaces a missing native registration as a typed failure', () async {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel, null);

      final result = await supportedSurface().execute('search_contacts', {'query': 'Ada'});

      expect(result.ok, isFalse);
      expect(result.reason, 'surface_unavailable');
    });
  });

  group('failure shape', () {
    test('carries the follow-up permission request the model should make', () {
      final result = DeviceToolResult.failure(
        'authorization_denied',
        'Contacts access is required.',
        permission: 'contacts',
      );

      expect(result.requiredPermission, 'contacts');
      expect(result.payload['next_tool'], 'request_permission');
      expect(result.payload['next_tool_arguments'], {'type': 'contacts'});
    });

    test('omits permission hints when the failure is not a permission problem', () {
      final result = DeviceToolResult.failure('empty_body', 'Provide the message text.');

      expect(result.requiredPermission, isNull);
      expect(result.payload.containsKey('next_tool'), isFalse);
    });
  });
}
