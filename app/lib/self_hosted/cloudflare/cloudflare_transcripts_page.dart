import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:provider/provider.dart';

import 'cloudflare_transcript_models.dart';
import 'cloudflare_transcript_provider.dart';

class CloudflareTranscriptsPage extends StatefulWidget {
  const CloudflareTranscriptsPage({super.key});

  @override
  State<CloudflareTranscriptsPage> createState() => _CloudflareTranscriptsPageState();
}

class _CloudflareTranscriptsPageState extends State<CloudflareTranscriptsPage> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => context.read<CloudflareTranscriptProvider>().loadSessions());
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(context.l10n.transcriptTab)),
      body: Consumer<CloudflareTranscriptProvider>(
        builder: (context, provider, _) {
          if (provider.isLoading && provider.sessions.isEmpty) return const Center(child: CircularProgressIndicator());
          if (provider.error != null) return _ErrorState(onRetry: provider.loadSessions);
          if (provider.sessions.isEmpty) return Center(child: Text(context.l10n.cloudflareTranscriptListEmptyMessage));
          return RefreshIndicator(
            onRefresh: provider.loadSessions,
            child: ListView.separated(
              itemCount: provider.sessions.length,
              separatorBuilder: (_, __) => const Divider(height: 1),
              itemBuilder: (context, index) => _SessionTile(session: provider.sessions[index]),
            ),
          );
        },
      ),
    );
  }
}

class _SessionTile extends StatelessWidget {
  const _SessionTile({required this.session});

  final CloudflareTranscriptSession session;

  @override
  Widget build(BuildContext context) {
    final metadata = _sessionMetadata(context, session);
    final semanticsLabel = context.l10n.cloudflareTranscriptSessionSemantics(session.id, metadata);
    return Semantics(
      key: Key('cloudflare_transcript_session_${session.id}'),
      label: semanticsLabel,
      button: true,
      onTap: () => _openDetail(context),
      child: ExcludeSemantics(
        child: ListTile(
          title: Text(session.id),
          subtitle: Text(metadata),
          trailing: const Icon(Icons.chevron_right),
          onTap: () => _openDetail(context),
        ),
      ),
    );
  }

  void _openDetail(BuildContext context) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => CloudflareTranscriptDetailPage(session: session)),
    );
  }
}

class CloudflareTranscriptDetailPage extends StatefulWidget {
  const CloudflareTranscriptDetailPage({super.key, required this.session});

  final CloudflareTranscriptSession session;

  @override
  State<CloudflareTranscriptDetailPage> createState() => _CloudflareTranscriptDetailPageState();
}

class _CloudflareTranscriptDetailPageState extends State<CloudflareTranscriptDetailPage> {
  Future<CloudflareTranscriptDetail>? _detail;

  @override
  void initState() {
    super.initState();
    _detail = context.read<CloudflareTranscriptProvider>().loadTranscript(widget.session.id);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(context.l10n.transcriptTab)),
      body: FutureBuilder<CloudflareTranscriptDetail>(
        future: _detail,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) return const Center(child: CircularProgressIndicator());
          if (snapshot.hasError) return _ErrorState(onRetry: _retry);
          final detail = snapshot.data;
          final text = detail?.fullText ?? '';
          if (text.isEmpty) return Center(child: Text(context.l10n.noTranscriptMessage));
          final session = detail?.session ?? widget.session;
          final metadata = _sessionMetadata(context, session);
          return SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Semantics(
                  key: const Key('cloudflare_transcript_detail_metadata'),
                  container: true,
                  label: context.l10n.cloudflareTranscriptSessionSemantics(session.id, metadata),
                  child: ExcludeSemantics(child: Text(metadata)),
                ),
                const SizedBox(height: 12),
                SelectableText(text),
              ],
            ),
          );
        },
      ),
    );
  }

  void _retry() {
    setState(() {
      _detail = context.read<CloudflareTranscriptProvider>().loadTranscript(widget.session.id);
    });
  }
}

class _ErrorState extends StatelessWidget {
  const _ErrorState({required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(context.l10n.cloudflareTranscriptLoadError, textAlign: TextAlign.center),
            const SizedBox(height: 12),
            OutlinedButton(onPressed: onRetry, child: Text(context.l10n.retry)),
          ],
        ),
      ),
    );
  }
}

String _sessionMetadata(BuildContext context, CloudflareTranscriptSession session) {
  final time = session.displayTime;
  return [
    '${context.l10n.statusLabel}: ${session.status}',
    if (time != null) DateFormat.yMMMd(Localizations.localeOf(context).toString()).add_Hm().format(time),
    if (session.characterCount case final characterCount?) context.l10n.charactersCount(characterCount),
  ].join(' · ');
}
