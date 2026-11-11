import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/review.dart' as api;
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/review.dart';
import 'package:omi/pages/chat/widgets/content_blocks/conversation_link_blocks.dart';
import 'package:omi/pages/review/widgets/review_parts.dart';
import 'package:omi/pages/review/widgets/review_question_card.dart';
import 'package:omi/providers/review_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

typedef EntityPageLoader = Future<ApiResult<EntityPageData>> Function(String entityId);
typedef EntityCorrectionSender = Future<ApiResult<void>> Function(String entityId, String text);

/// A person, organization or project page that Omi keeps current: a short summary, the open
/// threads, what Omi knows (each fact with its source), and recent conversations. One template
/// for every entity type; sections without content are left out.
class EntityPage extends StatefulWidget {
  const EntityPage({super.key, required this.entityId, this.load, this.sendCorrection});

  final String entityId;
  final EntityPageLoader? load;
  final EntityCorrectionSender? sendCorrection;

  @override
  State<EntityPage> createState() => _EntityPageState();
}

class _EntityPageState extends State<EntityPage> {
  EntityPageData? _page;
  bool _failed = false;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    setState(() => _failed = false);
    final result = await (widget.load ?? api.getEntityPage)(widget.entityId);
    if (!mounted) return;
    setState(() {
      switch (result) {
        case ApiSuccess(:final data):
          _page = data;
        case ApiFailure():
          _failed = _page == null;
      }
    });
  }

  Future<void> _correct(EntityPageData page) async {
    final l10n = context.l10n;
    final text = await showOmiSheet<String>(
      context: context,
      title: l10n.entityCorrectionTitle,
      builder: (_) => const _CorrectionSheet(),
    );
    if (text == null || text.trim().isEmpty || !mounted) return;
    final result = await (widget.sendCorrection ?? api.postEntityCorrection)(page.entityId, text.trim());
    if (!mounted) return;
    switch (result) {
      case ApiSuccess():
        OmiFeedback.confirm(context, l10n.entityCorrectionSaved);
      case ApiFailure():
        OmiFeedback.error(context, l10n.entityCorrectionFailed);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final page = _page;
    final Widget body;
    if (page == null && _failed) {
      body = OmiErrorState(message: l10n.entityLoadFailed, onRetry: _refresh);
    } else if (page == null) {
      body = const OmiLoadingState();
    } else {
      body = RefreshIndicator(
        onRefresh: _refresh,
        color: OmiColors.onAccent,
        backgroundColor: OmiColors.accent,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 0, OmiSpacing.md, OmiSpacing.xxl),
          children: _sections(context, page),
        ),
      );
    }
    return Scaffold(
      appBar: AppBar(
        leading: const OmiBackButton(),
        actions: [
          if (page != null)
            OmiIconButton(
              icon: const Icon(Icons.edit_outlined),
              label: l10n.entityCorrectionTitle,
              onPressed: () => _correct(page),
            ),
        ],
      ),
      body: body,
    );
  }

  List<Widget> _sections(BuildContext context, EntityPageData page) {
    final l10n = context.l10n;
    final dates = OmiDateFormat.of(context);
    final question = page.pendingQuestion ?? context.watch<ReviewProvider?>()?.questionAbout(page.entityId);
    final isProject = page.type == EntityType.project;
    return [
      _Header(page: page),
      const SizedBox(height: OmiSpacing.md),
      if (page.summary != null) ...[
        Container(
          padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.md, OmiSpacing.xs, OmiSpacing.xxs),
          decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.only(right: OmiSpacing.xs),
                child: Text(page.summary!, style: OmiType.callout.copyWith(height: 1.4)),
              ),
              Row(
                children: [
                  Expanded(
                    child: Text(
                      l10n.entityKeptCurrent,
                      style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
                    ),
                  ),
                  OmiButton.tertiary(
                    key: const Key('entity_not_right'),
                    label: l10n.entityNotRight,
                    size: OmiButtonSize.compact,
                    onPressed: () => _correct(page),
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: OmiSpacing.md),
      ],
      if (question != null && context.watch<ReviewProvider?>() != null) ...[
        ReviewQuestionCard(item: question),
        const SizedBox(height: OmiSpacing.md),
      ],
      if (page.people.isNotEmpty && page.type != EntityType.person) ...[
        ReviewSectionLabel(label: l10n.people),
        Wrap(
          spacing: OmiSpacing.xs,
          runSpacing: OmiSpacing.xs,
          children: [for (final person in page.people) _EntityPill(entity: person)],
        ),
        const SizedBox(height: OmiSpacing.md),
      ],
      if (page.projects.isNotEmpty && !isProject) ...[
        ReviewSectionLabel(label: l10n.entityProjects),
        for (final project in page.projects)
          _LinkRow(icon: Icons.folder_outlined, title: project.name, entity: project),
        const SizedBox(height: OmiSpacing.md),
      ],
      if (page.decisions.isNotEmpty) ...[
        ReviewSectionLabel(label: l10n.entityDecisions),
        for (final fact in page.decisions) _FactRow(fact: fact, icon: Icons.check),
        const SizedBox(height: OmiSpacing.md),
      ],
      if (page.openTasks.isNotEmpty) ...[
        ReviewSectionLabel(
            label: isProject ? l10n.entityOpenTasks : l10n.entityOpenThreads,
            trailing:
                Text('${page.openTasks.length}', style: OmiType.footnote.copyWith(color: OmiColors.textSecondary))),
        for (final task in page.openTasks)
          _ListRow(
            leading: Icon(Icons.radio_button_unchecked, size: 20, color: OmiColors.textTertiary),
            title: task.description,
            subtitle: [
              if (task.waitingOn != null) l10n.entityWaitingOn(task.waitingOn!),
              if (task.waitingOn == null && task.ownerLabel != null) task.ownerLabel!,
              if (task.dueAt != null) l10n.entityDue(dates.date(task.dueAt!)),
            ].join(' · '),
          ),
        const SizedBox(height: OmiSpacing.md),
      ],
      if (page.facts.isNotEmpty) ...[
        ReviewSectionLabel(label: l10n.entityWhatOmiKnows),
        for (final fact in page.facts) _FactRow(fact: fact),
        const SizedBox(height: OmiSpacing.md),
      ],
      if (page.recentConversations.isNotEmpty) ...[
        ReviewSectionLabel(label: l10n.entityRecentConversations),
        for (final conversation in page.recentConversations)
          Padding(
            padding: const EdgeInsets.only(bottom: OmiSpacing.xs),
            child: Material(
              color: OmiColors.conversationCard,
              borderRadius: OmiRadius.lgAll,
              child: InkWell(
                borderRadius: OmiRadius.lgAll,
                onTap: () => openChatBlockConversation(context, conversationId: conversation.conversationId),
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(14, 12, 8, 12),
                  child: Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(conversation.title, style: OmiType.callout.copyWith(fontWeight: FontWeight.w600)),
                            const SizedBox(height: 3),
                            Text(
                              [
                                if (conversation.startedAt != null) dates.date(conversation.startedAt!),
                                if (conversation.durationSeconds > 0)
                                  OmiDuration.compact(conversation.durationSeconds, l10n),
                              ].join(' · '),
                              style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                            ),
                          ],
                        ),
                      ),
                      Icon(Icons.chevron_right, color: OmiColors.textTertiary),
                    ],
                  ),
                ),
              ),
            ),
          ),
      ],
    ];
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.page});

  final EntityPageData page;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final org = page.organization;
    final isProject = page.type == EntityType.project;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (isProject) ...[
          Row(
            children: [
              Icon(Icons.folder_outlined, size: 18, color: OmiColors.textSecondary),
              const SizedBox(width: 6),
              Text(l10n.entityProject, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
            ],
          ),
          const SizedBox(height: 6),
          Text(page.name, style: OmiType.title1),
        ] else
          Row(
            children: [
              EntityInitialAvatar(name: page.name, type: page.type, size: 64),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(page.name, style: OmiType.title2),
                    if (page.subtitle != null) ...[
                      const SizedBox(height: 4),
                      Text(page.subtitle!, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
                    ],
                  ],
                ),
              ),
            ],
          ),
        if (isProject && page.subtitle != null) ...[
          const SizedBox(height: 4),
          Text(page.subtitle!, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
        ],
        if (org != null || (page.type == EntityType.person && page.projects.isNotEmpty)) ...[
          const SizedBox(height: 10),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              if (org != null)
                ReviewLinkChip(
                    label: org.name, icon: Icons.apartment_outlined, onTap: () => openEntityPage(context, org)),
              if (page.type == EntityType.person)
                for (final project in page.projects.take(2))
                  ReviewLinkChip(
                    label: project.name,
                    icon: Icons.folder_outlined,
                    onTap: () => openEntityPage(context, project),
                  ),
            ],
          ),
        ],
      ],
    );
  }
}

