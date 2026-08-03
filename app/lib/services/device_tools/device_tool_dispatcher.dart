import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/preferences.dart';
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

  /// The call id alone, recovered from a frame too malformed to execute.
  ///
  /// Refusing to run such a frame is right; staying silent about it is not.
  /// The server is blocked on this call id, so when the id itself survived we
  /// answer with a failure instead of making the user wait out the timeout.
  static String? recoverCallId(String raw) {
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map) return null;
      final callId = decoded['call_id'];
      return callId is String && callId.isNotEmpty ? callId : null;
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
  DeviceToolDispatcher({DeviceToolSurface? surface, String Function()? currentOwnerUid})
      : _surface = surface ?? DeviceToolSurface(),
        // Injectable so the account-change path is exercised in tests without a
        // real sign-out.
        _currentOwnerUid = currentOwnerUid ?? (() => SharedPreferencesUtil().uid);

  final DeviceToolSurface _surface;
  final String Function() _currentOwnerUid;

  /// The tool names to declare when opening a chat turn. The backend offers the
  /// model only what appears here, so a device that cannot message never gets
  /// asked to.
  ///
  /// Asynchronous because it asks the device what it can do rather than assuming
  /// the platform's full capability set.
  Future<List<String>> declaredToolNames() async {
    final available = await _surface.availableTools();
    return available.map((tool) => tool.name).toList();
  }

  /// Handles one `tool:` frame end to end. Never throws: a failure here has to
  /// come back to the model as a result, or the turn hangs until the server's
  /// timeout.
  Future<void> handleFrame(String rawFrame) async {
    final request = DeviceToolRequest.tryParse(rawFrame);
    if (request == null) {
      // The frame will not execute, but the server is still blocked on it. When
      // the call id survived the damage, say so; otherwise there is no address
      // to answer and the server's own timeout is the only way out.
      final callId = DeviceToolRequest.recoverCallId(rawFrame);
      if (callId == null) {
        Logger.error('Discarding malformed device tool frame with no recoverable call id');
        return;
      }
      Logger.error('Rejecting malformed device tool frame call_id=$callId');
      await _postResult(
        callId,
        DeviceToolResult.failure('malformed_request', 'The device could not read this tool call.'),
      );
      return;
    }

    // The effect and its result must both belong to the account that opened the
    // turn. A sheet can stay open across a sign-out or an account switch, and
    // posting the outcome afterwards would attribute it to whoever is signed in
    // now — or fail, leaving the original turn to time out on a message that may
    // well have been sent.
    final owner = _currentOwnerUid();

    DeviceToolResult result;
    try {
      result = await _executeWithOwnerBoundary(request.tool, request.arguments, owner);
    } catch (e) {
      result = DeviceToolResult.failure('execution_failed', e.toString());
    }

    if (_currentOwnerUid() != owner) {
      Logger.error('Dropping device tool result after an account change call_id=${request.callId}');
      return;
    }

    await _postResult(request.callId, result);
  }

  Future<DeviceToolResult> _executeWithOwnerBoundary(
    String tool,
    Map<String, dynamic> arguments,
    String? owner,
  ) async {
    final execution = _surface.execute(tool, arguments);
    while (true) {
      final completed = await Future.any<Object?>([
        execution,
        Future<Object?>.delayed(const Duration(milliseconds: 100)),
      ]);
      if (completed is DeviceToolResult) return completed;
      if (_currentOwnerUid() == owner) continue;
      try {
        await _surface.cancelPendingInteraction();
      } catch (error) {
        Logger.error('Could not cancel device tool after an account change: $error');
      }
      return await execution;
    }
  }

  Future<void> _postResult(String callId, DeviceToolResult result) async {
    try {
      final response = await makeApiCall(
        url: '${Env.apiBaseUrl}v2/messages/device-tool/$callId/result',
        headers: {'Content-Type': 'application/json'},
        method: 'POST',
        body: jsonEncode({'result': result.payload}),
        timeout: const Duration(seconds: 10),
        retries: 0,
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
