import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api_result.dart';
import '../spine/c3_fixture.dart';

void main() {
  test('fixture HTTP faults are ordered, one-shot, counted, and cleared', () async {
    final f = await C3Fixture.start();
    addTearDown(f.close);
    final request = ApiRequest(url: '${f.backend.baseUrl}v1/conversations', method: 'GET');
    f.backend.failNext('GET', '/v1/conversations', status: 503, body: '{"error":"fixture"}');
    f.backend.failNext('GET', '/v1/conversations', status: 402);
    final failed = await f.send(request);
    expect(failed.statusCode, 503);
    expect(failed.body, '{"error":"fixture"}');
    expect((await f.send(request)).statusCode, 402);
    expect((await f.send(request)).statusCode, 200);
    expect(f.backend.countOf('GET', '/v1/conversations'), 3);
    f.backend.failNext('GET', '/v1/conversations', status: 422);
    f.backend.clearFaults();
    expect((await f.send(request)).statusCode, 200);
    await expectLater(f.send(const ApiRequest(url: 'http://127.0.0.1:1/', method: 'GET')), throwsStateError);
  });
}
