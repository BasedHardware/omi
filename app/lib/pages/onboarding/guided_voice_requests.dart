import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;

import 'package:omi/backend/http/api/messages.dart' show parseMessageChunk;
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/streaming_error.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/env/env.dart';
import 'guided_voice_controller.dart';

/// Unlike the settings banner's fail-open probe, onboarding offers typing if
/// reachability, decoding or the existing read-only health signal fails.
/// This signals streaming STT configuration, not Android's batch POST health;
/// final batch failures must still offer clip retry and typing.
Future<bool> guidedVoicePreflight({ApiSend? probe, Duration timeout = const Duration(seconds: 4)}) async {
  var slow = false;
  try {
    final result = await executeApi<bool>(
      request: ApiRequest(url: '${Env.apiBaseUrl}v3/speech-profile/stt-availability', method: 'GET'),
      send: (request) async {
        try {
          return await (probe?.call(request) ??
              sendUncaughtApiCall(
                  url: request.url, method: request.method, headers: request.headers, body: request.body));
        } on TimeoutException {
          slow = true;
          rethrow;
        }
      },
      decode: (body) {
        final data = jsonDecode(body);
        if (data is! Map || data['available'] is! bool) throw const FormatException('Invalid availability');
        return data['available'] as bool;
      },
    ).timeout(timeout);
    return slow || (result is ApiSuccess<bool> && result.data);
  } on TimeoutException {
    return true; // Slow is not proof that transcription is unavailable.
  } catch (_) {
    return false;
  }
}

Future<String> transcribeGuidedAnswer(File file, String language, {Future<http.Response> Function()? upload}) async {
  final response = await (upload?.call() ??
          makeMultipartApiCallUnpooled(
            url: '${Env.apiBaseUrl}v2/voice-message/transcribe',
            files: [file],
            fields: {'language': language},
          ))
      .timeout(const Duration(seconds: 30));
  if (response.statusCode != 200) {
    throw const GuidedVoiceFailure('transcribe_http_error');
  }
  final text = (jsonDecode(response.body)['transcript'] as String? ?? '').trim();
  if (text.isEmpty) throw const GuidedVoiceFailure('transcribe_empty');
  return text;
}

/// Uses the normal persisted chat turn, with no provider/paywall UI. A fresh
/// account needs only auth; explicit saved facts avoid waiting for indexing.
/// Device tools are deliberately absent: onboarding must not open a compose or
/// permission sheet while producing this small receipt. Server quota remains
/// enforced; its error is handled by the deterministic summary.
Future<String> askGuidedPayoff(String question, List<String> savedAnswers,
    {Stream<String> Function(String)? stream,
    void Function()? onAccepted,
    ApiStreamingSeams? seams,
    Duration timeout = const Duration(seconds: 8)}) async {
  final body = jsonEncode({
    'text': '$question\n\n${savedAnswers.map((s) => '> ${s.replaceAll('\n', '\n> ')}').join('\n\n')}',
    'device_tools': <String>[],
  });
  final abort = Completer<void>();
  final client = http.Client();
  final abortTimer = Timer(timeout, () {
    if (!abort.isCompleted) abort.complete();
    client.close();
  });
  final lines = StreamIterator(stream?.call(body) ??
      makeStreamingApiCall(
        url: '${Env.apiBaseUrl}v2/messages',
        headers: const {'X-Omi-Chat-Failure-Protocol': '1'},
        body: body,
        seams: ApiStreamingSeams(
            headers: seams?.headers,
            auth: seams?.auth,
            transport: (request) async {
              if (abort.isCompleted) throw TimeoutException('Payoff deadline');
              final bounded = http.AbortableRequest(request.method, request.url, abortTrigger: abort.future)
                ..headers.addAll(request.headers)
                ..body = body;
              final response = await (seams?.transport(bounded) ?? client.send(bounded));
              if (response.statusCode == 200) onAccepted?.call();
              return response;
            }),
      ));
  final deadline = DateTime.now().add(timeout);
  try {
    while (await lines.moveNext().timeout(deadline.difference(DateTime.now()))) {
      final line = lines.current;
      if (line.trim().isEmpty || line.trimLeft().startsWith(':')) continue;
      if (line.startsWith('error:402:')) throw StateError('Chat unavailable');
      final chunk = parseMessageChunk(line, 'introduction');
      if (chunk == null) throw StateError('Invalid chat response');
      if (chunk.type == MessageChunkType.error && chunk.errorCode == 'timeout') {
        throw const ChatStreamException(ChatStreamFailureClass.timeout);
      }
      if (chunk.type == MessageChunkType.error || chunk.type == MessageChunkType.tool) {
        throw StateError('Chat unavailable');
      }
      // Accept only the server's persisted final answer, never a partial stream.
      if (chunk.type == MessageChunkType.done) return chunk.message?.text ?? '';
    }
    throw StateError('No completed chat answer');
  } finally {
    abortTimer.cancel();
    if (!abort.isCompleted) abort.complete();
    client.close();
    unawaited(lines.cancel());
  }
}
