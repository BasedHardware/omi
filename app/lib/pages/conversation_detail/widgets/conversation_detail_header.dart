import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/folder.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_meta.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/share.dart';
import 'package:omi/pages/conversation_detail/widgets.dart';
import 'package:omi/pages/conversation_detail/widgets/calendar_event_sheets.dart';
import 'package:omi/pages/conversation_detail/widgets/capture_recordings.dart';
import 'package:omi/pages/conversations/conversation_action_analytics.dart';
import 'package:omi/pages/conversations/widgets/move_to_folder_sheet.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/utils/conversations/capture_groups.dart';
import 'package:omi/utils/folders/folder_icon_mapper.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/capture_sources.dart';

const _metaColor = OmiColors.textSecondary;

/// The conversation page's header, shared by every tab so switching between
/// Summary, Transcript and Action items never loses the title or the facts.
///
/// Three compact rows: emoji and title (tap to rename); one line of facts
/// (when, how long, category, and the device when only one recorded it); then
/// the controls a reader reaches for — the event's recordings, who spoke, the
/// folder and the visibility.
class ConversationDetailHeader extends StatelessWidget {
  const ConversationDetailHeader({super.key, required this.onOpenRecordings});

  /// Opens the recordings sheet for an event several devices recorded.
  final void Function(List<CaptureRecording> recordings) onOpenRecordings;

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<ConversationDetailProvider>();
    final conversation = provider.conversationOrNull;
    if (conversation == null) return const SizedBox.shrink();
    final recordings = CaptureGroupPresentation.recordings(conversation);
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xxs, OmiSpacing.md, OmiSpacing.sm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _titleRow(context, provider, conversation),
          const SizedBox(height: 6),
          _metaLine(context, conversation, isGroupedEvent: recordings.isNotEmpty),
          const SizedBox(height: 10),
          Consumer<FolderProvider>(
            builder: (context, folderProvider, _) {
              final folderId = conversation.folderId;
              final folder = folderId == null ? null : folderProvider.getFolderById(folderId);
              final people = _people(context, conversation);
              final peopleLabel = ConversationDetailMeta.peopleLabel(
                people.named,
                people.unnamed,
                summary: (first, others) => context.l10n.participantsSummary(first, others),
              );
              return Wrap(
                spacing: 6,
                runSpacing: 6,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  if (recordings.isNotEmpty)
                    CaptureRecordingsChip(
                      recordings: recordings,
                      onTap: () {
                        trackConversationAction(
                            ConversationActionAction.recordingsOpen, ConversationActionSurface.detailBody);
                        onOpenRecordings(recordings);
                      },
                    ),
                  if (peopleLabel != null) _peopleChip(context, conversation, peopleLabel),
                  _FolderChip(conversation: conversation, folder: folder),
                  _VisibilityChip(conversation: conversation),
                ],
              );
            },
          ),
        ],
      ),
    );
  }

  Widget _titleRow(BuildContext context, ConversationDetailProvider provider, ServerConversation conversation) {
    final titleStyle = OmiType.title3.copyWith(height: 1.25);
    // The title is one line, so the emoji centres on it.
    return Row(
      children: [
        if (!conversation.discarded) ...[
          ExcludeSemantics(child: Text(conversation.structured.getEmoji(), style: titleStyle)),
          const SizedBox(width: 10),
        ],
        Expanded(
          child: conversation.discarded
              ? Text(context.l10n.discardedConversation, style: titleStyle)
              : ConversationTitleField(
                  focusNode: provider.titleFocusNode,
                  controller: provider.titleController,
                  style: titleStyle,
                ),
        ),
      ],
    );
  }

  /// "Today · 1:57 PM – 2:59 PM · 1h 2m · Business". A linked calendar event
  /// leads with its logo and opens the event on tap.
  Widget _metaLine(BuildContext context, ServerConversation conversation, {required bool isGroupedEvent}) {
    final dates = OmiDateFormat.of(context);
    final start = conversation.startedAt ?? conversation.createdAt;
    final end = conversation.finishedAt;
    final time = end != null && end.isAfter(start) && conversation.source != ConversationSource.sdcard
        ? dates.timeRange(start, end)
        : dates.time(start);
    // The list row's rule and format, so the page and the row never disagree.
    final duration = conversationDurationLabel(conversation, context.l10n);
    final category = conversation.structured.category.trim();
    final facts = [
      '${dates.dayHeader(start)} · $time',
      if (duration.isNotEmpty) duration,
      if (!conversation.discarded && category.isNotEmpty && category != 'other')
        category[0].toUpperCase() + category.substring(1),
    ];
    // A grouped event names its devices in the recordings control; naming one here
    // would single out whichever recording happens to be open.
    final source = isGroupedEvent ? null : conversation.source?.name;
    final calendarEvent = conversation.calendarEvent;
    final style = OmiType.footnote.copyWith(color: _metaColor, height: 1.35);
    final line = Text.rich(
      TextSpan(
        style: style,
        children: [
          if (calendarEvent != null)
            WidgetSpan(
              alignment: PlaceholderAlignment.middle,
              child: Padding(
                padding: const EdgeInsets.only(right: 6),
                child: ClipRRect(
                  borderRadius: const BorderRadius.all(Radius.circular(3)),
                  child: Image.asset('assets/integration_app_logos/google-calendar.png', width: 14, height: 14),
                ),
              ),
            ),
          TextSpan(text: facts.join(' · ')),
          if (source != null) ...[
            const TextSpan(text: ' · '),
            WidgetSpan(
              alignment: PlaceholderAlignment.middle,
              child: Padding(
                padding: const EdgeInsets.only(right: 3),
                child: Icon(CaptureSources.icon(source), size: 14, color: _metaColor),
              ),
            ),
            TextSpan(text: CaptureSources.label(context, source)),
          ],
        ],
      ),
    );
    if (calendarEvent == null) return line;
    return Semantics(
      button: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () => _showCalendarEvent(context, calendarEvent),
        child: line,
      ),
    );
  }

  /// Who spoke, by name only: the owner as "You" and named people, plus how many unnamed speakers
  /// there were. When the transcript names nobody, a linked calendar event's attendees.
  static ({List<String> named, int unnamed}) _people(BuildContext context, ServerConversation conversation) {
    final speakers = ConversationDetailMeta.participants(
      conversation.transcriptSegments,
      you: context.l10n.you,
      personName: (personId) => SharedPreferencesUtil().getPersonById(personId)?.name,
    );
    if (speakers.named.isNotEmpty) return speakers;
    final attendees = (conversation.calendarEvent?.attendees ?? const []).map(_attendeeName).toList();
    return attendees.isEmpty ? speakers : (named: attendees, unnamed: 0);
  }

  static String _attendeeName(String attendee) {
    if (attendee.contains('@')) {
      final local = attendee.split('@')[0];
      return local.isEmpty ? local : local[0].toUpperCase() + local.substring(1);
    }
    return attendee.split(' ')[0];
  }

  Widget _peopleChip(BuildContext context, ServerConversation conversation, String label) {
    final chip = _HeaderChip(
      icon: const Icon(Icons.people_outline, size: 15, color: OmiColors.textSecondary),
      label: label,
      color: OmiColors.textSecondary,
    );
    final calendarEvent = conversation.calendarEvent;
    if (calendarEvent == null) return Semantics(label: label, excludeSemantics: true, child: chip);
    return Semantics(
      button: true,
      label: label,
      excludeSemantics: true,
      child: GestureDetector(onTap: () => _showCalendarEvent(context, calendarEvent), child: chip),
    );
  }

  static void _showCalendarEvent(BuildContext context, CalendarEventLink calendarEvent) {
    final provider = context.read<ConversationDetailProvider>();
    showCalendarEventDetailsSheet(context, calendarEvent, onUnlink: provider.unlinkCalendarEvent);
  }
}

