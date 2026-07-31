import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/device_tools/device_tool_surface.dart';
import 'package:omi/utils/logger.dart';

/// One device tool request, as the backend announced it on the chat stream.
class DeviceToolRequest {
  const DeviceToolRequest({required this.callId, required this.tool, required this.arguments});

  final String callId;
  final String tool;
  final Map<String, dynamic> arguments;

  /// Returns null when the frame is not a well-formed request. A malformed
  /// frame is dropped rather than guessed at: executing a tool call whose
  /// arguments did not parse could send the wrong text to the wrong person.
  static DeviceToolRequest? tryParse(String raw) {
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map) return null;
      final callId = decoded['call_id'];
      final tool = decoded['tool'];
      if (callId is! String || callId.isEmpty) return null;
      if (tool is! String || tool.isEmpty) return null;
      final args = decoded['arguments'];
      return DeviceToolRequest(
        callId: callId,
        tool: tool,
        arguments: args is Map ? Map<String, dynamic>.from(args) : const {},
      );
    } on FormatException {
      return null;
    }
  }
}

/// Executes device tool requests arriving on the chat stream and returns the
/// results to the backend.
///
/// The turn stays open on the server while this runs, so the reply the user
/// eventually sees already accounts for what happened on the device — including
/// them cancelling the compose sheet.
class DeviceToolDispatcher {
  DeviceToolDispatcher({DeviceToolSurface? surface}) : _surface = surface ?? DeviceToolSurface();

  final DeviceToolSurface _surface;

  /// The tool names to declare when opening a chat turn. The backend offers the
  /// model only what appears here, so a device that cannot message never gets
  /// asked to.
  List<String> get declaredToolNames => _surface.tools.map((tool) => tool.name).toList();

  /// Handles one `tool:` frame end to end. Never throws: a failure here has to
  /// come back to the model as a result, or the turn hangs until the server's
  /// timeout.
  Future<void> handleFrame(String rawFrame) async {
    final request = DeviceToolRequest.tryParse(rawFrame);
    if (request == null) {
      Logger.error('Discarding malformed device tool frame');
      return;
    }

    DeviceToolResult result;
    try {
      result = await _surface.execute(request.tool, request.arguments);
    } catch (e) {
      result = DeviceToolResult.failure('execution_failed', e.toString());
    }

    await _postResult(request.callId, result);
  }

  Future<void> _postResult(String callId, DeviceToolResult result) async {
    try {
      final response = await makeApiCall(
        url: '${Env.apiBaseUrl}v2/messages/device-tool/$callId/result',
        headers: {'Content-Type': 'application/json'},
        method: 'POST',
        body: jsonEncode({'result': result.payload}),
      );
      if (response == null || response.statusCode != 200) {
        Logger.error('Device tool result rejected: status=${response?.statusCode}');
      }
    } catch (e) {
      // Nothing more to do — the server-side call times out on its own and the
      // model answers without the result rather than hanging forever.
      Logger.error('Could not deliver device tool result: $e');
    }
  }
}
