// Episode member list with disclosure of the existing Home noise classification.
// Unknown classifications stay visible; canonical row interactions remain intact.

import 'package:flutter/material.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

class EpisodeConversations extends StatefulWidget {
  const EpisodeConversations({super.key, required this.members, this.metadata = const {}});
  final List<ServerConversation> members;
  final Map<String, ServerConversation> metadata;

  @override
  State<EpisodeConversations> createState() => _EpisodeConversationsState();
}

class _EpisodeConversationsState extends State<EpisodeConversations> {
  bool _showNoise = false;

  Widget _row(ServerConversation member) => ConversationListItem(
        key: ValueKey('episode_member_${member.id}'),
        conversation: member,
        date: member.startedAt ?? member.createdAt,
        conversationIdx: -1,
        embedded: true,
        compact: true,
        compactOverview:
            member.structured.overview.trim().isEmpty ? widget.metadata[member.id]?.structured.overview : null,
        allowSelection: false,
        openEpisodeFromSearch: false,
      );

  String? _step(ServerConversation member) => member.homeStep ?? widget.metadata[member.id]?.homeStep;

  @override
  Widget build(BuildContext context) {
    // Unknown/legacy classifications remain visible. Never infer noise from text or length.
    final noise = widget.members.where((m) => _step(m) == 'noise').toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final member in widget.members.where((m) => _step(m) != 'noise')) _row(member),
        if (noise.isNotEmpty) ...[
          if (_showNoise) ...[for (final member in noise) _row(member)],
          Wrap(
            crossAxisAlignment: WrapCrossAlignment.center,
            spacing: OmiSpacing.xs,
            children: [
              if (!_showNoise)
                Text(context.l10n.homeNoiseFoldHidden(noise.length),
                    style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
              OmiButton.tertiary(
                key: const Key('noise_toggle'),
                label: _showNoise ? context.l10n.homeNoiseFoldHide(noise.length) : context.l10n.homeNoiseFoldShow,
                icon: _showNoise ? Icons.expand_less : Icons.expand_more,
                size: OmiButtonSize.compact,
                onPressed: () => setState(() => _showNoise = !_showNoise),
              ),
            ],
          ),
        ],
      ],
    );
  }
}