/// "What's not right?": free text that becomes a fact only the user can overrule.
class _CorrectionSheet extends StatefulWidget {
  const _CorrectionSheet();

  @override
  State<_CorrectionSheet> createState() => _CorrectionSheetState();
}

class _CorrectionSheetState extends State<_CorrectionSheet> {
  final _text = TextEditingController();

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Padding(
      padding: const EdgeInsets.only(top: OmiSpacing.xs, bottom: OmiSpacing.md),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          TextField(
            key: const Key('entity_correction_text'),
            controller: _text,
            autofocus: true,
            minLines: 3,
            maxLines: 6,
            maxLength: 2000,
            textCapitalization: TextCapitalization.sentences,
            onChanged: (_) => setState(() {}),
            decoration: InputDecoration(hintText: l10n.entityCorrectionHint),
          ),
          const SizedBox(height: OmiSpacing.sm),
          OmiButton(
            label: l10n.save,
            expand: true,
            onPressed: _text.text.trim().isEmpty ? null : () => Navigator.of(context).pop(_text.text.trim()),
          ),
        ],
      ),
    );
  }
}

/// Pushes the page for [entity].
Future<void> openEntityPage(BuildContext context, EntityRef entity) =>
    routeToPage(context, EntityPage(entityId: entity.entityId));

