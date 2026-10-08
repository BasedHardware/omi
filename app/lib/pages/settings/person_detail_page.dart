import 'dart:async';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/mobile/native_ui/ios_native_home.dart';
import 'package:omi/mobile/native_ui/native_read_session.dart';
import 'package:omi/mobile/native_ui/native_conversation_projection.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/settings/person_name_dialog.dart';
import 'package:omi/pages/settings/widgets/people_list.dart';
import 'package:omi/pages/settings/widgets/person_avatar.dart';
import 'package:omi/pages/settings/widgets/person_confidence.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/services/auth_service.dart';
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
  late final NativeReadSession _readSession;
  StreamSubscription<int>? _authSubscription;

  @override
  void initState() {
    super.initState();
    final owner = iosSwiftUiEnabled ? AuthService.instance.captureSessionSnapshot() : null;
    _readSession = NativeReadSession(
      isCurrent: () =>
          mounted && (owner == null ? !iosSwiftUiEnabled : AuthService.instance.isSessionSnapshotCurrent(owner)),
    );
    if (iosSwiftUiEnabled) {
      _authSubscription = AuthService.instance.sessionGenerationEvents.listen((_) {
        if (!_readSession.active && mounted) {
          setState(() {
            _conversations.clear();
            _hasMore = false;
            _loading = false;
          });
        }
      });
    }
    _scroll.addListener(() {
      if (_scroll.position.pixels > _scroll.position.maxScrollExtent - 400) _loadMore();
    });
    _loadMore();
  }

  @override
  void dispose() {
    _readSession.dispose();
    _authSubscription?.cancel();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _loadMore() async {
    if (!_readSession.active || _loading || !_hasMore) return;
    setState(() {
      _loading = true;
      _failed = false;
    });
    final result = await _readSession.read(() => searchConversationsServerResult(
          '',
          page: _page + 1,
          limit: _pageSize,
          includeDiscarded: false,
          speakerId: widget.personId,
        ));
    if (!mounted || result == null || !_readSession.active) return;
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

  /// A pinned person gets the name-bearing confirm; this is the only way to delete one.
  Future<void> _confirmDeletePerson(PeopleProvider provider, Person person) async {
    if (await confirmAndDeletePeople(context, provider, [person]) && mounted) Navigator.of(context).pop();
  }

  /// Pull-to-refresh: the person's stats and the first page of conversations.
  Future<void> _refresh() async {
    if (_loading) return;
    setState(() {
      _conversations.clear();
      _page = 0;
      _hasMore = true;
    });
    await Future.wait([context.read<PeopleProvider>().refresh(), _loadMore()]);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final provider = context.watch<PeopleProvider>();
    final index = provider.people.indexWhere((p) => p.id == widget.personId);
    if (index == -1) {
      final classic = Scaffold(
        backgroundColor: OmiColors.surface0,
        appBar: AppBar(leading: const OmiBackButton(), title: Text(l10n.people)),
        body: OmiEmptyState(icon: Icons.person_off_outlined, title: l10n.noPeopleYet),
      );
      return IosNativeSurface(
          title: l10n.people,
          sections: const [],
          empty: l10n.noPeopleYet,
          fallback: classic,
          toolbar: [
            NativeRow('person_back', l10n.back, symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop())
          ]);
    }
    final person = provider.people[index];
    final dates = OmiDateFormat.of(context);
    final samples = person.speechSamples ?? const <String>[];
    final transcripts = person.speechSampleTranscripts ?? const <String>[];
    final classic = Scaffold(
      backgroundColor: OmiColors.surface0,
      appBar: AppBar(
        leading: const OmiBackButton(),
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
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: ListView(
          controller: _scroll,
          padding: EdgeInsets.fromLTRB(
            OmiSpacing.md,
            0,
            OmiSpacing.md,
            MediaQuery.paddingOf(context).bottom + OmiSpacing.xl,
          ),
          children: [
            _Header(person: person),
            const SizedBox(height: OmiSpacing.lg),
            Row(
              children: [
                _Stat(value: person.conversationCount?.toString() ?? '–', label: l10n.conversations),
                const SizedBox(width: OmiSpacing.xs),
                _Stat(
                  value: person.talkSeconds == null ? '–' : OmiDuration.compact(person.talkSeconds!.round(), l10n),
                  label: l10n.personTalkTime,
                ),
                const SizedBox(width: OmiSpacing.xs),
                _Stat(
                  value: person.lastHeardAt == null ? '–' : dates.dayHeader(person.lastHeardAt!),
                  label: l10n.personLastHeard,
                ),
              ],
            ),
            const SizedBox(height: OmiSpacing.xl),
            OmiSettingsGroup(
              children: [
                OmiSettingsRow.toggle(
                  key: const Key('person_pin_switch'),
                  title: l10n.pinAction,
                  subtitle: l10n.pinPersonHonestLine,
                  value: person.pinned,
                  onChanged: (_) => togglePersonPinned(context, provider, person),
                ),
              ],
            ),
            const SizedBox(height: OmiSpacing.xl),
            OmiSectionHeader(l10n.speechProfile),
            _Card(
              children: [
                if (samples.isEmpty)
                  Padding(
                    padding: const EdgeInsets.all(OmiSpacing.md),
                    child: Text(
                      l10n.voiceSettingsSaveOthersSubtitle,
                      style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                    ),
                  ),
                for (final (j, sample) in samples.indexed)
                  PersonSampleRow(
                    title: l10n.sampleNumber(j + 1),
                    transcript: j < transcripts.length ? transcripts[j] : null,
                    playing: provider.currentPlayingPersonIndex == index &&
                        provider.currentPlayingIndex == j &&
                        provider.isPlaying,
                    onPlayPause: () => provider.playPause(index, j, sample),
                    onDelete: () => _confirmDeleteSample(provider, index, person, j),
                  ),
              ],
            ),
            const SizedBox(height: OmiSpacing.xl),
            OmiSectionHeader(l10n.conversations),
            if (_conversations.isEmpty && _failed)
              OmiErrorState(message: l10n.somethingWentWrongTryAgain, onRetry: _loadMore)
            else if (_conversations.isEmpty && !_loading)
              OmiEmptyState(icon: Icons.forum_outlined, title: l10n.noConversationsYet)
            else if (_conversations.isNotEmpty)
              _Card(
                children: [
                  for (final conversation in _conversations)
                    _ConversationRow(conversation: conversation, onTap: () => _open(conversation)),
                ],
              ),
            if (_loading)
              const Padding(
                padding: EdgeInsets.all(OmiSpacing.lg),
                child: Center(child: OmiSpinner()),
              ),
            if (_failed && _conversations.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: OmiSpacing.md),
                child: OmiButton.secondary(label: l10n.tryAgain, onPressed: _loadMore),
              ),
          ],
        ),
      ),
    );
    return IosNativeSurface(
      title: person.name,
      fallback: classic,
      onRefresh: (_) => _refresh(),
      toolbar: [
        NativeRow('person_back', l10n.back, symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop()),
        NativeRow('person_edit', l10n.editPerson,
            symbol: 'pencil', action: (_) => showPersonNameDialog(context, provider, person: person)),
        NativeRow('person_delete', l10n.deletePersonLabel,
            symbol: 'trash', destructive: true, action: (_) => _confirmDeletePerson(provider, person)),
      ],
      sections: [
        NativeSection('person_confidence', [
          NativeRow('person_evidence', confidenceLabel(context, person.confidence),
              kind: 'navigation',
              subtitle: personReasonLine(context, person),
              level: confidenceLevel(person.confidence),
              action: (_) => showPersonConfidenceSheet(context, person)),
        ]),
        NativeSection('person_stats', [
          NativeRow('person_conversations', l10n.conversations,
              kind: 'label', subtitle: person.conversationCount?.toString() ?? '–'),
          NativeRow('person_talk_time', l10n.personTalkTime,
              kind: 'label',
              subtitle: person.talkSeconds == null ? '–' : OmiDuration.compact(person.talkSeconds!.round(), l10n)),
          NativeRow('person_last_heard', l10n.personLastHeard,
              kind: 'label', subtitle: person.lastHeardAt == null ? '–' : dates.dayHeader(person.lastHeardAt!)),
        ]),
        NativeSection('person_pinning', [
          NativeRow('person_pin', l10n.pinAction,
              subtitle: l10n.pinPersonHonestLine,
              kind: 'toggle',
              value: person.pinned,
              action: (_) => togglePersonPinned(context, provider, person)),
        ]),
        NativeSection(
            'person_samples',
            [
              if (samples.isEmpty) NativeRow('person_no_samples', l10n.voiceSettingsSaveOthersSubtitle, kind: 'label'),
              for (final (sampleIndex, sample) in samples.indexed) ...[
                NativeRow('person_sample_$sampleIndex', l10n.sampleNumber(sampleIndex + 1),
                    subtitle: sampleIndex < transcripts.length ? transcripts[sampleIndex] : '',
                    symbol: provider.currentPlayingPersonIndex == index &&
                            provider.currentPlayingIndex == sampleIndex &&
                            provider.isPlaying
                        ? 'pause.fill'
                        : 'play.fill',
                    action: (_) => provider.playPause(index, sampleIndex, sample)),
                NativeRow('person_delete_sample_$sampleIndex', l10n.delete,
                    symbol: 'trash',
                    destructive: true,
                    action: (_) => _confirmDeleteSample(provider, index, person, sampleIndex)),
              ],
            ],
            title: l10n.speechProfile),
        NativeSection(
            'person_history',
            [
              for (final conversation in _conversations)
                NativeRow(
                    'person_conversation_${conversation.id}',
                    projectNativeConversation(conversation,
                        title: conversation.structured.title,
                        timestamp: dates.timestamp(conversation.startedAt ?? conversation.createdAt),
                        lockedTitle: l10n.conversations,
                        speaker: (_) => '')['title'] as String,
                    kind: 'navigation',
                    subtitle: dates.timestamp(conversation.startedAt ?? conversation.createdAt),
                    symbol: conversation.isLocked ? 'lock.fill' : 'bubble.left',
                    action: (_) => _open(conversation)),
              if (_loading) NativeRow('person_loading', l10n.loading, kind: 'label'),
              if (_failed)
                NativeRow('person_retry', l10n.tryAgain,
                    subtitle: l10n.somethingWentWrongTryAgain, action: (_) => _loadMore()),
              if (!_loading && !_failed && _conversations.isEmpty)
                NativeRow('person_history_empty', l10n.noConversationsYet, kind: 'label'),
              if (_hasMore && !_loading && !_failed)
                NativeRow('person_load_more', l10n.showMore, action: (_) => _loadMore(), onVisible: (_) => _loadMore()),
            ],
            title: l10n.conversations),
      ],
    );
  }
}

