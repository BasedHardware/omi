import 'package:flutter_test/flutter_test.dart';
import 'package:omi/self_hosted/cloudflare/cloudflare_transcript_api.dart';
import 'package:omi/self_hosted/cloudflare/cloudflare_transcript_models.dart';
import 'package:omi/self_hosted/cloudflare/cloudflare_transcript_provider.dart';

void main() {
  test('does not fetch when Cloudflare configuration is disabled', () async {
    final api = _FakeApi(enabled: false);
    final provider = CloudflareTranscriptProvider(api: api);

    await provider.loadSessions();

    expect(api.listCalls, 0);
    expect(provider.sessions, isEmpty);
  });

  test('keeps the existing Omi UI boundary by retaining failures in the provider', () async {
    final provider = CloudflareTranscriptProvider(
      api: _FakeApi(error: const CloudflareTranscriptApiException('safe error')),
    );

    await provider.loadSessions();

    expect(provider.error, 'safe error');
    expect(provider.isLoading, isFalse);
  });
}

class _FakeApi implements CloudflareTranscriptApi {
  _FakeApi({this.enabled = true, this.error});

  @override
  final bool enabled;
  final Object? error;
  int listCalls = 0;

  @override
  Future<CloudflareTranscriptDetail> getTranscript(String sessionId) async =>
      const CloudflareTranscriptDetail(session: CloudflareTranscriptSession(id: 'id', status: 'ready'), chunks: []);

  @override
  Future<List<CloudflareTranscriptSession>> listSessions({int limit = 50}) async {
    listCalls += 1;
    if (error != null) throw error!;
    return const [];
  }
}
