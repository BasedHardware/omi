import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:path/path.dart' as path;

/// Tests the 401→refresh→retry→signout logic pattern used in
/// makeMultipartApiCall() and makeMultipartStreamingApiCall().
///
/// The production code in shared.dart uses singletons (HttpPoolManager,
/// SharedPreferencesUtil, AuthService) that aren't injectable, so this
/// test exercises the exact same branching logic via a minimal abstraction
/// that mirrors the production flow.

/// Abstracts the dependencies used by the multipart 401 retry logic.
class AuthRetryDeps {
  final Future<http.StreamedResponse> Function(http.BaseRequest) sendRequest;
  final Future<String> Function() refreshToken;
  final Future<void> Function() signOut;

  AuthRetryDeps({
    required this.sendRequest,
    required this.refreshToken,
    required this.signOut,
  });
}

/// Builds a fresh MultipartRequest (mirrors _buildMultipartRequest in shared.dart).
/// Streams are single-use, so we must rebuild for each send attempt.
Future<http.MultipartRequest> buildMultipartRequest({
  required String url,
  required List<File> files,
  required Map<String, String> headers,
  required Map<String, String> fields,
  required String fileFieldName,
  required String method,
}) async {
  var request = http.MultipartRequest(method, Uri.parse(url));
  request.headers.addAll(headers);
  request.fields.addAll(fields);

  for (var file in files) {
    var stream = http.ByteStream(file.openRead());
    var length = await file.length();
    var multipartFile = http.MultipartFile(
      fileFieldName,
      stream,
      length,
      filename: path.basename(file.path),
    );
    request.files.add(multipartFile);
  }

  return request;
}

/// Mirrors the exact 401 retry logic from makeMultipartApiCall() in shared.dart.
/// Returns the final http.Response and whether signOut was called.
Future<http.Response> makeMultipartApiCallWithRetry({
  required String url,
  required List<File> files,
  required Map<String, String> headers,
  required Map<String, String> fields,
  required String fileFieldName,
  required String method,
  required bool requireAuthCheck,
  required AuthRetryDeps deps,
}) async {
  var request = await buildMultipartRequest(
    url: url,
    files: files,
    headers: headers,
    fields: fields,
    fileFieldName: fileFieldName,
    method: method,
  );

  var streamedResponse = await deps.sendRequest(request);
  var response = await http.Response.fromStream(streamedResponse);

  if (requireAuthCheck && response.statusCode == 401) {
    // Refresh token
    String newToken = await deps.refreshToken();
    if (newToken.isNotEmpty) {
      // Rebuild request (streams are consumed) and retry
      request = await buildMultipartRequest(
        url: url,
        files: files,
        headers: {...headers, 'Authorization': 'Bearer $newToken'},
        fields: fields,
        fileFieldName: fileFieldName,
        method: method,
      );
      streamedResponse = await deps.sendRequest(request);
      response = await http.Response.fromStream(streamedResponse);
      if (response.statusCode == 401) {
        await deps.signOut();
      }
    } else {
      await deps.signOut();
    }
  }

  return response;
}