class _HeaderChip extends StatelessWidget {
  const _HeaderChip({required this.icon, required this.label, required this.color, this.background, this.trailing});

  final Widget icon;
  final String label;
  final Color color;
  final Color? background;
  final bool? trailing;

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(minHeight: 30),
      padding: EdgeInsets.only(left: 10, right: trailing == true ? 6 : 10, top: 4, bottom: 4),
      decoration: BoxDecoration(color: background ?? OmiColors.surface2, borderRadius: OmiRadius.pillAll),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          icon,
          const SizedBox(width: 6),
          Flexible(
            child: Text(
              label,
              style: OmiType.footnote.copyWith(color: color, fontWeight: FontWeight.w500),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          if (trailing == true) ...[
            const SizedBox(width: 2),
            Icon(Icons.keyboard_arrow_down, size: 16, color: color),
          ],
        ],
      ),
    );
  }
}

/// Opens the move-to-folder sheet; tinted with the folder's colour when filed.
class _FolderChip extends StatelessWidget {
  const _FolderChip({required this.conversation, required this.folder});

  final ServerConversation conversation;
  final Folder? folder;

  @override
  Widget build(BuildContext context) {
    final color = folder?.colorValue ?? OmiColors.textSecondary;
    final label = folder?.name ?? context.l10n.noFolder;
    return Semantics(
      button: true,
      label: '${context.l10n.moveToFolder}: $label',
      excludeSemantics: true,
      child: GestureDetector(
        onTap: () {
          trackConversationAction(ConversationActionAction.moveFolder, ConversationActionSurface.detailBody);
          showConversationFolderSheet(context, conversation, source: 'detail_page_sheet');
        },
        child: _HeaderChip(
          icon: FaIcon(folderIconToFa(folder?.icon), size: 12, color: color),
          label: label,
          color: color,
          background: folder?.colorValue.withValues(alpha: 0.2),
          trailing: true,
        ),
      ),
    );
  }
}

