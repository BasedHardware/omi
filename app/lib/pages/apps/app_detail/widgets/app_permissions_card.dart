import 'package:flutter/material.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

enum _PermissionKind { access, create, trigger }

class _Permission {
  const _Permission(this.kind, this.title);

  final _PermissionKind kind;
  final String title;
}

/// The rounded card every section of the app detail page sits in.
class AppDetailSectionCard extends StatelessWidget {
  const AppDetailSectionCard({super.key, required this.title, required this.child, this.trailing});

  final String title;
  final Widget child;

  /// Shown at the end of the title row (a chevron when the card opens a page).
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final inset = MediaQuery.sizeOf(context).width * 0.05;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(OmiSpacing.md),
      margin: EdgeInsets.only(left: inset, right: inset, top: OmiSpacing.sm, bottom: 6),
      decoration: BoxDecoration(color: OmiColors.surface1.withValues(alpha: 0.8), borderRadius: OmiRadius.lgAll),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Semantics(
                  header: true,
                  child: Text(title, style: OmiType.callout.copyWith(fontWeight: FontWeight.w600)),
                ),
              ),
              if (trailing != null) trailing!,
            ],
          ),
          const SizedBox(height: OmiSpacing.md),
          child,
        ],
      ),
    );
  }
}

/// What an app that works outside Omi can read, create and what starts it.
///
/// Renders nothing for apps that stay inside Omi or declare no actions or trigger.
class AppPermissionsCard extends StatelessWidget {
  const AppPermissionsCard({super.key, required this.app});

  final App app;

  List<_Permission> _permissions(BuildContext context) {
    final l10n = context.l10n;
    final actions = app.externalIntegration?.actions ?? [];
    bool has(String action) => actions.any((a) => a.action == action);
    final trigger = app.externalIntegration?.getTriggerOnString();
    return [
      if (has('read_conversations')) _Permission(_PermissionKind.access, l10n.permissionReadConversations),
      if (has('read_memories')) _Permission(_PermissionKind.access, l10n.permissionReadMemories),
      if (has('read_tasks')) _Permission(_PermissionKind.access, l10n.permissionReadTasks),
      if (has('create_conversation')) _Permission(_PermissionKind.create, l10n.permissionCreateConversations),
      if (has('create_facts')) _Permission(_PermissionKind.create, l10n.permissionCreateMemories),
      if (trigger != null && trigger != 'Unknown')
        _Permission(
          _PermissionKind.trigger,
          trigger == 'Transcript Segment Processed' ? l10n.realtimeListening : trigger,
        ),
    ];
  }

  @override
  Widget build(BuildContext context) {
    if (!app.worksExternally()) return const SizedBox.shrink();
    final permissions = _permissions(context);
    if (permissions.isEmpty) return const SizedBox.shrink();

    return AppDetailSectionCard(
      title: context.l10n.permissionsAndTriggers,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final (index, permission) in permissions.indexed)
            Padding(
              padding: EdgeInsets.only(bottom: index == permissions.length - 1 ? 0 : OmiSpacing.xs),
              child: _PermissionRow(permission: permission),
            ),
        ],
      ),
    );
  }
}

class _PermissionRow extends StatelessWidget {
  const _PermissionRow({required this.permission});

  final _Permission permission;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final (label, color) = switch (permission.kind) {
      _PermissionKind.access => (l10n.permissionTypeAccess, OmiColors.success),
      _PermissionKind.create => (l10n.permissionTypeCreate, OmiColors.warning),
      _PermissionKind.trigger => (l10n.permissionTypeTrigger, OmiColors.textSecondary),
    };
    return Row(
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: OmiSpacing.xxs),
          decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: OmiRadius.mdAll),
          child: Text(label, style: OmiType.caption.copyWith(color: color, fontWeight: FontWeight.w600)),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            permission.title,
            style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w500),
          ),
        ),
      ],
    );
  }
}

/// The chat tools an app adds to Omi's chat, as chips.
class AppChatToolsCard extends StatelessWidget {
  const AppChatToolsCard({super.key, required this.app});

  final App app;

  /// "send_slack_message" → "Send Slack Message".
  static String formatToolName(String name) {
    return name
        .split('_')
        .map((word) => word.isNotEmpty ? '${word[0].toUpperCase()}${word.substring(1).toLowerCase()}' : '')
        .join(' ');
  }

  @override
  Widget build(BuildContext context) {
    final tools = app.chatTools;
    if (tools == null || tools.isEmpty) return const SizedBox.shrink();
    return AppDetailSectionCard(
      title: context.l10n.chatFeatures,
      child: Wrap(
        spacing: OmiSpacing.sm,
        runSpacing: OmiSpacing.sm,
        children: [
          for (final tool in tools)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: OmiSpacing.xs),
              decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
              child: Text(
                formatToolName(tool.name),
                style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w500),
              ),
            ),
        ],
      ),
    );
  }
}
