import 'dart:io';

import 'package:flutter/services.dart';

/// The mobile on-device tool surface.
///
/// Tool names and result shapes deliberately mirror the macOS desktop surface
/// (`search_contacts`, `propose_message`) so one model-facing contract covers
/// both platforms. What differs is the capability set, and that difference is
/// declared rather than discovered: iOS cannot send a message without the user
/// confirming it in the system compose sheet, and it cannot read message
/// history or run scripts at all.
///
/// Every result carries `ok`, and every failure carries `reason`. When the
/// failure is a missing permission the result also carries `permission` and
/// `next_tool`, matching what the desktop executors return so the model handles
/// both platforms identically.
class DeviceToolResult {
  const DeviceToolResult(this.payload);

  final Map<String, dynamic> payload;

  bool get ok => payload['ok'] == true;
  String? get reason => payload['reason'] as String?;
  String? get error => payload['error'] as String?;
  String? get requiredPermission => payload['permission'] as String?;

  static DeviceToolResult failure(String reason, String message, {String? permission}) {
    return DeviceToolResult({
      'ok': false,
      'reason': reason,
      'error': message,
      if (permission != null) 'permission': permission,
      if (permission != null) 'next_tool': 'request_permission',
      if (permission != null) 'next_tool_arguments': {'type': permission},
    });
  }
}

/// A tool the model may call on this device.
class DeviceToolDescriptor {
  const DeviceToolDescriptor({
    required this.name,
    required this.description,
    required this.parameters,
    required this.required,
    required this.requiresUserConfirmation,
  });

  final String name;
  final String description;
  final Map<String, Map<String, dynamic>> parameters;
  final List<String> required;

  /// True when the platform itself puts a confirmation UI in front of the
  /// effect. `propose_message` is the canonical case: the compose sheet is the
  /// approval, so the app must not add a second one.
  final bool requiresUserConfirmation;

  Map<String, dynamic> toJson() => {
        'name': name,
        'description': description,
        'input_schema': {
          'type': 'object',
          'properties': parameters,
          'required': required,
          'additionalProperties': false,
        },
        'requires_user_confirmation': requiresUserConfirmation,
      };
}

class DeviceToolSurface {
  DeviceToolSurface({MethodChannel? channel, bool? supported})
      : _channel = channel ?? const MethodChannel('com.omi.device_tools'),
        // Injectable so the iOS behaviour is exercised by tests running on a
        // desktop host, where `Platform.isIOS` would otherwise skip it.
        isSupported = supported ?? Platform.isIOS;

  final MethodChannel _channel;

  static const String searchContactsTool = 'search_contacts';
  static const String proposeMessageTool = 'propose_message';
  static const String requestPermissionTool = 'request_permission';

  /// iOS is the only mobile platform with a compose-sheet API and a Contacts
  /// store this surface can reach. Android would need its own implementations,
  /// so the surface reports empty there rather than advertising tools that
  /// would fail at call time.
  final bool isSupported;

  List<DeviceToolDescriptor> get tools {
    if (!isSupported) return const [];
    return const [
      DeviceToolDescriptor(
        name: searchContactsTool,
        description:
            'Resolve a person\'s name to their phone numbers and email addresses from the local Contacts store. Use before propose_message when the user names a person instead of giving a handle.',
        parameters: {
          'query': {'type': 'string', 'description': 'Name or partial name to search for.'},
          'limit': {'type': 'number', 'description': 'Maximum contacts to return (default 10, max 50).'},
        },
        required: ['query'],
        requiresUserConfirmation: false,
      ),
      DeviceToolDescriptor(
        name: proposeMessageTool,
        description:
            'Open the system message composer prefilled with a recipient and body. iOS requires the user to tap Send; the result reports whether they sent or cancelled. This does not send on its own.',
        parameters: {
          'to': {
            'type': 'array',
            'items': {'type': 'string'},
            'description': 'Recipient phone numbers or emails.',
          },
          'text': {'type': 'string', 'description': 'Exact message body to prefill.'},
          'subject': {'type': 'string', 'description': 'Optional subject, when the device supports it.'},
        },
        required: ['to', 'text'],
        requiresUserConfirmation: true,
      ),
      DeviceToolDescriptor(
        name: requestPermissionTool,
        description:
            'Ask the user for a device permission this turn needs. Call only when a tool result says next_tool=request_permission, and pass the type it named. On iOS the only supported type is contacts.',
        parameters: {
          'type': {'type': 'string', 'description': 'Which permission to ask for (iOS: contacts).'},
        },
        required: ['type'],
        requiresUserConfirmation: true,
      ),
    ];
  }