class _EntityPill extends StatelessWidget {
  const _EntityPill({required this.entity});

  final EntityRef entity;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: OmiColors.surface1,
      shape: const StadiumBorder(),
      child: InkWell(
        customBorder: const StadiumBorder(),
        onTap: () => openEntityPage(context, entity),
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 44),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(8, 8, 14, 8),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                EntityInitialAvatar(name: entity.name, type: entity.type),
                const SizedBox(width: 8),
                Text(entity.name, style: OmiType.subhead.copyWith(fontWeight: FontWeight.w500)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _LinkRow extends StatelessWidget {
  const _LinkRow({required this.icon, required this.title, required this.entity});

  final IconData icon;
  final String title;
  final EntityRef entity;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: OmiSpacing.xs),
      child: Material(
        color: OmiColors.surface1,
        borderRadius: OmiRadius.lgAll,
        child: InkWell(
          borderRadius: OmiRadius.lgAll,
          onTap: () => openEntityPage(context, entity),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(14, 12, 8, 12),
            child: Row(
              children: [
                Icon(icon, size: 20, color: OmiColors.textSecondary),
                const SizedBox(width: OmiSpacing.sm),
                Expanded(child: Text(title, style: OmiType.callout.copyWith(fontWeight: FontWeight.w600))),
                Icon(Icons.chevron_right, color: OmiColors.textTertiary),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ListRow extends StatelessWidget {
  const _ListRow({required this.leading, required this.title, this.subtitle = ''});

  final Widget leading;
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 10, horizontal: OmiSpacing.xxs),
      decoration: BoxDecoration(border: Border(top: BorderSide(color: OmiColors.border, width: 0.5))),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(padding: const EdgeInsets.only(top: 1), child: leading),
          const SizedBox(width: OmiSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: OmiType.callout),
                if (subtitle.isNotEmpty) ...[
                  const SizedBox(height: 2),
                  Text(subtitle, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _FactRow extends StatelessWidget {
  const _FactRow({required this.fact, this.icon});

  final Fact fact;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final dates = OmiDateFormat.of(context);
    final sourceIcon = switch (fact.sourceKind) {
      FactSourceKind.conversation => Icons.chat_bubble_outline,
      FactSourceKind.chat => Icons.forum_outlined,
      FactSourceKind.screen => Icons.desktop_windows_outlined,
      FactSourceKind.user => Icons.person_outline,
    };
    final label = [fact.sourceLabel, if (fact.at != null) dates.date(fact.at!)].where((s) => s.isNotEmpty).join(' · ');
    return Container(
      padding: const EdgeInsets.symmetric(vertical: OmiSpacing.sm, horizontal: OmiSpacing.xxs),
      decoration: BoxDecoration(border: Border(top: BorderSide(color: OmiColors.border, width: 0.5))),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (icon != null) ...[
            Padding(
                padding: const EdgeInsets.only(top: 2), child: Icon(icon, size: 18, color: OmiColors.textSecondary)),
            const SizedBox(width: OmiSpacing.sm),
          ],
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(fact.text, style: OmiType.callout),
                if (label.isNotEmpty) ...[
                  const SizedBox(height: 6),
                  ReviewLinkChip(
                    label: label,
                    icon: sourceIcon,
                    onTap: fact.conversationId == null
                        ? null
                        : () => openChatBlockConversation(context, conversationId: fact.conversationId!),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}
