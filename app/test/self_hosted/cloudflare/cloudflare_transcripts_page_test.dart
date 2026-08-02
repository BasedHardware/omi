import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/conversations_section_header.dart';
import 'package:omi/self_hosted/cloudflare/cloudflare_transcript_api.dart';
import 'package:omi/self_hosted/cloudflare/cloudflare_transcript_models.dart';
import 'package:omi/self_hosted/cloudflare/cloudflare_transcript_provider.dart';
import 'package:omi/self_hosted/cloudflare/cloudflare_transcripts_page.dart';
import 'package:provider/provider.dart';

void main() {
  const session = CloudflareTranscriptSession(
    id: 'session-1',
    status: 'transcribed',
    characterCount: 12,
  );

  testWidgets('Omi-zero fixture keeps the configured Cloudflare entry and opens the normal list and detail',
      (tester) async {
    final provider = CloudflareTranscriptProvider(
      api: _FakeApi(
        sessions: const [session],
        detail: const CloudflareTranscriptDetail(
          session: session,
          chunks: [
            CloudflareTranscriptChunk(sequence: 1, text: 'first'),
            CloudflareTranscriptChunk(sequence: 2, text: 'second'),
          ],
        ),
      ),
    );

    await tester.pumpWidget(
      _app(
        provider,
        const Scaffold(
          body: CustomScrollView(
            slivers: [
              SliverToBoxAdapter(
                child: ConversationsSectionHeader(showDailySummaries: false, hasOmiConversationState: false),
              ),
            ],
          ),
        ),
      ),
    );

    expect(find.byKey(const Key('cloudflare_transcripts_entry')), findsOneWidget);
    await tester.tap(find.byKey(const Key('cloudflare_transcripts_entry')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('cloudflare_transcript_session_session-1')), findsOneWidget);

    await tester.tap(find.byKey(const Key('cloudflare_transcript_session_session-1')));
    await tester.pumpAndSettle();
    expect(find.text('first\nsecond'), findsOneWidget);
  });

  testWidgets('empty list and disabled Omi-zero header preserve their respective empty boundaries', (tester) async {
    final disabledProvider = CloudflareTranscriptProvider(api: _FakeApi(enabled: false));
    await tester.pumpWidget(
      _app(
        disabledProvider,
        const Scaffold(
          body: ConversationsSectionHeader(showDailySummaries: false, hasOmiConversationState: false),
        ),
      ),
    );
    expect(find.byKey(const Key('cloudflare_transcripts_entry')), findsNothing);

    final emptyProvider = CloudflareTranscriptProvider(api: _FakeApi());
    await tester.pumpWidget(_app(emptyProvider, const CloudflareTranscriptsPage()));
    await tester.pumpAndSettle();
    expect(find.text("This conversation doesn't have a transcript."), findsOneWidget);
  });

  testWidgets('list failures remain in the Cloudflare page and offer retry', (tester) async {
    final provider = CloudflareTranscriptProvider(
      api: _FakeApi(error: const CloudflareTranscriptApiException('safe Worker error')),
    );

    await tester.pumpWidget(_app(provider, const CloudflareTranscriptsPage()));
    await tester.pumpAndSettle();

    expect(find.text('safe Worker error'), findsOneWidget);
    expect(find.byType(OutlinedButton), findsOneWidget);
  });
}

Widget _app(CloudflareTranscriptProvider provider, Widget home) {
  return ChangeNotifierProvider<CloudflareTranscriptProvider>.value(
    value: provider,
    child: MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: home,
    ),
  );
}

class _FakeApi implements CloudflareTranscriptApi {
  _FakeApi({
    this.enabled = true,
    this.sessions = const [],
    this.detail = const CloudflareTranscriptDetail(
      session: CloudflareTranscriptSession(id: 'unused', status: 'unknown'),
      chunks: [],
    ),
    this.error,
  });

  @override
  final bool enabled;
  final List<CloudflareTranscriptSession> sessions;
  final CloudflareTranscriptDetail detail;
  final Object? error;

  @override
  Future<CloudflareTranscriptDetail> getTranscript(String sessionId) async => detail;

  @override
  Future<List<CloudflareTranscriptSession>> listSessions({int limit = 50}) async {
    if (error != null) throw error!;
    return sessions;
  }
}
