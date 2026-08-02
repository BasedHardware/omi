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
          if (provider.error != null) return _ErrorState(message: provider.error!, onRetry: provider.loadSessions);
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
    final time = session.displayTime;
    final subtitle = [
      session.status,
      if (time != null) DateFormat.yMMMd(Localizations.localeOf(context).toString()).add_Hm().format(time),
      if (session.characterCount != null) session.characterCount.toString(),
    ].join(' · ');
    return ListTile(
      key: Key('cloudflare_transcript_session_${session.id}'),
      title: Text(session.id),
      subtitle: Text(subtitle),
      trailing: const Icon(Icons.chevron_right),
      onTap: () => Navigator.of(context).push(
        MaterialPageRoute<void>(builder: (_) => CloudflareTranscriptDetailPage(session: session)),
      ),
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
          if (snapshot.hasError) return _ErrorState(message: snapshot.error.toString(), onRetry: _retry);
          final text = snapshot.data?.fullText ?? '';
          if (text.isEmpty) return Center(child: Text(context.l10n.noTranscriptMessage));
          return SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: SelectableText(text),
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
  const _ErrorState({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 12),
            OutlinedButton(onPressed: onRetry, child: Text(context.l10n.retry)),
          ],
        ),
      ),
    );
  }
}
