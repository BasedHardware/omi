import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_timezone/flutter_timezone.dart';
import 'package:http/http.dart' as http;

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/gen/messages_wire.g.dart' as wire;
import 'package:omi/backend/schema/message.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/chat_video_sampler.dart';
import 'package:omi/services/device_tools/device_tool_dispatcher.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/off_ui_isolate.dart';
import 'package:omi/utils/other/string_utils.dart';
import 'package:path/path.dart' as p;

/// Hard-scope payload for POST /v2/messages `context` (#4515).
class ChatPageContext {
  final String type;
  final String? id;
  final String? title;
  final String? startDate;
  final String? endDate;

  const ChatPageContext({
    required this.type,
    this.id,
    this.title,
    this.startDate,
    this.endDate,
  });

  Map<String, dynamic> toJson() => {
        'type': type,
        if (id != null) 'id': id,
        if (title != null) 'title': title,
        if (startDate != null) 'start_date': startDate,
        if (endDate != null) 'end_date': endDate,
      };

  ChatPageContext copyWith({
    String? type,
    String? id,
    String? title,
    String? startDate,
    String? endDate,
    bool clearDates = false,
  }) {
    return ChatPageContext(
      type: type ?? this.type,
      id: id ?? this.id,
      title: title ?? this.title,
      startDate: clearDates ? null : (startDate ?? this.startDate),
      endDate: clearDates ? null : (endDate ?? this.endDate),
    );
  }
}

const messageHistoryBackgroundParseBytes = 64 * 1024;

List<ServerMessage> decodeMessageHistory(String body) => (jsonDecode(body) as List<dynamic>)
    .map((message) => ServerMessage.fromGeneratedWireJson(message as Map<String, dynamic>))
    .toList();

@visibleForTesting
List<ServerMessage> Function(String) messageHistoryDecoder = decodeMessageHistory;

Future<List<ServerMessage>> parseMessageHistory(String body) {
  final decoder = messageHistoryDecoder;
  return offUiIsolate(
    () => decoder(body),
    size: body.length,
    threshold: messageHistoryBackgroundParseBytes,
    debugName: 'message_history_parse',
  );
}

Future<List<ServerMessage>> getMessagesServer({
  String? appId,
  bool dropdownSelected = false,
  int limit = 100,
  int offset = 0,
}) async {
  if (appId == 'no_selected') appId = null;
  var response = await makeApiCall(
    url:
        '${Env.apiBaseUrl}v2/messages?app_id=${appId ?? ''}&dropdown_selected=$dropdownSelected&limit=$limit&offset=$offset',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return [];
  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    var messages = await parseMessageHistory(body);
    if (messages.isEmpty) {
      return [];
    }
    Logger.debug('getMessages length: ${messages.length}');
    // Debug: Check if any messages have ratings
    var ratedMessages = messages.where((m) => m.rating != null).toList();
    if (ratedMessages.isNotEmpty) {
      Logger.debug('📊 Messages with ratings: ${ratedMessages.length}');
      for (var m in ratedMessages) {
        Logger.debug('  - Message ${m.id}: rating=${m.rating}');
      }
    }
    return messages;
  }
  return [];
}

Future<List<ServerMessage>> clearChatServer({String? appId, String? chatSessionId}) async {
  if (appId == 'no_selected') appId = null;
  var response = await makeApiCall(
    url:
        '${Env.apiBaseUrl}v2/messages?app_id=${appId ?? ''}${chatSessionId == null ? '' : '&chat_session_id=${Uri.encodeQueryComponent(chatSessionId)}'}',
    headers: {},
    method: 'DELETE',
    body: '',
  );
  if (response == null) throw Exception('Failed to delete chat');
  if (response.statusCode == 200) {
    return [ServerMessage.fromGeneratedWireJson(jsonDecode(response.body) as Map<String, dynamic>)];
  } else {
    throw Exception('Failed to delete chat');
  }
}

const String chatStreamTimeoutFrameText = 'The response took too long. Please try again.';