/// Large avatar, name, and what Omi knows of their voice.
class _Header extends StatelessWidget {
  const _Header({required this.person});

  final Person person;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        PersonAvatar(person: person, size: 88, ring: OmiColors.surface0),
        const SizedBox(height: OmiSpacing.sm),
        Semantics(
          header: true,
          child: Text(person.name, style: OmiType.title2, textAlign: TextAlign.center),
        ),
        const SizedBox(height: OmiSpacing.xs),
        _ConfidencePill(person: person),
      ],
    );
  }
}

/// The meter, its level and "Why?", as one button that opens the evidence sheet.
class _ConfidencePill extends StatelessWidget {
  const _ConfidencePill({required this.person});

  final Person person;

  @override
  Widget build(BuildContext context) {
    final label = confidenceLabel(context, person.confidence);
    final why = context.l10n.personWhyConfidence;
    return Semantics(
      button: true,
      label: '${context.l10n.confidenceMeterLabel(label)}, $why',
      excludeSemantics: true,
      child: InkWell(
        key: const Key('person_confidence_pill'),
        borderRadius: OmiRadius.pillAll,
        onTap: () => showPersonConfidenceSheet(context, person),
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 44),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.xs),
            decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.pillAll),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                PersonConfidenceMeter(person: person, size: OmiLevelMeterSize.medium),
                const SizedBox(width: OmiSpacing.xs),
                Text(label, style: OmiType.subhead.copyWith(fontWeight: FontWeight.w500)),
                Container(
                  width: 1,
                  height: 16,
                  margin: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm),
                  color: OmiColors.border,
                ),
                Text(why, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Rows in one rounded card, separated by hairlines.
class _Card extends StatelessWidget {
  const _Card({required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: OmiRadius.lgAll,
      child: Material(
        color: OmiColors.surface1,
        child: Column(
          children: [
            for (final (i, child) in children.indexed) ...[
              if (i > 0) Divider(height: 1, thickness: 1, indent: OmiSpacing.md, color: OmiColors.border),
              child,
            ],
          ],
        ),
      ),
    );
  }
}

class _ConversationRow extends StatelessWidget {
  const _ConversationRow({required this.conversation, required this.onTap});

  final ServerConversation conversation;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final seconds = conversation.getDurationInSeconds();
    final when = OmiDateFormat.of(context).timestamp(conversation.startedAt ?? conversation.createdAt);
    final subtitle = seconds > 0 ? '$when · ${OmiDuration.compact(seconds, context.l10n)}' : when;
    return InkWell(
      onTap: onTap,
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: 64),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
          child: Row(
            children: [
              ExcludeSemantics(
                child: Container(
                  width: 40,
                  height: 40,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
                  child: Text(conversation.structured.emoji, style: OmiType.title3, textScaler: TextScaler.noScaling),
                ),
              ),
              const SizedBox(width: OmiSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      conversation.structured.title,
                      style: OmiType.body,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 2),
                    Text(subtitle, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                  ],
                ),
              ),
              Icon(Icons.chevron_right, color: OmiColors.textTertiary),
            ],
          ),
        ),
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
      child: MergeSemantics(
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xs, vertical: OmiSpacing.sm),
          decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.mdAll),
          child: Column(
            children: [
              Text(value, style: OmiType.headline, maxLines: 1, overflow: TextOverflow.ellipsis),
              const SizedBox(height: 2),
              Text(
                label,
                style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ),
        ),
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
