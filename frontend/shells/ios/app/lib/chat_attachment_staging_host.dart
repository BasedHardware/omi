import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:file_picker/file_picker.dart';
import 'package:webview_flutter/webview_flutter.dart';

import 'bridge_http_host.dart';
import 'chat_bridge_javascript_sink.dart';
import 'chat_native_http.dart';
import 'gen/bridge_http_contract.g.dart';

const int _maxSafeInteger = 9007199254740991;
const int _maxResponseBytes = 16 * 1024;
const int maxChatAttachmentBytes = 50 * 1024 * 1024;
final RegExp _safeOpaque = RegExp(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$');
final RegExp _safeMime = RegExp(r"^[!#\$%&'*+.^_`|~0-9A-Za-z-]+/[!#\$%&'*+.^_`|~0-9A-Za-z-]+$");
final RegExp _canonicalExpiry = RegExp(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$');

abstract interface class ChatAttachmentPicker {
  Future<PickedChatAttachment?> pickOne();
}

abstract interface class PickedChatAttachment {
  int get sizeBytes;
  Future<bool> isRegularFile();
  Stream<List<int>> openRead();
}

class FilePickerChatAttachmentPicker implements ChatAttachmentPicker {
  const FilePickerChatAttachmentPicker();

  @override
  Future<PickedChatAttachment?> pickOne() async {
    final result = await FilePicker.platform.pickFiles(allowMultiple: false, withData: false, withReadStream: false);
    if (result == null) return null;
    if (result.files.length != 1 || result.files.single.path == null) {
      throw const FileSystemException('picker did not return exactly one local file');
    }
    return LocalPickedChatAttachment(result.files.single.path!, result.files.single.size);
  }
}

class LocalPickedChatAttachment implements PickedChatAttachment {
  LocalPickedChatAttachment(String path, this.sizeBytes) : _file = File(path);

  final File _file;

  @override
  final int sizeBytes;

  @override
  Future<bool> isRegularFile() async => (await _file.stat()).type == FileSystemEntityType.file;

  @override
  Stream<List<int>> openRead() => _file.openRead();
}

class ChatAttachmentStagingHost {
  ChatAttachmentStagingHost({
    required this.baseUrl,
    required this.custody,
    required this.clientIdentity,
    required this.sink,
    ChatAttachmentPicker? picker,
    ChatNativeHttpClient? httpClient,
    String Function()? boundaryFactory,
  }) : _picker = picker ?? const FilePickerChatAttachmentPicker(),
       _httpClient = httpClient ?? DartIoChatNativeHttpClient(),
       _boundaryFactory = boundaryFactory ?? _randomBoundary;

  final Uri baseUrl;
  final ShellCredentialCustody custody;
  final String? clientIdentity;
  final ChatBridgeJavaScriptSink sink;
  final ChatAttachmentPicker _picker;
  final ChatNativeHttpClient _httpClient;
  final String Function() _boundaryFactory;

  bool _registered = false;
  bool _closed = false;
  int _documentEpoch = 0;
  _StagingOperation? _operation;

  static String _randomBoundary() {
    final random = Random.secure();
    final suffix = List<int>.generate(24, (_) => random.nextInt(16)).map((value) => value.toRadixString(16)).join();
    return 'omi-chat-$suffix';
  }

  Future<void> register(WebViewController controller) {
    if (_registered) return Future<void>.value();
    _registered = true;
    return controller.addJavaScriptChannel(
      ChatAttachmentStagingContract.channel,
      onMessageReceived: (JavaScriptMessage message) {
        unawaited(handleMessage(message.message));
      },
    );
  }

  Future<void> handleMessage(String raw) async {
    if (_closed) return;
    dynamic decoded;
    try {
      decoded = jsonDecode(raw);
    } on FormatException {
      return;
    }
    if (decoded is! Map<String, dynamic>) return;
    final id = decoded['id'];
    if (id is! String || !_safeOpaque.hasMatch(id)) return;
    if (decoded.length != ChatAttachmentStagingContract.requestFields.length ||
        !decoded.keys.every(ChatAttachmentStagingContract.requestFields.contains) ||
        decoded['t'] != ChatAttachmentStagingContract.requestMessage) {
      await _replyFailure(id, ChatAttachmentStagingFailureReason.shellError, _documentEpoch, sink.generation);
      return;
    }
    if (_operation != null) {
      await _replyFailure(id, ChatAttachmentStagingFailureReason.unavailable, _documentEpoch, sink.generation);
      return;
    }
    if (!custody.hasCredential) {
      await _replyFailure(id, ChatAttachmentStagingFailureReason.unavailable, _documentEpoch, sink.generation);
      return;
    }
    final operation = _StagingOperation(host: this, id: id, epoch: _documentEpoch, documentGeneration: sink.generation);
    _operation = operation;
    unawaited(operation.start());
  }

  bool _isCurrent(_StagingOperation operation) =>
      !_closed && operation.epoch == _documentEpoch && identical(_operation, operation);

  void _retire(_StagingOperation operation) {
    if (identical(_operation, operation)) _operation = null;
  }

  Future<void> _replyFailure(
    String id,
    ChatAttachmentStagingFailureReason reason,
    int epoch,
    int documentGeneration,
  ) async {
    if (_closed || epoch != _documentEpoch) return;
    await sink.stagingReply(id, <String, Object>{
      'ok': false,
      'id': id,
      'reason': reason.wire,
    }, generation: documentGeneration);
  }

  Future<void> _replySuccess(String id, Map<String, Object> attachment, int epoch, int documentGeneration) async {
    if (_closed || epoch != _documentEpoch) return;
    await sink.stagingReply(id, <String, Object>{
      'ok': true,
      'id': id,
      'attachment': attachment,
    }, generation: documentGeneration);
  }

  Future<void> resetForNavigation() async {
    sink.resetForNavigation();
    _documentEpoch += 1;
    final operation = _operation;
    _operation = null;
    await operation?.cancel();
  }

  Future<void> close() async {
    if (_closed) return;
    _closed = true;
    sink.close();
    _documentEpoch += 1;
    final operation = _operation;
    _operation = null;
    await operation?.cancel();
    _httpClient.close(force: true);
  }
}

class _StagingOperation {
  _StagingOperation({required this.host, required this.id, required this.epoch, required this.documentGeneration});

  final ChatAttachmentStagingHost host;
  final String id;
  final int epoch;
  final int documentGeneration;
  ChatNativeHttpRequest? _request;
  bool _cancelled = false;
  bool _settled = false;

  Future<void> start() async {
    try {
      final picked = await host._picker.pickOne();
      if (!host._isCurrent(this) || _cancelled) return;
      if (picked == null) {
        await _fail(ChatAttachmentStagingFailureReason.cancelled);
        return;
      }
      if (picked.sizeBytes <= 0 || picked.sizeBytes > maxChatAttachmentBytes || !await picked.isRegularFile()) {
        await _fail(ChatAttachmentStagingFailureReason.shellError);
        return;
      }
      final token = host.custody.currentToken;
      if (token == null) {
        await _fail(ChatAttachmentStagingFailureReason.unavailable);
        return;
      }
      final boundary = host._boundaryFactory();
      if (!RegExp(r'^[A-Za-z0-9-]{1,70}$').hasMatch(boundary)) {
        await _fail(ChatAttachmentStagingFailureReason.shellError);
        return;
      }
      final prefix = utf8.encode(
        '--$boundary\r\n'
        'Content-Disposition: form-data; name="file"; filename="upload"\r\n\r\n',
      );
      final suffix = utf8.encode('\r\n--$boundary--\r\n');
      final request = await host._httpClient.openUrl('POST', host.baseUrl.resolve('/v1/chat-attachments'));
      _request = request;
      if (!host._isCurrent(this) || _cancelled) {
        request.abort();
        return;
      }
      request.followRedirects = false;
      request.contentLength = prefix.length + picked.sizeBytes + suffix.length;
      request.setHeader(HttpHeaders.authorizationHeader, 'Bearer $token');
      request.setHeader(AppRequestContract.versionHeader, AppRequestContract.version);
      request.setHeader(HttpHeaders.contentTypeHeader, 'multipart/form-data; boundary=$boundary');
      if (host.clientIdentity != null) {
        request.setHeader(BridgeHttpHostPolicy.clientIdHeader, host.clientIdentity!);
      }
      request.add(prefix);
      await request.addStream(_validatedFileBytes(picked));
      if (!host._isCurrent(this) || _cancelled) return;
      request.add(suffix);
      final response = await request.close().timeout(const Duration(seconds: 30));
      if (!host._isCurrent(this) || _cancelled) {
        await response.bytes.listen(null).cancel();
        return;
      }
      if (response.isRedirect || response.statusCode != HttpStatus.created) {
        await response.bytes.listen(null).cancel();
        await _fail(ChatAttachmentStagingFailureReason.shellError);
        return;
      }
      if (!responseHasMediaType(response.contentType, 'application/json')) {
        await response.bytes.listen(null).cancel();
        await _fail(ChatAttachmentStagingFailureReason.shellError);
        return;
      }
      final body = await _readBounded(response.bytes);
      final descriptor = _parseDescriptor(body, picked.sizeBytes);
      if (descriptor == null) {
        await _fail(ChatAttachmentStagingFailureReason.shellError);
        return;
      }
      _settled = true;
      host._retire(this);
      await host._replySuccess(id, descriptor, epoch, documentGeneration);
    } on TimeoutException {
      await _fail(ChatAttachmentStagingFailureReason.shellError);
    } on FileSystemException {
      await _fail(ChatAttachmentStagingFailureReason.shellError);
    } on SocketException {
      await _fail(ChatAttachmentStagingFailureReason.shellError);
    } on HttpException {
      await _fail(ChatAttachmentStagingFailureReason.shellError);
    } catch (_) {
      await _fail(ChatAttachmentStagingFailureReason.shellError);
    }
  }

  Stream<List<int>> _validatedFileBytes(PickedChatAttachment picked) async* {
    var byteCount = 0;
    await for (final chunk in picked.openRead()) {
      if (_cancelled || !host._isCurrent(this)) {
        throw const FileSystemException('upload cancelled');
      }
      byteCount += chunk.length;
      if (byteCount > picked.sizeBytes) {
        throw const FileSystemException('file grew during upload');
      }
      yield chunk;
    }
    if (byteCount != picked.sizeBytes) {
      throw const FileSystemException('file size changed during upload');
    }
  }

  Future<String> _readBounded(Stream<List<int>> source) async {
    final bytes = <int>[];
    await for (final chunk in source) {
      if (bytes.length + chunk.length > _maxResponseBytes) {
        throw const FormatException('attachment response too large');
      }
      bytes.addAll(chunk);
    }
    return const Utf8Decoder(allowMalformed: false).convert(bytes);
  }

  Map<String, Object>? _parseDescriptor(String raw, int expectedSize) {
    dynamic decoded;
    try {
      decoded = jsonDecode(raw);
    } on FormatException {
      return null;
    }
    if (decoded is! Map<String, dynamic> || decoded.length != 1 || !decoded.containsKey('attachment')) {
      return null;
    }
    final attachment = decoded['attachment'];
    if (attachment is! Map<String, dynamic> ||
        attachment.length != ChatAttachmentStagingContract.descriptorFields.length ||
        !attachment.keys.every(ChatAttachmentStagingContract.descriptorFields.contains)) {
      return null;
    }
    final attachmentId = attachment['id'];
    final mimeType = attachment['mimeType'];
    final sizeBytes = attachment['sizeBytes'];
    final expiresAt = attachment['expiresAt'];
    if (attachmentId is! String || !_safeOpaque.hasMatch(attachmentId)) {
      return null;
    }
    if (mimeType is! String || mimeType.length > 127 || !_safeMime.hasMatch(mimeType)) {
      return null;
    }
    if (sizeBytes is! int || sizeBytes != expectedSize || sizeBytes <= 0 || sizeBytes > _maxSafeInteger) {
      return null;
    }
    if (attachment['state'] != ChatAttachmentStagingContract.stagedState) {
      return null;
    }
    if (expiresAt is! String || !_canonicalExpiry.hasMatch(expiresAt)) {
      return null;
    }
    final parsedExpiry = DateTime.tryParse(expiresAt);
    if (parsedExpiry == null || parsedExpiry.toUtc().toIso8601String() != expiresAt) {
      return null;
    }
    return <String, Object>{
      'id': attachmentId,
      'mimeType': mimeType,
      'sizeBytes': sizeBytes,
      'expiresAt': expiresAt,
      'state': ChatAttachmentStagingContract.stagedState,
    };
  }

  Future<void> _fail(ChatAttachmentStagingFailureReason reason) async {
    if (_settled || _cancelled) return;
    _settled = true;
    host._retire(this);
    _request?.abort();
    await host._replyFailure(id, reason, epoch, documentGeneration);
  }

  Future<void> cancel() async {
    if (_cancelled) return;
    _cancelled = true;
    _request?.abort();
  }
}