ServerMessageChunk? parseMessageChunk(String line, String messageId) {
  if (line == 'memory: saved' || line == 'memory: updated') {
    return ServerMessageChunk(messageId, line.substring('memory: '.length), MessageChunkType.memory);
  }
  if (line.startsWith('error: ')) {
    final payload = line.substring('error: '.length).trim();
    Object? decoded;
    try {
      decoded = jsonDecode(payload);
    } on FormatException {
      decoded = null;
    }
    if (decoded is Map) {
      final message = decoded['message'];
      final code = decoded['error'];
      if (message is String && message.trim().isNotEmpty) {
        return ServerMessageChunk(
          messageId,
          message,
          MessageChunkType.error,
          errorCode: code is String ? code : null,
        );
      }
      if (code is String) {
        return ServerMessageChunk(messageId, payload, MessageChunkType.error, errorCode: code);
      }
      return ServerMessageChunk.failedMessage();
    }
    if (payload == chatStreamTimeoutFrameText) {
      return ServerMessageChunk(messageId, payload, MessageChunkType.error, errorCode: 'timeout');
    }
    return ServerMessageChunk(
      messageId,
      payload.isEmpty ? ServerMessageChunk.failedMessage().text : payload,
      MessageChunkType.error,
    );
  }

  if (line.startsWith('think: ')) {
    return ServerMessageChunk(messageId, line.substring(7).replaceAll("__CRLF__", "\n"), MessageChunkType.think);
  }

  if (line.startsWith('data: ')) {
    return ServerMessageChunk(messageId, line.substring(6).replaceAll("__CRLF__", "\n"), MessageChunkType.data);
  }

  // A device tool request. Base64 because the payload carries arbitrary message
  // text that must not be parsed as part of the line-delimited SSE grammar.
  //
  // A frame that will not decode yields an empty payload rather than throwing.
  // decodeBase64 throwing here would tear down the whole stream mid-turn, so a
  // single corrupt frame would cost the user the entire reply instead of one
  // tool call; the dispatcher fails that call closed on its own.
  if (line.startsWith('tool: ')) {
    String payload;
    try {
      payload = decodeBase64(line.substring(6));
    } catch (e) {
      Logger.error('Discarding undecodable device tool frame: $e');
      payload = '';
    }
    return ServerMessageChunk(messageId, payload, MessageChunkType.tool);
  }

  if (line.startsWith('done: ')) {
    var text = decodeBase64(line.substring(6));
    return ServerMessageChunk(
      messageId,
      text,
      MessageChunkType.done,
      message: ServerMessage.fromResponseJson(json.decode(text)),
    );
  }

  if (line.startsWith('message: ')) {
    var text = decodeBase64(line.substring(9));
    return ServerMessageChunk(
      messageId,
      text,
      MessageChunkType.message,
      message: ServerMessage.fromResponseJson(json.decode(text)),
    );
  }

  return null;
}

/// Decodes voice-message-specific terminal SSE errors.
///
/// The voice endpoint emits typed transcription failures as
/// `error: {"message":"..."}` while quota failures keep their legacy
/// `error:402:<body>` shape. Never surface a malformed server frame directly:
/// return the established generic error chunk instead.
ServerMessageChunk? parseVoiceMessageStreamChunk(String line, String messageId) {
  if (line.startsWith('error:402:')) {
    return ServerMessageChunk(messageId, line.substring('error:402:'.length), MessageChunkType.error,
        errorCode: 'quota_exceeded');
  }

  if (line.startsWith('error: ')) {
    try {
      final payload = jsonDecode(line.substring('error: '.length));
      if (payload is! Map) return ServerMessageChunk.failedMessage();

      final message = payload['message'];
      if (message is! String || message.trim().isEmpty) return ServerMessageChunk.failedMessage();
      final errorCode = payload['error'];

      return ServerMessageChunk(
        messageId,
        message,
        MessageChunkType.error,
        errorCode: errorCode is String ? errorCode : null,
      );
    } on FormatException {
      return ServerMessageChunk.failedMessage();
    }
  }

  return parseMessageChunk(line, messageId);
}

bool _isIgnorableStreamFrame(String line) => line.trim().isEmpty || line.trimLeft().startsWith(':');

Stream<ServerMessageChunk> sendMessageStreamServer(
  String text, {
  String? appId,
  List<String>? filesId,
  ChatPageContext? context,
  String? chatSessionId,
  ApiStreamingSeams? seams,
  Future<void>? cancelSignal,
}) async* {
  var url = '${Env.apiBaseUrl}v2/messages?app_id=$appId';
  if (appId == null || appId.isEmpty || appId == 'null' || appId == 'no_selected') {
    url = '${Env.apiBaseUrl}v2/messages';
  }

  if (chatSessionId != null) {
    url += '${url.contains('?') ? '&' : '?'}chat_session_id=${Uri.encodeQueryComponent(chatSessionId)}';
  }

  var messageId = "1000"; // Default new message
  String? deviceTimeZone;
  try {
    deviceTimeZone = (await FlutterTimezone.getLocalTimezone()).identifier;
  } catch (_) {
    // Omit time_zone when device timezone is unavailable so chat send is not blocked.
  }
  final dispatcher = DeviceToolDispatcher();
  final body = <String, dynamic>{
    'text': text,
    'file_ids': filesId,
    'device_tools': await dispatcher.declaredToolNames(),
    if (deviceTimeZone != null) 'time_zone': deviceTimeZone,
    if (context != null) 'context': context.toJson(),
  };

  await for (var line in makeStreamingApiCall(
    url: url,
    headers: const {'X-Omi-Chat-Failure-Protocol': '1'},
    body: jsonEncode(body),
    seams: seams,
    cancelSignal: cancelSignal,
  )) {
    if (_isIgnorableStreamFrame(line)) continue;
    if (line.startsWith('error:402:')) {
      yield ServerMessageChunk(messageId, line.substring('error:402:'.length), MessageChunkType.error,
          errorCode: 'quota_exceeded');
      return;
    }
    var messageChunk = parseMessageChunk(line, messageId);
    if (messageChunk != null) {
      // A device tool request is handled here rather than surfaced to the chat
      // UI: the server is still waiting on this turn, and the visible result is
      // the reply it produces once the tool comes back.
      if (messageChunk.type == MessageChunkType.tool) {
        await dispatcher.handleFrame(messageChunk.text);
        continue;
      }
      yield messageChunk;
    } else {
      yield ServerMessageChunk.failedMessage();
      return;
    }
  }
}

