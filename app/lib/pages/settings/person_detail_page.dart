import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/settings/person_name_dialog.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// One person: what Omi knows about them (conversations, talk time, voice samples) and every
/// conversation they are in, newest first.
class PersonDetailPage extends StatefulWidget {
  const PersonDetailPage({super.key, required this.personId});

  final String personId;

  @override
  State<PersonDetailPage> createState() => _PersonDetailPageState();
}

class _PersonDetailPageState extends State<PersonDetailPage> {
  static const _pageSize = 20;

  final _conversations = <ServerConversation>[];
  final _scroll = ScrollController();
  int _page = 0;
  bool _hasMore = true;
  bool _loading = false;
  bool _failed = false;

  @override
  void initState() {
    super.initState();
    _scroll.addListener(() {
      if (_scroll.position.pixels > _scroll.position.maxScrollExtent - 400) _loadMore();
    });
    _loadMore();
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _loadMore() async {
    if (_loading || !_hasMore) return;
    setState(() {
      _loading = true;
      _failed = false;
    });
    final result = await searchConversationsServerResult(
      '',
      page: _page + 1,
      limit: _pageSize,
      includeDiscarded: false,
      speakerId: widget.personId,
    );
    if (!mounted) return;
    setState(() {
      _loading = false;
      if (!result.isSuccess) {
        _failed = true;
        return;
      }
      _page = result.currentPage;
      final known = _conversations.map((c) => c.id).toSet();
      _conversations.addAll(result.items.where((c) => !known.contains(c.id)));
      _hasMore = result.totalPages > result.currentPage;
    });
  }

  Future<void> _open(ServerConversation conversation) async {
    final timestamp = conversation.startedAt ?? conversation.createdAt;
    context.read<ConversationDetailProvider>().updateConversation(conversation.id, conversationLocalDayKey(timestamp));
    await routeToPage(context, ConversationDetailPage(conversation: conversation));
  }

  Future<void> _confirmDeleteSample(PeopleProvider provider, int personIdx, Person person, int sampleIdx) async {
    final connectivity = Provider.of<ConnectivityProvider>(context, listen: false);
    if (!connectivity.isConnected) {
      ConnectivityProvider.showNoInternetDialog(context);
      return;
    }
    final confirmed = await showOmiConfirm(
      context,
      title: context.l10n.deleteSampleQuestion,
      message: context.l10n.deleteSampleConfirmation(person.name),
      confirmLabel: context.l10n.delete,
      destructive: true,
    );
    if (confirmed) await provider.deletePersonSample(personIdx, sampleIdx);
  }

  Future<void> _confirmDeletePerson(PeopleProvider provider, Person person) async {
    final confirmed = await showOmiConfirm(
      context,
      title: context.l10n.deletePersonTitle,
      message: context.l10n.deletePersonConfirmation(person.name),
      confirmLabel: context.l10n.delete,
      destructive: true,
    );
    if (!confirmed) return;
    await provider.deletePeople([person.id]);
    if (mounted) Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final provider = context.watch<PeopleProvider>();
    final index = provider.people.indexWhere((p) => p.id == widget.personId);
    if (index == -1) {
      return Scaffold(
        backgroundColor: OmiColors.surface0,
        appBar: AppBar(leading: const OmiBackButton(), title: Text(l10n.people)),
        body: OmiEmptyState(icon: Icons.person_off_outlined, title: l10n.noPeopleYet),
      );
    }
    final person = provider.people[index];
    final dates = OmiDateFormat.of(context);
    final samples = person.speechSamples ?? const <String>[];
    return Scaffold(
      backgroundColor: OmiColors.surface0,
      appBar: AppBar(
        leading: const OmiBackButton(),
        title: Text(person.name),
        actions: [
          OmiIconButton(
            icon: const Icon(Icons.edit_outlined),
            label: l10n.editPerson,
            onPressed: () => showPersonNameDialog(context, provider, person: person),
          ),
          OmiIconButton(
            icon: const Icon(Icons.delete_outline),
            label: l10n.deletePersonLabel,
            onPressed: () => _confirmDeletePerson(provider, person),
          ),
        ],
      ),
      body: ListView(
        controller: _scroll,
        padding: EdgeInsets.only(bottom: MediaQuery.paddingOf(context).bottom + OmiSpacing.xl),
        children: [
          Padding(
            padding: const EdgeInsets.all(OmiSpacing.md),
            child: Row(
              children: [
                _Stat(
                  value: person.conversationCount?.toString() ?? '–',
                  label: l10n.conversations,
                ),
                _Stat(
                  value: person.talkSeconds == null ? '–' : OmiDuration.compact(person.talkSeconds!.round(), l10n),
                  label: l10n.personTalkTime,
                ),
                _Stat(
                  value: person.lastHeardAt == null ? '–' : dates.date(person.lastHeardAt!),
                  label: l10n.personLastHeard,
                ),
              ],
            ),
          ),
          OmiSectionHeader(l10n.speechProfile),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
            child: Text(
              l10n.voiceRecognitionStatus(person.voiceReadiness),
              style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
            ),
          ),
          for (final (j, sample) in samples.indexed)
            PersonSampleRow(
              title: l10n.sampleNumber(j + 1),
              transcript: person.speechSampleTranscripts != null && j < person.speechSampleTranscripts!.length
                  ? person.speechSampleTranscripts![j]
                  : null,
              playing: provider.currentPlayingPersonIndex == index &&
                  provider.currentPlayingIndex == j &&
                  provider.isPlaying,
              onPlayPause: () => provider.playPause(index, j, sample),
              onDelete: () => _confirmDeleteSample(provider, index, person, j),
            ),
          OmiSectionHeader(l10n.conversations),
          if (_conversations.isEmpty && !_loading && !_failed)
            Padding(
              padding: const EdgeInsets.all(OmiSpacing.xl),
              child: OmiEmptyState(icon: Icons.forum_outlined, title: l10n.noConversationsYet),
            ),
          for (final conversation in _conversations)
            ListTile(
              leading: Text(conversation.structured.emoji, style: OmiType.title2),
              title: Text(conversation.structured.title, maxLines: 1, overflow: TextOverflow.ellipsis),
              subtitle: Text(dates.timestamp(conversation.startedAt ?? conversation.createdAt)),
              trailing: Icon(Icons.chevron_right, color: OmiColors.textTertiary),
              onTap: () => _open(conversation),
            ),
          if (_loading) const Padding(padding: EdgeInsets.all(OmiSpacing.lg), child: Center(child: OmiSpinner())),
          if (_failed)
            Padding(
              padding: const EdgeInsets.all(OmiSpacing.md),
              child: OmiButton.secondary(label: l10n.tryAgain, onPressed: _loadMore),
            ),
        ],
      ),
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat({required this.value, required this.label});

  final String value;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Column(
        children: [
          Text(value, style: OmiType.title3, maxLines: 1, overflow: TextOverflow.ellipsis),
          const SizedBox(height: 2),
          Text(label, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary), maxLines: 1),
        ],
      ),
    );
  }
}

