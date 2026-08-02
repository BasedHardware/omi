import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/conversations_section_header.dart';
import 'package:omi/self_hosted/cloudflare/cloudflare_transcript_api.dart';
import 'package:omi/self_hosted/cloudflare/cloudflare_transcript_configuration.dart';
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
    expect(find.text('No Cloudflare transcripts are available yet.'), findsOneWidget);
  });

  testWidgets('disabled Cloudflare keeps existing Omi and daily-summary headers', (tester) async {
    final provider = CloudflareTranscriptProvider(api: _FakeApi(enabled: false));

    await tester.pumpWidget(
      _app(
        provider,
        const Scaffold(
          body: ConversationsSectionHeader(showDailySummaries: false, hasOmiConversationState: true),
        ),
      ),
    );
    expect(find.text('Conversations'), findsOneWidget);
    expect(find.byKey(const Key('cloudflare_transcripts_entry')), findsNothing);

    await tester.pumpWidget(
      _app(
        provider,
        const Scaffold(
          body: ConversationsSectionHeader(showDailySummaries: true, hasOmiConversationState: false),
        ),
      ),
    );
    expect(find.text('Daily Recaps'), findsOneWidget);
    expect(find.byKey(const Key('cloudflare_transcripts_entry')), findsNothing);
  });

  testWidgets('invalid Cloudflare configuration hides the Conversations entry', (tester) async {
    const configuration = CloudflareTranscriptConfiguration(
      workerUrl: 'https://credential@worker.example.test',
      token: 'token',
    );
    final provider = CloudflareTranscriptProvider(
      api: CloudflareTranscriptHttpApi(configuration: configuration),
    );

    await tester.pumpWidget(
      _app(
        provider,
        const Scaffold(
          body: ConversationsSectionHeader(showDailySummaries: false, hasOmiConversationState: false),
        ),
      ),
    );

    expect(find.byKey(const Key('cloudflare_transcripts_entry')), findsNothing);
  });

  testWidgets('detail empty keeps the detail-specific no-transcript message', (tester) async {
    final provider = CloudflareTranscriptProvider(
      api: _FakeApi(
        detail: const CloudflareTranscriptDetail(session: session, chunks: []),
      ),
    );

    await tester.pumpWidget(_app(provider, const CloudflareTranscriptDetailPage(session: session)));
    await tester.pumpAndSettle();

    expect(find.text("This conversation doesn't have a transcript."), findsOneWidget);
  });

  testWidgets('list failures remain in the Cloudflare page and offer retry', (tester) async {
    final provider = CloudflareTranscriptProvider(
      api: _FakeApi(
        listOutcomes: [const CloudflareTranscriptApiException('safe list Worker error')],
      ),
    );

    await tester.pumpWidget(_app(provider, const CloudflareTranscriptsPage()));
    await tester.pumpAndSettle();

    expect(find.text('safe list Worker error'), findsOneWidget);
    expect(find.byType(OutlinedButton), findsOneWidget);
  });

  testWidgets('detail failures remain visible and offer retry', (tester) async {
    final provider = CloudflareTranscriptProvider(
      api: _FakeApi(
        transcriptOutcomes: [const CloudflareTranscriptApiException('safe detail Worker error')],
      ),
    );

    await tester.pumpWidget(_app(provider, const CloudflareTranscriptDetailPage(session: session)));
    await tester.pumpAndSettle();

    expect(find.text('safe detail Worker error'), findsOneWidget);
    expect(find.byType(OutlinedButton), findsOneWidget);
  });

  testWidgets('detail retry replaces an error with the retried transcript', (tester) async {
    final api = _FakeApi(
      transcriptOutcomes: [
        const CloudflareTranscriptApiException('safe retryable detail error'),
        const CloudflareTranscriptDetail(
          session: session,
          chunks: [CloudflareTranscriptChunk(sequence: 1, text: 'retried transcript')],
        ),
      ],
    );
    final provider = CloudflareTranscriptProvider(api: api);

    await tester.pumpWidget(_app(provider, const CloudflareTranscriptDetailPage(session: session)));
    await tester.pumpAndSettle();
    expect(find.text('safe retryable detail error'), findsOneWidget);

    await tester.tap(find.byType(OutlinedButton));
    await tester.pumpAndSettle();

    expect(api.transcriptCalls, 2);
    expect(find.text('retried transcript'), findsOneWidget);
    expect(find.text('safe retryable detail error'), findsNothing);
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
    List<Object>? listOutcomes,
    List<Object>? transcriptOutcomes,
  })  : _listOutcomes = List<Object>.from(listOutcomes ?? const []),
        _transcriptOutcomes = List<Object>.from(transcriptOutcomes ?? const []);

  @override
  final bool enabled;
  final List<CloudflareTranscriptSession> sessions;
  final CloudflareTranscriptDetail detail;
  final List<Object> _listOutcomes;
  final List<Object> _transcriptOutcomes;
  int transcriptCalls = 0;

  @override
  Future<CloudflareTranscriptDetail> getTranscript(String sessionId) async {
    transcriptCalls += 1;
    final outcome = _transcriptOutcomes.isEmpty ? detail : _transcriptOutcomes.removeAt(0);
    if (outcome is CloudflareTranscriptDetail) return outcome;
    throw outcome;
  }

  @override
  Future<List<CloudflareTranscriptSession>> listSessions({int limit = 50}) async {
    final outcome = _listOutcomes.isEmpty ? sessions : _listOutcomes.removeAt(0);
    if (outcome is List<CloudflareTranscriptSession>) return outcome;
    throw outcome;
  }
}
