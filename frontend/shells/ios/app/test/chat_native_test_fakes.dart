import 'dart:async';
import 'dart:convert';

import 'package:omi_webview_proto/chat_attachment_staging_host.dart';
import 'package:omi_webview_proto/chat_native_http.dart';

class FakeChatNativeHttpClient implements ChatNativeHttpClient {
  final List<FakeChatNativeHttpResponse> responses =
      <FakeChatNativeHttpResponse>[];
  final List<FakeChatNativeHttpRequest> requests =
      <FakeChatNativeHttpRequest>[];
  bool closed = false;

  @override
  Future<ChatNativeHttpRequest> openUrl(String method, Uri url) async {
    if (responses.isEmpty) throw StateError('no scripted response');
    final request = FakeChatNativeHttpRequest(
      method,
      url,
      responses.removeAt(0),
    );
    requests.add(request);
    return request;
  }

  @override
  void close({bool force = false}) {
    closed = true;
  }
}

class FakeChatNativeHttpRequest implements ChatNativeHttpRequest {
  FakeChatNativeHttpRequest(this.method, this.url, this.response);

  final String method;
  final Uri url;
  final FakeChatNativeHttpResponse response;
  final Map<String, String> headers = <String, String>{};
  bool followsRedirects = true;
  int declaredContentLength = -1;
  int bodyByteCount = 0;
  final List<int> capturedPrefix = <int>[];
  final List<int> capturedSuffix = <int>[];
  bool aborted = false;
  bool closed = false;

  @override
  set followRedirects(bool value) => followsRedirects = value;

  @override
  set contentLength(int value) => declaredContentLength = value;

  @override
  void setHeader(String name, Object value) =>
      headers[name.toLowerCase()] = value.toString();

  @override
  void add(List<int> bytes) {
    bodyByteCount += bytes.length;
    if (capturedPrefix.length < 4096) {
      final remaining = 4096 - capturedPrefix.length;
      capturedPrefix.addAll(bytes.take(remaining));
    }
    capturedSuffix.addAll(bytes);
    if (capturedSuffix.length > 4096) {
      capturedSuffix.removeRange(0, capturedSuffix.length - 4096);
    }
  }

  @override
  Future<ChatNativeHttpResponse> close() async {
    closed = true;
    return response;
  }

  @override
  void abort([Object? exception]) {
    aborted = true;
  }

  String get prefixText => utf8.decode(capturedPrefix, allowMalformed: true);
  String get suffixText => utf8.decode(capturedSuffix, allowMalformed: true);
}

class FakeChatNativeHttpResponse implements ChatNativeHttpResponse {
  FakeChatNativeHttpResponse({
    required this.statusCode,
    this.isRedirect = false,
    Stream<List<int>>? bytes,
  }) : bytes = bytes ?? const Stream<List<int>>.empty();

  @override
  final int statusCode;
  @override
  final bool isRedirect;
  @override
  final Stream<List<int>> bytes;
}

class FakePickedChatAttachment implements PickedChatAttachment {
  FakePickedChatAttachment({
    required this.sizeBytes,
    required this.stream,
    this.regular = true,
  });

  @override
  final int sizeBytes;
  final Stream<List<int>> stream;
  final bool regular;
  int openReadCalls = 0;
  int regularChecks = 0;

  @override
  Future<bool> isRegularFile() async {
    regularChecks += 1;
    return regular;
  }

  @override
  Stream<List<int>> openRead() {
    openReadCalls += 1;
    return stream;
  }
}

class FakeChatAttachmentPicker implements ChatAttachmentPicker {
  FakeChatAttachmentPicker(this.result);

  final PickedChatAttachment? result;
  int calls = 0;

  @override
  Future<PickedChatAttachment?> pickOne() async {
    calls += 1;
    return result;
  }
}

Future<void> waitFor(
  bool Function() predicate, {
  String reason = 'condition',
}) async {
  for (var attempt = 0; attempt < 200; attempt += 1) {
    if (predicate()) return;
    await Future<void>.delayed(Duration.zero);
  }
  throw StateError('timed out waiting for $reason');
}

Map<String, dynamic> parseSingleArgumentFrame(String source) {
  final open = source.indexOf('(');
  final close = source.lastIndexOf(');');
  final raw = jsonDecode(source.substring(open + 1, close)) as String;
  return jsonDecode(raw) as Map<String, dynamic>;
}

Map<String, dynamic> parseStagingReply(String source) {
  final open = source.indexOf('(');
  final close = source.lastIndexOf(');');
  final arguments = source.substring(open + 1, close);
  final comma = arguments.indexOf(',');
  final raw = jsonDecode(arguments.substring(comma + 1)) as String;
  return jsonDecode(raw) as Map<String, dynamic>;
}