/// Moves [conversation] to a folder through the shared sheet and updates the
/// page immediately. Used by the header chip and the overflow menu.
Future<void> showConversationFolderSheet(
  BuildContext context,
  ServerConversation conversation, {
  required String source,
}) async {
  OmiHaptics.selection();
  final currentFolderId = conversation.folderId;
  PlatformManager.instance.analytics.conversationDetailFolderChipClicked(
    conversationId: conversation.id,
    currentFolderId: currentFolderId,
  );
  final folderProvider = Provider.of<FolderProvider>(context, listen: false);
  if (folderProvider.folders.isEmpty) {
    await folderProvider.loadFolders();
  }
  if (!context.mounted) return;
  final newFolderId = await showMoveToFolderSheet(
    context,
    conversationId: conversation.id,
    currentFolderId: currentFolderId,
  );
  // Update locally at once for instant feedback.
  if (newFolderId != null && context.mounted) {
    context.read<ConversationDetailProvider>().updateFolderIdLocally(newFolderId);
    PlatformManager.instance.analytics.conversationMovedToFolder(
      conversationId: conversation.id,
      fromFolderId: currentFolderId,
      toFolderId: newFolderId,
      source: source,
    );
  }
}

class _VisibilityChip extends StatelessWidget {
  const _VisibilityChip({required this.conversation});

  final ServerConversation conversation;

  @override
  Widget build(BuildContext context) {
    final isPrivate = conversation.visibility == ConversationVisibility.private_;
    final color = isPrivate ? OmiColors.textSecondary : OmiColors.success;
    final label = isPrivate ? context.l10n.private : context.l10n.shared;
    return Semantics(
      button: true,
      label: '${context.l10n.visibility}: $label',
      excludeSemantics: true,
      child: GestureDetector(
        onTap: () {
          OmiHaptics.selection();
          trackConversationAction(ConversationActionAction.visibility, ConversationActionSurface.detailBody);
          _showVisibilitySheet(context, conversation);
        },
        child: _HeaderChip(
          icon: Icon(isPrivate ? Icons.lock_outline : Icons.public, size: 14, color: color),
          label: label,
          color: color,
          background: isPrivate ? null : OmiColors.successSurface,
          trailing: true,
        ),
      ),
    );
  }

  static void _showVisibilitySheet(BuildContext context, ServerConversation conversation) {
    final provider = context.read<ConversationDetailProvider>();

    Future<void> choose(BuildContext sheetContext, ConversationVisibility target) async {
      if (conversation.visibility == target) {
        Navigator.pop(sheetContext);
        return;
      }
      final previousVisibility = conversation.visibility;
      provider.updateVisibilityLocally(target);
      Navigator.pop(sheetContext);
      final success = await setConversationVisibility(conversation.id, visibility: target.value);
      if (!success) {
        provider.updateVisibilityLocally(previousVisibility);
        return;
      }
      PlatformManager.instance.analytics.conversationVisibilityChanged(
        conversationId: conversation.id,
        fromVisibility: previousVisibility.value,
        toVisibility: target.value,
      );
      if (target == ConversationVisibility.shared && context.mounted) shareConversationLink(conversation);
    }

    showOmiSheet<void>(
      context: context,
      title: context.l10n.visibility,
      padding: const EdgeInsets.only(bottom: OmiSpacing.md),
      builder: (sheetContext) => Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _option(
            icon: Icons.lock_outline,
            label: context.l10n.private,
            description: context.l10n.onlyYouCanSeeConversation,
            isSelected: conversation.visibility == ConversationVisibility.private_,
            onTap: () => choose(sheetContext, ConversationVisibility.private_),
          ),
          _option(
            icon: Icons.public,
            label: context.l10n.shared,
            description: context.l10n.anyoneWithLinkCanView,
            isSelected: conversation.visibility == ConversationVisibility.shared,
            onTap: () => choose(sheetContext, ConversationVisibility.shared),
          ),
        ],
      ),
    );
  }

  static Widget _option({
    required IconData icon,
    required String label,
    required String description,
    required bool isSelected,
    required VoidCallback onTap,
  }) {
    return Semantics(
      button: true,
      selected: isSelected,
      child: InkWell(
        onTap: onTap,
        borderRadius: OmiRadius.mdAll,
        child: Container(
          margin: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.xxs),
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: 14),
          decoration: BoxDecoration(
            color: isSelected ? OmiColors.surface2 : Colors.transparent,
            borderRadius: OmiRadius.mdAll,
            border: isSelected ? Border.all(color: OmiColors.border) : null,
          ),
          child: Row(
            children: [
              Icon(icon, size: 22, color: isSelected ? OmiColors.textPrimary : OmiColors.textTertiary),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(label, style: OmiType.callout.copyWith(fontWeight: FontWeight.w500)),
                    const SizedBox(height: 2),
                    Text(description, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
                  ],
                ),
              ),
              if (isSelected) const Icon(Icons.check_circle, color: OmiColors.textPrimary, size: 22),
            ],
          ),
        ),
      ),
    );
  }
}