Future<ServerMessage> getInitialAppMessage(String? appId) {
  return makeApiCall(
    url: '${Env.apiBaseUrl}v2/initial-message?app_id=$appId',
    headers: {},
    method: 'POST',
    body: '',
  ).then((response) {
    if (response == null) throw Exception('Failed to send message');
    if (response.statusCode == 200) {
      return ServerMessage.fromGeneratedWireJson(jsonDecode(response.body) as Map<String, dynamic>);
    } else {
      throw Exception('Failed to send message');
    }
  });
}

Stream<ServerMessageChunk> sendVoiceMessageStreamServer(List<File> files,
    {String? language, ApiStreamingSeams? seams, Future<void>? abort}) async* {
  var messageId = "1000"; // Default new message

  await for (var line in makeMultipartStreamingApiCall(
    url: '${Env.apiBaseUrl}v2/voice-messages',
    files: files,
    fields: language != null ? {'language': language} : {},
    seams: seams,
    abort: abort,
  )) {
    if (_isIgnorableStreamFrame(line)) continue;
    var messageChunk = parseVoiceMessageStreamChunk(line, messageId);
    if (messageChunk != null) {
      yield messageChunk;
      if (messageChunk.type == MessageChunkType.error) return;
    } else {
      yield ServerMessageChunk.failedMessage();
      return;
    }
  }
}

String _filesUrl(String path, String? appId) {
  if (appId == null || appId.isEmpty || appId == 'null' || appId == 'no_selected') {
    return '${Env.apiBaseUrl}$path';
  }
  return '${Env.apiBaseUrl}$path?app_id=$appId';
}

/// Uploads chat attachments; one result per file, in the order given.
///
/// Videos are sampled on device (frames + audio → `/v2/files/video`) so the clip itself is
/// not uploaded; when the platform can't sample one, the clip goes to `/v2/files` and the
/// server samples it.
Future<List<MessageFile>?> uploadFilesServer(List<File> files, {String? appId}) async {
  if (!files.any((f) => isChatVideo(f.path))) return _uploadFilesBatch(files, appId: appId);
  final results = List<MessageFile?>.filled(files.length, null);
  final others = [
    for (var i = 0; i < files.length; i++)
      if (!isChatVideo(files[i].path)) i
  ];
  // The quick batch first: if it fails, no video has been stored yet.
  if (others.isNotEmpty) {
    final uploaded = await _uploadFilesBatch([for (final i in others) files[i]], appId: appId);
    if (uploaded == null || uploaded.length != others.length) {
      throw Exception('Failed to upload file');
    }
    for (var k = 0; k < others.length; k++) {
      results[others[k]] = uploaded[k];
    }
  }
  for (var i = 0; i < files.length; i++) {
    if (results[i] == null) results[i] = await uploadVideoServer(files[i], appId: appId);
  }
  return results.cast<MessageFile>();
}

Future<MessageFile> uploadVideoServer(File video, {String? appId}) async {
  final sampled = await ChatVideoSampler.sample(video);
  if (sampled == null) {
    final whole = await _uploadFilesBatch([video], appId: appId);
    if (whole == null || whole.isEmpty) throw Exception('Failed to upload video');
    return whole.first;
  }
  try {
    final response = await makeMultipartApiCall(
      url: _filesUrl('v2/files/video', appId),
      files: sampled.frames,
      fileFieldName: 'frames',
      fields: {
        'frame_times': jsonEncode(sampled.times),
        'duration_seconds': sampled.duration.toString(),
        'name': p.basename(video.path),
      },
      namedFiles: {if (sampled.audio != null) 'audio': sampled.audio!},
    );
    if (response.statusCode != 200) {
      Logger.debug('Failed to upload video frames. Status code: ${response.statusCode}');
      throw Exception('Failed to upload video. Status code: ${response.statusCode}');
    }
    final stored = (jsonDecode(response.body) as List<dynamic>)
        .map((file) => MessageFile.fromGenerated(wire.GeneratedFileChat.fromJson(file as Map<String, dynamic>)))
        .first;
    stored.localPreviewPath = await _keepPosterFrame(sampled.frames, stored.id);
    return stored;
  } finally {
    await sampled.dispose();
  }
}

