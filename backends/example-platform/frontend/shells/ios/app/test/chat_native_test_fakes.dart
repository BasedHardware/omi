import 'dart:async';
import 'dart:convert';

import 'package:omi_webview_proto/chat_attachment_staging_host.dart';
import 'package:omi_webview_proto/chat_native_http.dart';

class FakeChatNativeHttpClient implements ChatNativeHttpClient {
  final List<FakeChatNativeHttpResponse> responses = <FakeChatNativeHttpResponse>[];
  final List<FakeChatNativeHttpRequest> requests = <FakeChatNativeHttpRequest>[];
  bool closed = false;
  bool demandGatedRequests = false;

  @override
  Future<ChatNativeHttpRequest> openUrl(String method, Uri url) async {
    if (responses.isEmpty) throw StateError('no scripted response');
    final request = FakeChatNativeHttpRequest(method, url, responses.removeAt(0), demandGated: demandGatedRequests);
    requests.add(request);
    return request;
  }

  @override
  void close({bool force = false}) {
    closed = true;
  }
}

class FakeChatNativeHttpRequest implements ChatNativeHttpRequest {
  FakeChatNativeHttpRequest(this.method, this.url, this.response, {this.demandGated = false});

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
  final bool demandGated;
  int streamedChunks = 0;
  StreamSubscription<List<int>>? _bodySubscription;
  Completer<void>? _bodyDone;
  Completer<void>? _demandRelease;

  @override
  set followRedirects(bool value) => followsRedirects = value;

  @override
  set contentLength(int value) => declaredContentLength = value;

  @override
  void setHeader(String name, Object value) => headers[name.toLowerCase()] = value.toString();

  @override
  void add(List<int> bytes) {
    _record(bytes);
  }

  void _record(List<int> bytes) {
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
  Future<void> addStream(Stream<List<int>> stream) async {
    final done = Completer<void>();
    _bodyDone = done;
    late final StreamSubscription<List<int>> subscription;
    subscription = stream.listen(
      (chunk) {
        subscription.pause();
        streamedChunks += 1;
        _record(chunk);
        if (demandGated) {
          final release = Completer<void>();
          _demandRelease = release;
          unawaited(
            release.future.then((_) {
              if (!aborted) subscription.resume();
            }),
          );
        } else {
          subscription.resume();
        }
      },
      onError: (Object error, StackTrace stack) {
        if (!done.isCompleted) done.completeError(error, stack);
      },
      onDone: () {
        if (!done.isCompleted) done.complete();
      },
      cancelOnError: true,
    );
    _bodySubscription = subscription;
    try {
      await done.future;
    } finally {
      await subscription.cancel();
      _bodySubscription = null;
      _bodyDone = null;
      _demandRelease = null;
    }
  }

  void releaseDemand() {
    final release = _demandRelease;
    if (release != null && !release.isCompleted) release.complete();
  }

  @override
  Future<ChatNativeHttpResponse> close() async {
    closed = true;
    return response;
  }

  @override
  void abort([Object? exception]) {
    aborted = true;
    unawaited(_bodySubscription?.cancel());
    final done = _bodyDone;
    if (done != null && !done.isCompleted) {
      done.completeError(exception ?? StateError('aborted'));
    }
    releaseDemand();
  }

  String get prefixText => utf8.decode(capturedPrefix, allowMalformed: true);
  String get suffixText => utf8.decode(capturedSuffix, allowMalformed: true);
}

class FakeChatNativeHttpResponse implements ChatNativeHttpResponse {
  FakeChatNativeHttpResponse({
    required this.statusCode,
    required this.contentType,
    this.isRedirect = false,
    Map<String, String>? headers,
    Stream<List<int>>? bytes,
  }) : _headers = <String, String>{...?headers?.map((key, value) => MapEntry(key.toLowerCase(), value))},
       bytes = bytes ?? const Stream<List<int>>.empty();

  @override
  final int statusCode;
  @override
  final bool isRedirect;
  @override
  final String? contentType;
  final Map<String, String> _headers;
  @override
  String? header(String name) => _headers[name.toLowerCase()];
  @override
  final Stream<List<int>> bytes;
}

class FakePickedChatAttachment implements PickedChatAttachment {
  FakePickedChatAttachment({required this.sizeBytes, required this.stream, this.regular = true});

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

Future<void> waitFor(bool Function() predicate, {String reason = 'condition'}) async {
  for (var attempt = 0; attempt < 200; attempt += 1) {
    if (predicate()) return;
    await Future<void>.delayed(Duration.zero);
  }
  throw StateError('timed out waiting for $reason');
}

Map<String, dynamic> parseSingleArgumentFrame(String source) {
  final function = source.indexOf('__omiStreamFrame(');
  final open = source.indexOf('(', function);
  final close = source.indexOf(');', open);
  final raw = jsonDecode(source.substring(open + 1, close)) as String;
  return jsonDecode(raw) as Map<String, dynamic>;
}

Map<String, dynamic> parseStagingReply(String source) {
  final function = source.indexOf('__omiChatAttachmentStagingReply(');
  final open = source.indexOf('(', function);
  final close = source.indexOf(');', open);
  final arguments = source.substring(open + 1, close);
  final comma = arguments.indexOf(',');
  final raw = jsonDecode(arguments.substring(comma + 1)) as String;
  return jsonDecode(raw) as Map<String, dynamic>;
}
