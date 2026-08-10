import 'dart:io';

abstract interface class ChatNativeHttpClient {
  Future<ChatNativeHttpRequest> openUrl(String method, Uri url);
  void close({bool force = false});
}

abstract interface class ChatNativeHttpRequest {
  set followRedirects(bool value);
  set contentLength(int value);
  void setHeader(String name, Object value);
  void add(List<int> bytes);
  Future<ChatNativeHttpResponse> close();
  void abort([Object? exception]);
}

abstract interface class ChatNativeHttpResponse {
  int get statusCode;
  bool get isRedirect;
  Stream<List<int>> get bytes;
}

class DartIoChatNativeHttpClient implements ChatNativeHttpClient {
  DartIoChatNativeHttpClient()
    : _client = HttpClient()
        ..connectionTimeout = const Duration(seconds: 10)
        ..userAgent = null;

  final HttpClient _client;

  @override
  Future<ChatNativeHttpRequest> openUrl(String method, Uri url) async {
    return DartIoChatNativeHttpRequest(await _client.openUrl(method, url));
  }

  @override
  void close({bool force = false}) => _client.close(force: force);
}

class DartIoChatNativeHttpRequest implements ChatNativeHttpRequest {
  DartIoChatNativeHttpRequest(this._request);

  final HttpClientRequest _request;

  @override
  set followRedirects(bool value) => _request.followRedirects = value;

  @override
  set contentLength(int value) => _request.contentLength = value;

  @override
  void setHeader(String name, Object value) =>
      _request.headers.set(name, value);

  @override
  void add(List<int> bytes) => _request.add(bytes);

  @override
  Future<ChatNativeHttpResponse> close() async {
    return DartIoChatNativeHttpResponse(await _request.close());
  }

  @override
  void abort([Object? exception]) => _request.abort(exception);
}

class DartIoChatNativeHttpResponse implements ChatNativeHttpResponse {
  DartIoChatNativeHttpResponse(this._response);

  final HttpClientResponse _response;

  @override
  int get statusCode => _response.statusCode;

  @override
  bool get isRedirect => _response.isRedirect;

  @override
  Stream<List<int>> get bytes => _response;
}
