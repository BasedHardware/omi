import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/chat/chat_provider.dart';
import 'package:nooto_v2/chat/chat_session.dart';
import 'package:nooto_v2/chat/widgets/session_actions_sheet.dart';
import 'package:nooto_v2/theme/app_theme.dart';

/// ChatGPT-style left drawer that lists chat sessions grouped by date bucket.
///
/// Read source for [ChatProvider]: sessions, currentSessionId, sending.
/// Mutations exposed: `newSession()`, `selectSession(id)`, `togglePin(id)`.
/// The long-press affordance opens a session-options bottom sheet — wiring
/// for that lives in the integration phase, so this widget just exposes a
/// `onLongPress` callback per row and uses a no-op placeholder by default.
///
/// Mirrors the desktop-v2 `ChatSessionsSidebar` date-grouping (Today /
/// Yesterday / This week / Older) plus a "Pinned" group above the buckets.
class ChatSessionsDrawer extends StatelessWidget {
  const ChatSessionsDrawer({super.key});

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<ChatProvider>();
    final mediaWidth = MediaQuery.of(context).size.width;
    final drawerWidth = (mediaWidth * 0.85).clamp(0.0, 360.0);

    return SizedBox(
      width: drawerWidth,
      child: Drawer(
        backgroundColor: AppColors.backgroundPrimary,
        elevation: 0,
        shape: const Border(
          right: BorderSide(color: Color(0x0FFFFFFF), width: 0.5),
        ),
        child: SafeArea(
          child: Column(
            children: [
              _Header(
                onNewChat: () {
                  provider.newSession();
                  Navigator.pop(context);
                },
              ),
              Expanded(
                child: provider.sessions.isEmpty
                    ? const _EmptyState()
                    : _SessionsList(
                        sessions: provider.sessions,
                        currentSessionId: provider.currentSessionId,
                        sending: provider.sending,
                        onSelect: (id) {
                          provider.selectSession(id);
                          Navigator.pop(context);
                        },
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.onNewChat});

  final VoidCallback onNewChat;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppStyles.spacingS,
        AppStyles.spacingS,
        AppStyles.spacingS,
        AppStyles.spacingXS,
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onNewChat,
          borderRadius: BorderRadius.circular(AppStyles.radiusMedium),
          child: Padding(
            padding: const EdgeInsets.symmetric(
              horizontal: AppStyles.spacingM,
              vertical: AppStyles.spacingM,
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  Icons.edit_outlined,
                  size: 18,
                  color: AppColors.textPrimary,
                ),
                const SizedBox(width: AppStyles.spacingM),
                Text(
                  'New chat',
                  style: TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w500,
                    color: AppColors.textPrimary,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState();

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: AppStyles.spacingXL),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              'No chats yet',
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w600,
                color: AppColors.textPrimary,
              ),
            ),
            SizedBox(height: AppStyles.spacingS),
            Text(
              'Start a conversation to see it here.',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 14,
                color: AppColors.textTertiary,
                height: 1.5,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SessionsList extends StatelessWidget {
  const _SessionsList({
    required this.sessions,
    required this.currentSessionId,
    required this.sending,
    required this.onSelect,
  });

  final List<ChatSession> sessions;
  final String? currentSessionId;
  final bool sending;
  final ValueChanged<String> onSelect;

  @override
  Widget build(BuildContext context) {
    final groups = _groupSessions(sessions, DateTime.now());

    final children = <Widget>[];
    for (final group in groups) {
      children.add(_GroupLabel(label: group.label));
      for (final session in group.sessions) {
        final isActive = session.id == currentSessionId;
        final isStreaming = sending && isActive;
        children.add(
          _SessionRow(
            session: session,
            isActive: isActive,
            isStreaming: isStreaming,
            onTap: () => onSelect(session.id),
            onLongPress: () => showSessionActionsSheet(context, session),
          ),
        );
      }
    }

    return ListView(
      padding: const EdgeInsets.only(bottom: AppStyles.spacingL),
      children: children,
    );
  }
}

class _GroupLabel extends StatelessWidget {
  const _GroupLabel({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(
        left: AppStyles.spacingL,
        right: AppStyles.spacingL,
        top: AppStyles.spacingS,
        bottom: AppStyles.spacingXS,
      ),
      child: Text(
        label,
        style: const TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w600,
          color: AppColors.textTertiary,
          letterSpacing: 0.4,
        ),
      ),
    );
  }
}

class _SessionRow extends StatelessWidget {
  const _SessionRow({
    required this.session,
    required this.isActive,
    required this.isStreaming,
    required this.onTap,
    required this.onLongPress,
  });

  final ChatSession session;
  final bool isActive;
  final bool isStreaming;
  final VoidCallback onTap;
  final VoidCallback onLongPress;

  @override
  Widget build(BuildContext context) {
    final hasPreview = session.preview != null && session.preview!.isNotEmpty;
    final relative = _relativeTime(session.updatedAt);

    final semanticsLabel = _buildSemanticsLabel(
      title: session.title,
      preview: hasPreview ? session.preview : null,
      relative: relative,
      isActive: isActive,
      isStreaming: isStreaming,
    );

    return Semantics(
      button: true,
      label: semanticsLabel,
      child: Material(
        color: isActive ? AppColors.backgroundSecondary : Colors.transparent,
        child: InkWell(
          onTap: onTap,
          onLongPress: () {
            HapticFeedback.mediumImpact();
            onLongPress();
          },
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 56),
            child: Padding(
              padding: const EdgeInsets.symmetric(
                horizontal: AppStyles.spacingL,
                vertical: AppStyles.spacingM,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Row(
                    children: [
                      if (session.pinned) ...[
                        const Icon(
                          Icons.push_pin_rounded,
                          size: 14,
                          color: AppColors.textTertiary,
                        ),
                        const SizedBox(width: 4),
                      ],
                      if (isStreaming) ...[
                        Container(
                          width: 6,
                          height: 6,
                          decoration: const BoxDecoration(
                            shape: BoxShape.circle,
                            color: AppColors.brandPrimary,
                          ),
                        ),
                        const SizedBox(width: 6),
                      ],
                      Expanded(
                        child: Text(
                          session.title,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: 15,
                            fontWeight: FontWeight.w600,
                            color: isActive
                                ? AppColors.brandPrimary
                                : AppColors.textPrimary,
                          ),
                        ),
                      ),
                      const SizedBox(width: AppStyles.spacingS),
                      Text(
                        relative,
                        style: const TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w500,
                          color: AppColors.textQuaternary,
                          letterSpacing: 0.2,
                        ),
                      ),
                    ],
                  ),
                  if (hasPreview) ...[
                    const SizedBox(height: 4),
                    Text(
                      session.preview!,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 13,
                        color: AppColors.textTertiary,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  String _buildSemanticsLabel({
    required String title,
    required String? preview,
    required String relative,
    required bool isActive,
    required bool isStreaming,
  }) {
    final buffer = StringBuffer();
    if (isActive) buffer.write('Currently open. ');
    if (isStreaming) buffer.write('Receiving response. ');
    buffer.write('Chat: $title. ');
    if (preview != null) buffer.write('$preview. ');
    buffer.write('$relative. ');
    buffer.write('Double-tap to open. Long press for options.');
    return buffer.toString();
  }
}

// ---------------------------------------------------------------------------
// Grouping + relative time helpers
// ---------------------------------------------------------------------------

class _Group {
  _Group(this.label) : sessions = [];

  final String label;
  final List<ChatSession> sessions;
}

/// Splits sessions into Pinned + Today / Yesterday / This week / Older
/// buckets. Pinned is always first; pinned sessions do not also appear in a
/// date bucket. Each group sorted by `updatedAt` desc. Empty groups dropped.
List<_Group> _groupSessions(List<ChatSession> sessions, DateTime now) {
  final pinned = _Group('PINNED');
  final today = _Group('TODAY');
  final yesterday = _Group('YESTERDAY');
  final thisWeek = _Group('THIS WEEK');
  final older = _Group('OLDER');

  for (final s in sessions) {
    if (s.pinned) {
      pinned.sessions.add(s);
      continue;
    }
    switch (_bucketFor(s.updatedAt, now)) {
      case 'TODAY':
        today.sessions.add(s);
        break;
      case 'YESTERDAY':
        yesterday.sessions.add(s);
        break;
      case 'THIS WEEK':
        thisWeek.sessions.add(s);
        break;
      default:
        older.sessions.add(s);
    }
  }

  int byUpdatedDesc(ChatSession a, ChatSession b) =>
      b.updatedAt.compareTo(a.updatedAt);

  for (final g in [pinned, today, yesterday, thisWeek, older]) {
    g.sessions.sort(byUpdatedDesc);
  }

  return [pinned, today, yesterday, thisWeek, older]
      .where((g) => g.sessions.isNotEmpty)
      .toList();
}

/// Returns "TODAY" / "YESTERDAY" / "THIS WEEK" / "OLDER" for a session's
/// updatedAt vs `now`. Calendar-day aware (not 24-hour windows) so a chat
/// from 11pm yesterday lands in "YESTERDAY", not "TODAY".
String _bucketFor(DateTime updatedAt, DateTime now) {
  final updatedDay = DateTime(updatedAt.year, updatedAt.month, updatedAt.day);
  final today = DateTime(now.year, now.month, now.day);
  final daysAgo = today.difference(updatedDay).inDays;
  if (daysAgo <= 0) return 'TODAY';
  if (daysAgo == 1) return 'YESTERDAY';
  if (daysAgo < 7) return 'THIS WEEK';
  return 'OLDER';
}

/// Compact relative time for the row trailing label.
/// "now" (<60s), "5m" (<60min), "2h" (<24h), "3d" (<7d), "Apr 28" (older).
String _relativeTime(DateTime t) {
  final now = DateTime.now();
  final diff = now.difference(t);
  if (diff.inSeconds < 60) return 'now';
  if (diff.inMinutes < 60) return '${diff.inMinutes}m';
  if (diff.inHours < 24) return '${diff.inHours}h';
  if (diff.inDays < 7) return '${diff.inDays}d';
  const months = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
  ];
  return '${months[t.month - 1]} ${t.day}';
}