void main() {
  late Directory tempDir;
  late File testFile;

  setUp(() {
    tempDir = Directory.systemTemp.createTempSync('multipart_401_test_');
    testFile = File('${tempDir.path}/test.txt')..writeAsStringSync('test content');
  });

  tearDown(() {
    tempDir.deleteSync(recursive: true);
  });

  http.StreamedResponse mockStreamedResponse(int statusCode, {String body = ''}) {
    return http.StreamedResponse(
      Stream.value(body.codeUnits),
      statusCode,
    );
  }

  group('makeMultipartApiCall 401 retry logic', () {
    test('non-401 response returns directly without refresh or signout', () async {
      int sendCount = 0;
      bool refreshCalled = false;
      bool signOutCalled = false;

      final deps = AuthRetryDeps(
        sendRequest: (_) async {
          sendCount++;
          return mockStreamedResponse(200, body: 'ok');
        },
        refreshToken: () async {
          refreshCalled = true;
          return 'new-token';
        },
        signOut: () async {
          signOutCalled = true;
        },
      );

      final response = await makeMultipartApiCallWithRetry(
        url: 'https://api.omi.me/v1/sync-local-files',
        files: [testFile],
        headers: {'Authorization': 'Bearer old-token'},
        fields: {},
        fileFieldName: 'files',
        method: 'POST',
        requireAuthCheck: true,
        deps: deps,
      );

      expect(response.statusCode, 200);
      expect(sendCount, 1);
      expect(refreshCalled, false);
      expect(signOutCalled, false);
    });

    test('401 → refresh succeeds → retry succeeds (200)', () async {
      int sendCount = 0;
      bool refreshCalled = false;
      bool signOutCalled = false;

      final deps = AuthRetryDeps(
        sendRequest: (_) async {
          sendCount++;
          if (sendCount == 1) {
            return mockStreamedResponse(401);
          }
          return mockStreamedResponse(200, body: 'ok');
        },
        refreshToken: () async {
          refreshCalled = true;
          return 'refreshed-token';
        },
        signOut: () async {
          signOutCalled = true;
        },
      );

      final response = await makeMultipartApiCallWithRetry(
        url: 'https://api.omi.me/v1/sync-local-files',
        files: [testFile],
        headers: {'Authorization': 'Bearer expired-token'},
        fields: {},
        fileFieldName: 'files',
        method: 'POST',
        requireAuthCheck: true,
        deps: deps,
      );

      expect(response.statusCode, 200);
      expect(sendCount, 2);
      expect(refreshCalled, true);
      expect(signOutCalled, false);
    });

    test('401 → refresh succeeds → retry still 401 → signs out', () async {
      int sendCount = 0;
      bool refreshCalled = false;
      bool signOutCalled = false;

      final deps = AuthRetryDeps(
        sendRequest: (_) async {
          sendCount++;
          return mockStreamedResponse(401);
        },
        refreshToken: () async {
          refreshCalled = true;
          return 'refreshed-but-still-invalid';
        },
        signOut: () async {
          signOutCalled = true;
        },
      );

      final response = await makeMultipartApiCallWithRetry(
        url: 'https://api.omi.me/v1/sync-local-files',
        files: [testFile],
        headers: {'Authorization': 'Bearer expired-token'},
        fields: {},
        fileFieldName: 'files',
        method: 'POST',
        requireAuthCheck: true,
        deps: deps,
      );

      expect(response.statusCode, 401);
      expect(sendCount, 2);
      expect(refreshCalled, true);
      expect(signOutCalled, true);
    });

    test('401 → refresh fails (empty token) → signs out immediately without retry', () async {
      int sendCount = 0;
      bool refreshCalled = false;
      bool signOutCalled = false;

      final deps = AuthRetryDeps(
        sendRequest: (_) async {
          sendCount++;
          return mockStreamedResponse(401);
        },
        refreshToken: () async {
          refreshCalled = true;
          return ''; // empty = refresh failed
        },
        signOut: () async {
          signOutCalled = true;
        },
      );

      final response = await makeMultipartApiCallWithRetry(
        url: 'https://api.omi.me/v1/sync-local-files',
        files: [testFile],
        headers: {'Authorization': 'Bearer expired-token'},
        fields: {},
        fileFieldName: 'files',
        method: 'POST',
        requireAuthCheck: true,
        deps: deps,
      );

      expect(response.statusCode, 401);
      expect(sendCount, 1); // no retry when refresh fails
      expect(refreshCalled, true);
      expect(signOutCalled, true);
    });

    test('401 with requireAuthCheck=false returns 401 without retry', () async {
      int sendCount = 0;
      bool refreshCalled = false;
      bool signOutCalled = false;

      final deps = AuthRetryDeps(
        sendRequest: (_) async {
          sendCount++;
          return mockStreamedResponse(401);
        },
        refreshToken: () async {
          refreshCalled = true;
          return 'new-token';
        },
        signOut: () async {
          signOutCalled = true;
        },
      );

      final response = await makeMultipartApiCallWithRetry(
        url: 'https://external.api.com/upload',
        files: [testFile],
        headers: {},
        fields: {},
        fileFieldName: 'files',
        method: 'POST',
        requireAuthCheck: false, // external URL, no auth check
        deps: deps,
      );

      expect(response.statusCode, 401);
      expect(sendCount, 1);
      expect(refreshCalled, false);
      expect(signOutCalled, false);
    });

    test('request is rebuilt for retry (fresh stream)', () async {
      int sendCount = 0;
      final requestUrls = <String>[];
      final requestHeaders = <Map<String, String>>[];

      final deps = AuthRetryDeps(
        sendRequest: (request) async {
          sendCount++;
          requestUrls.add(request.url.toString());
          requestHeaders.add(Map.from(request.headers));
          if (sendCount == 1) {
            return mockStreamedResponse(401);
          }
          return mockStreamedResponse(200, body: 'ok');
        },
        refreshToken: () async => 'new-token',
        signOut: () async {},
      );

      final response = await makeMultipartApiCallWithRetry(
        url: 'https://api.omi.me/v1/sync-local-files',
        files: [testFile],
        headers: {'Authorization': 'Bearer old-token'},
        fields: {'key': 'value'},
        fileFieldName: 'files',
        method: 'POST',
        requireAuthCheck: true,
        deps: deps,
      );

      expect(response.statusCode, 200);
      expect(sendCount, 2);
      // Both requests hit the same URL
      expect(requestUrls[0], requestUrls[1]);
      // Second request has refreshed token
      expect(requestHeaders[1]['Authorization'], 'Bearer new-token');
    });

    test('500 response does not trigger auth retry', () async {
      int sendCount = 0;
      bool refreshCalled = false;

      final deps = AuthRetryDeps(
        sendRequest: (_) async {
          sendCount++;
          return mockStreamedResponse(500, body: 'server error');
        },
        refreshToken: () async {
          refreshCalled = true;
          return 'new-token';
        },
        signOut: () async {},
      );

      final response = await makeMultipartApiCallWithRetry(
        url: 'https://api.omi.me/v1/sync-local-files',
        files: [testFile],
        headers: {'Authorization': 'Bearer valid-token'},
        fields: {},
        fileFieldName: 'files',
        method: 'POST',
        requireAuthCheck: true,
        deps: deps,
      );

      expect(response.statusCode, 500);
      expect(sendCount, 1);
      expect(refreshCalled, false);
    });
  });
}