/// Copies the clip's first sampled frame out of the sampler's temp directory, which
/// [SampledChatVideo.dispose] deletes, so the sent bubble can show it as the preview.
Future<String?> _keepPosterFrame(List<File> frames, String fileId) async {
  if (frames.isEmpty) return null;
  try {
    final directory = Directory(p.join(Directory.systemTemp.path, 'omi-chat-video-posters'));
    await directory.create(recursive: true);
    final safeId = fileId.replaceAll(RegExp(r'[^A-Za-z0-9_-]'), '_');
    final poster = await frames.first.copy(p.join(directory.path, '$safeId.jpg'));
    return poster.path;
  } catch (e) {
    Logger.debug('Could not keep the video poster frame: $e');
    return null;
  }
}

Future<List<MessageFile>?> _uploadFilesBatch(List<File> files, {String? appId}) async {
  final url = _filesUrl('v2/files', appId);

  try {
    var response = await makeMultipartApiCall(url: url, files: files);

    if (response.statusCode == 200) {
      Logger.debug('uploadFileServer response body: ${response.body}');
      return (jsonDecode(response.body) as List<dynamic>)
          .map((file) => MessageFile.fromGenerated(wire.GeneratedFileChat.fromJson(file as Map<String, dynamic>)))
          .toList();
    } else {
      Logger.debug('Failed to upload file. Status code: ${response.statusCode} ${response.body}');
      throw Exception('Failed to upload file. Status code: ${response.statusCode}');
    }
  } catch (e) {
    Logger.debug('An error occurred uploadFileServer: $e');
    throw Exception('An error occurred uploadFileServer: $e');
  }
}

Future reportMessageServer(String messageId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v2/messages/$messageId/report',
    headers: {},
    method: 'POST',
    body: '',
  );
  if (response == null) throw Exception('Failed to report message');
  if (response.statusCode != 200) {
    throw Exception('Failed to report message');
  }
  wire.GeneratedMessageReportResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
}

/// A voice-message transcription failure with the server's HTTP status, so the caller can
/// log what failed and tell a server fault from a bad clip. The body is not read: the status
/// carries the distinction, and response bodies decode only through generated models.
class VoiceTranscriptionException implements Exception {
  final int? statusCode;
  final String? outcome;
  final bool? retryable;
  final String? cause;

  const VoiceTranscriptionException({this.statusCode, this.outcome, this.retryable, this.cause});

  /// A 5xx or 429: the fault is ours, the recording is fine and a later retry may work.
  /// No response (offline) is not reported as our fault.
  bool get isServerSide => statusCode != null && (statusCode! >= 500 || statusCode == 429);

  @override
  String toString() => 'VoiceTranscriptionException(status: $statusCode, outcome: $outcome, retryable: $retryable'
      '${cause == null ? '' : ', cause: $cause'})';
}

/// Transcribe audio files sequentially (one request per file) to stay under
/// Cloud Run's 32 MB request-body limit.  Transcripts are concatenated
/// client-side with a space separator — same behaviour as the backend's
/// multi-file mode but without a single oversized upload.
Future<String> transcribeVoiceMessage(List<File> audioFiles, {String? language}) async {
  final transcripts = <String>[];

  for (final file in audioFiles) {
    final http.Response response;
    try {
      response = await makeMultipartApiCallUnpooled(
        url: '${Env.apiBaseUrl}v2/voice-message/transcribe',
        files: [file],
        fields: language != null ? {'language': language} : {},
      );
    } catch (e) {
      throw VoiceTranscriptionException(cause: e.runtimeType.toString());
    }
    if (response.statusCode != 200) throw VoiceTranscriptionException(statusCode: response.statusCode);

    final data = wire.GeneratedVoiceMessageTranscriptionResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
    final transcript = data.transcript;
    if (transcript.isNotEmpty) {
      transcripts.add(transcript);
    }
  }

  final transcript = transcripts.join(' ').trim();
  if (transcript.isEmpty) {
    throw const VoiceTranscriptionException(statusCode: 200, outcome: 'empty_transcript', retryable: false);
  }
  return transcript;
}
