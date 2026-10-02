import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:http/io_client.dart';
import 'package:omi/backend/http/api_result.dart';
import '../../integration_test/journeys/support/fixture_backend.dart';

class _LoopbackHttp extends HttpOverrides {}

/// Bypasses flutter_test's blanket HTTP-400 fake only for the owned loopback
/// server. No Env, auth singleton, production URL or default CaptureController.
class C3Fixture {
  C3Fixture._(this.backend)
      : client = IOClient(HttpOverrides.runWithHttpOverrides(() => HttpClient(), _LoopbackHttp()));
  final JourneyFixtureBackend backend;
  final http.Client client;
  static Future<C3Fixture> start() async => C3Fixture._(await JourneyFixtureBackend.start());
  Future<http.Response> send(ApiRequest request) async {
    final uri = Uri.parse(request.url);
    final owned = Uri.parse(backend.baseUrl);
    if (uri.scheme != 'http' || uri.host != '127.0.0.1' || uri.port != owned.port) {
      throw StateError('C3 fixture refused a non-owned endpoint');
    }
    final wire = http.Request(request.method, uri)
      ..headers.addAll(request.headers)
      ..body = request.body;
    wire.followRedirects = false;
    return http.Response.fromStream(await client.send(wire));
  }

  Future<void> close() async {
    client.close();
    await backend.stop();
  }
}