/// One voice sample: tapping the row (or its play button) plays or pauses it; delete is the
/// labelled trailing control, behind a confirmation.
class PersonSampleRow extends StatelessWidget {
  const PersonSampleRow({
    super.key,
    required this.title,
    required this.transcript,
    required this.playing,
    required this.onPlayPause,
    required this.onDelete,
  });

  final String title;
  final String? transcript;
  final bool playing;
  final VoidCallback onPlayPause;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final hasTranscript = transcript != null && transcript!.isNotEmpty;
    return InkWell(
      onTap: onPlayPause,
      borderRadius: OmiRadius.mdAll,
      child: Row(
        children: [
          OmiIconButton(
            icon: Icon(playing ? Icons.pause : Icons.play_arrow),
            label: playing ? l10n.pausePlayback : l10n.play,
            onPressed: onPlayPause,
          ),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: OmiSpacing.xs),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: OmiType.callout),
                  if (hasTranscript)
                    Padding(
                      padding: const EdgeInsets.only(top: 2),
                      child: Text(
                        '“$transcript”',
                        style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontStyle: FontStyle.italic),
                      ),
                    ),
                ],
              ),
            ),
          ),
          OmiIconButton(
            icon: const Icon(Icons.delete_outline, size: 20),
            label: l10n.deleteSample,
            color: OmiColors.textSecondary,
            onPressed: onDelete,
          ),
        ],
      ),
    );
  }
}
