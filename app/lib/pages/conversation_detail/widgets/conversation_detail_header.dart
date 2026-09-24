import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/folder.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_meta.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/share.dart';
import 'package:omi/pages/conversation_detail/widgets.dart';
import 'package:omi/pages/conversation_detail/widgets/capture_recordings.dart';
import 'package:omi/pages/conversations/widgets/move_to_folder_sheet.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/utils/conversations/capture_groups.dart';
import 'package:omi/utils/folders/folder_icon_mapper.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/other/time_utils.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/capture_sources.dart';
import 'package:omi/widgets/extensions/string.dart';

const _metaColor = Color(0xFF9A9BA1);
const _chipText = TextStyle(fontSize: 13, fontWeight: FontWeight.w500);

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
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 12),
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
              return Wrap(
                spacing: 6,
                runSpacing: 6,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  if (recordings.isNotEmpty)
                    CaptureRecordingsChip(recordings: recordings, onTap: () => onOpenRecordings(recordings)),
                  if (people.isNotEmpty) _peopleChip(context, conversation, people),
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
    const titleStyle = TextStyle(fontSize: 22, height: 1.25, fontWeight: FontWeight.w600, color: Colors.white);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (!conversation.discarded) ...[
          Padding(
            padding: const EdgeInsets.only(top: 1),
            child: Text(conversation.structured.getEmoji(), style: const TextStyle(fontSize: 22, height: 1.25)),
          ),
          const SizedBox(width: 10),
        ],
        Expanded(
          child: conversation.discarded
              ? Text(context.l10n.discardedConversation, style: titleStyle)
              : GetEditTextField(
                  conversationId: conversation.id,
                  focusNode: provider.titleFocusNode,
                  controller: provider.titleController,
                  content: conversation.structured.title.decodeString,
                  style: titleStyle,
                ),
        ),
      ],
    );
  }

  /// "Today · 1:57 PM – 2:59 PM · 1h 2m · Business". A linked calendar event
  /// leads with its logo and opens the event on tap.
  Widget _metaLine(BuildContext context, ServerConversation conversation, {required bool isGroupedEvent}) {
    final start = conversation.startedAt ?? conversation.createdAt;
    final locale = Localizations.localeOf(context).languageCode;
    final end = conversation.finishedAt;
    final time = end != null && end.isAfter(start) && conversation.source != ConversationSource.sdcard
        ? '${dateTimeFormat('h:mm a', start, locale: locale)} – ${dateTimeFormat('h:mm a', end, locale: locale)}'
        : dateTimeFormat('h:mm a', start, locale: locale);
    final duration = _duration(context, conversation);
    final category = conversation.structured.category.trim();
    final facts = [
      '${_day(context, start)} · $time',
      if (duration.isNotEmpty) duration,
      if (!conversation.discarded && category.isNotEmpty && category != 'other')
        category[0].toUpperCase() + category.substring(1),
    ];
    // A grouped event names its devices in the recordings control; naming one here
    // would single out whichever recording happens to be open.
    final source = isGroupedEvent ? null : conversation.source?.name;
    final calendarEvent = conversation.calendarEvent;
    const style = TextStyle(color: _metaColor, fontSize: 13.5, height: 1.35);
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
                  borderRadius: BorderRadius.circular(3),
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

  static String _day(BuildContext context, DateTime date) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final day = DateTime(date.year, date.month, date.day);
    final locale = Localizations.localeOf(context).languageCode;
    if (day == today) return context.l10n.today;
    if (day == today.subtract(const Duration(days: 1))) return context.l10n.yesterday;
    return dateTimeFormat(date.year == now.year ? 'EEE, MMM d' : 'MMM d, yyyy', date, locale: locale);
  }

  static String _duration(BuildContext context, ServerConversation conversation) {
    if (conversation.transcriptSegments.isEmpty) return '';
    final seconds = conversation.getDurationInSeconds();
    return seconds <= 0 ? '' : secondsToCompactDuration(seconds, context);
  }

  /// Who spoke, from the transcript; a linked calendar event's attendees when
  /// the transcript names no one.
  static List<String> _people(BuildContext context, ServerConversation conversation) {
    final segments = conversation.transcriptSegments;
    final speakers = ConversationDetailMeta.participants(
      segments,
      you: context.l10n.you,
      speaker: (id) => context.l10n.speakerWithId('${TranscriptSegment.getDisplaySpeakerId(id, segments)}'),
      personName: (personId) => SharedPreferencesUtil().getPersonById(personId)?.name,
    );
    if (speakers.isNotEmpty) return speakers;
    return (conversation.calendarEvent?.attendees ?? const []).map(_attendeeName).toList();
  }

  static String _attendeeName(String attendee) {
    if (attendee.contains('@')) {
      final local = attendee.split('@')[0];
      return local.isEmpty ? local : local[0].toUpperCase() + local.substring(1);
    }
    return attendee.split(' ')[0];
  }

  Widget _peopleChip(BuildContext context, ServerConversation conversation, List<String> people) {
    final chip = _HeaderChip(
      icon: Icon(Icons.people_outline, size: 15, color: Colors.grey.shade300),
      label: ConversationDetailMeta.peopleSummary(people),
      color: Colors.grey.shade300,
    );
    final calendarEvent = conversation.calendarEvent;
    if (calendarEvent == null) return Semantics(label: people.join(', '), excludeSemantics: true, child: chip);
    return Semantics(
      button: true,
      label: people.join(', '),
      excludeSemantics: true,
      child: GestureDetector(onTap: () => _showCalendarEvent(context, calendarEvent), child: chip),
    );
  }

  static void _showCalendarEvent(BuildContext context, CalendarEventLink calendarEvent) {
    final provider = context.read<ConversationDetailProvider>();
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (_) => CalendarEventDetailsSheet(
        calendarEvent: calendarEvent,
        onUnlink: () async {
          await provider.unlinkCalendarEvent();
        },
      ),
    );
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
      height: 30,
      padding: EdgeInsets.only(left: 10, right: trailing == true ? 6 : 10),
      decoration: BoxDecoration(
        color: background ?? Colors.grey.withValues(alpha: 0.16),
        borderRadius: BorderRadius.circular(15),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          icon,
          const SizedBox(width: 6),
          Flexible(
            child: Text(label, style: _chipText.copyWith(color: color), maxLines: 1, overflow: TextOverflow.ellipsis),
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
    final color = folder?.colorValue ?? Colors.grey.shade300;
    final label = folder?.name ?? context.l10n.noFolder;
    return Semantics(
      button: true,
      label: '${context.l10n.moveToFolder}: $label',
      excludeSemantics: true,
      child: GestureDetector(
        onTap: () => showConversationFolderSheet(context, conversation, source: 'detail_page_sheet'),
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
  HapticFeedback.selectionClick();
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
    final color = isPrivate ? Colors.grey.shade300 : Colors.green;
    final label = isPrivate ? context.l10n.private : context.l10n.shared;
    return Semantics(
      button: true,
      label: '${context.l10n.visibility}: $label',
      excludeSemantics: true,
      child: GestureDetector(
        onTap: () {
          HapticFeedback.selectionClick();
          _showVisibilitySheet(context, conversation);
        },
        child: _HeaderChip(
          icon: Icon(isPrivate ? Icons.lock_outline : Icons.public, size: 14, color: color),
          label: label,
          color: color,
          background: isPrivate ? null : color.withValues(alpha: 0.2),
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

    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF1C1C1E),
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (sheetContext) {
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 20, 20, 16),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      context.l10n.visibility,
                      style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600, color: Colors.white),
                    ),
                    GestureDetector(
                      onTap: () => Navigator.pop(sheetContext),
                      child: Icon(Icons.close, color: Colors.grey.shade500, size: 24),
                    ),
                  ],
                ),
              ),
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
              const SizedBox(height: 16),
            ],
          ),
        );
      },
    );
  }

  static Widget _option({
    required IconData icon,
    required String label,
    required String description,
    required bool isSelected,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        decoration: BoxDecoration(
          color: isSelected ? Colors.white.withValues(alpha: 0.08) : Colors.transparent,
          borderRadius: BorderRadius.circular(12),
          border: isSelected ? Border.all(color: Colors.white.withValues(alpha: 0.15)) : null,
        ),
        child: Row(
          children: [
            Icon(icon, size: 22, color: isSelected ? Colors.green : Colors.grey.shade400),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(label, style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500)),
                  const SizedBox(height: 2),
                  Text(description, style: TextStyle(color: Colors.grey.shade500, fontSize: 13)),
                ],
              ),
            ),
            if (isSelected) const Icon(Icons.check_circle, color: Colors.green, size: 22),
          ],
        ),
      ),
    );
  }
}