  /// The tools this specific device can actually run, as opposed to the ones
  /// the platform defines.
  ///
  /// `tools` describes iOS; this asks the device. A simulator, an iPod touch, or
  /// an iPad with no messaging service reports `can_send_text: false`, and
  /// offering `propose_message` there would send the model on a round trip that
  /// can only come back `messaging_unavailable`. The per-request contract says
  /// the client declares what it can run, so the check belongs here rather than
  /// in the model's error handling.
  Future<List<DeviceToolDescriptor>> availableTools() async {
    if (!isSupported) return const [];
    final capabilities = await this.capabilities();
    final canSendText = capabilities['can_send_text'] == true;
    return tools.where((tool) => tool.name != proposeMessageTool || canSendText).toList();
  }

  Future<Map<String, dynamic>> capabilities() async {
    if (!isSupported) {
      return {
        'can_send_text': false,
        'can_read_messages': false,
        'can_run_scripts': false,
        'requires_user_confirmation': true,
      };
    }
    final result = await _invoke('capabilities', null);
    return Map<String, dynamic>.from(result.payload);
  }

  /// Executes one tool call by name. Unknown names fail closed rather than
  /// silently doing nothing, so a model hallucinating a desktop-only tool such
  /// as `run_applescript` gets a result it can reason about.
  Future<DeviceToolResult> execute(String toolName, Map<String, dynamic> arguments) async {
    if (!isSupported) {
      return DeviceToolResult.failure(
        'unsupported_platform',
        'The on-device tool surface is only available on iOS.',
      );
    }

    switch (toolName) {
      case searchContactsTool:
        final query = (arguments['query'] as String?)?.trim() ?? '';
        if (query.isEmpty) {
          return DeviceToolResult.failure('missing_query', 'Provide a name to search for.');
        }
        return _invoke('searchContacts', {
          'query': query,
          if (arguments['limit'] != null) 'limit': arguments['limit'],
        });

      case requestPermissionTool:
        final type = (arguments['type'] as String?)?.trim() ?? '';
        if (type.isEmpty || type != 'contacts') {
          return DeviceToolResult.failure(
            'unsupported_permission',
            'iOS can only prompt for the contacts permission.',
          );
        }
        return requestContactsPermission();

      case proposeMessageTool:
        final recipients = _recipients(arguments['to']);
        if (recipients.isEmpty) {
          return DeviceToolResult.failure('empty_recipient', 'Provide at least one recipient.');
        }
        final text = (arguments['text'] as String?) ?? '';
        if (text.trim().isEmpty) {
          return DeviceToolResult.failure('empty_body', 'Provide the message text to propose.');
        }
        return _invoke('proposeMessage', {
          'to': recipients,
          'text': text,
          if (arguments['subject'] != null) 'subject': arguments['subject'],
        });

      default:
        return DeviceToolResult.failure(
          'unknown_tool',
          '$toolName is not available on this device.',
        );
    }
  }

  Future<DeviceToolResult> contactsPermissionStatus() => _invoke('contactsPermissionStatus', null);

  Future<DeviceToolResult> requestContactsPermission() => _invoke('requestContactsPermission', null);

  static List<String> _recipients(dynamic raw) {
    if (raw is String) return raw.trim().isEmpty ? const [] : [raw.trim()];
    if (raw is List) {
      return raw.map((entry) => entry.toString().trim()).where((entry) => entry.isNotEmpty).toList();
    }
    return const [];
  }

  Future<DeviceToolResult> _invoke(String method, Map<String, dynamic>? arguments) async {
    try {
      final raw = await _channel.invokeMethod<dynamic>(method, arguments);
      if (raw is Map) {
        return DeviceToolResult(Map<String, dynamic>.from(raw));
      }
      return DeviceToolResult({'ok': true, 'value': raw});
    } on PlatformException catch (e) {
      return DeviceToolResult.failure('platform_error', e.message ?? e.code);
    } on MissingPluginException {
      return DeviceToolResult.failure(
        'surface_unavailable',
        'The on-device tool surface is not registered in this build.',
      );
    }
  }
}
