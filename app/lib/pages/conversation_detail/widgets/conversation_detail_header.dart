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
import 'package:omi/pages/conversation_detail/widgets/conversation_detail_chip.dart';
import 'package:omi/pages/conversations/conversation_action_analytics.dart';
import 'package:omi/pages/conversations/widgets/move_to_folder_sheet.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/utils/conversations/capture_groups.dart';
import 'package:omi/utils/conversations/conversation_title.dart';
import 'package:omi/utils/folders/folder_icon_mapper.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// The conversation page's header (v3), shared by both tabs so switching between Summary and
/// Transcript never loses the title or the facts.
///
/// The title in large type (tap to rename), then one row of outlined chips: when it started and how
/// long it ran, the folder, and — when they apply — who spoke and the event's recordings. Visibility
/// lives in the ⋯ menu ([ConversationVisibilitySheet]).
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
          const SizedBox(height: 14),
          Consumer<FolderProvider>(
            builder: (context, folderProvider, _) {
              final folderId = conversation.folderId;
              final folder = folderId == null ? null : folderProvider.getFolderById(folderId);
              final people = _people(context, conversation);
              final peopleLabel = ConversationDetailMeta.peopleLabel(
                people.named,
                people.unnamed,
                uncounted: people.uncounted,
                summary: (first, others) => context.l10n.participantsSummary(first, others),
                uncountedSummary: context.l10n.participantsSummaryUncounted,
              );
              return Wrap(
                spacing: 8,
                runSpacing: 8,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  _whenChip(context, conversation),
                  _FolderChip(conversation: conversation, folder: folder),
                  if (peopleLabel != null)
                    _peopleChip(
                      context,
                      conversation,
                      peopleLabel,
                      ConversationDetailMeta.avatars(people.named, people.unnamed, uncounted: people.uncounted),
                    ),
                  if (recordings.isNotEmpty)
                    CaptureRecordingsChip(
                      recordings: recordings,
                      onTap: () {
                        trackConversationAction(
                          ConversationActionAction.recordingsOpen,
                          ConversationActionSurface.detailBody,
                        );
                        onOpenRecordings(recordings);
                      },
                    ),
                ],
              );
            },
          ),
        ],
      ),
    );
  }

  Widget _titleRow(BuildContext context, ConversationDetailProvider provider, ServerConversation conversation) {
    final titleStyle = OmiType.title1.copyWith(height: 1.15, letterSpacing: -0.4);
    if (conversation.discarded) return Text(context.l10n.discardedConversation, style: titleStyle);
    return ConversationTitleField(
      focusNode: provider.titleFocusNode,
      controller: provider.titleController,
      style: titleStyle,
      hintText: transcriptFallbackTitle(conversation),
    );
  }

  /// "Today 12:40 PM · 14m": when it started and how long it ran, the list row's length rule. A
  /// linked calendar event shows its logo and opens the event.
  Widget _whenChip(BuildContext context, ServerConversation conversation) {
    final dates = OmiDateFormat.of(context);
    final start = conversation.startedAt ?? conversation.createdAt;
    final duration = conversationDurationLabel(conversation, context.l10n);
    final label = [
      '${dates.dayHeader(start)} ${dates.time(start)}',
      if (duration.isNotEmpty) duration,
    ].join(' · ');
    final calendarEvent = conversation.calendarEvent;
    final chip = ConversationDetailChip(
      key: const Key('conversation_when'),
      icon: calendarEvent == null
          ? const Icon(Icons.calendar_today_outlined)
          : ClipRRect(
              borderRadius: const BorderRadius.all(Radius.circular(3)),
              child: Image.asset('assets/integration_app_logos/google-calendar.png', width: 15, height: 15),
            ),
      label: label,
    );
    if (calendarEvent == null) return Semantics(label: label, excludeSemantics: true, child: chip);
    return Semantics(
      button: true,
      label: label,
      excludeSemantics: true,
      child: GestureDetector(onTap: () => _showCalendarEvent(context, calendarEvent), child: chip),
    );
  }

  /// Who spoke, by name only: the owner as "You" and named people, plus how many unnamed voices
  /// took part. When the transcript names nobody, a linked calendar event's attendees.
  static ({List<String> named, int unnamed, bool uncounted}) _people(
    BuildContext context,
    ServerConversation conversation,
  ) {
    final speakers = ConversationDetailMeta.participants(
      conversation.transcriptSegments,
      you: context.l10n.you,
      personName: (personId) => SharedPreferencesUtil().getPersonById(personId)?.name,
      speakers: conversation.speakerResolution,
    );
    if (speakers.named.isNotEmpty) return speakers;
    final attendees = (conversation.calendarEvent?.attendees ?? const []).map(_attendeeName).toList();
    return attendees.isEmpty ? speakers : (named: attendees, unnamed: 0, uncounted: false);
  }

  static String _attendeeName(String attendee) {
    if (attendee.contains('@')) {
      final local = attendee.split('@')[0];
      return local.isEmpty ? local : local[0].toUpperCase() + local.substring(1);
    }
    return attendee.split(' ')[0];
  }

  /// Who spoke: their avatars, overlapping, then "You + 1 other".
  Widget _peopleChip(BuildContext context, ServerConversation conversation, String label, List<String> avatars) {
    final chip = ConversationDetailChip(
      key: const Key('conversation_people'),
      icon: _PeopleAvatars(avatars),
      label: label,
      startPadding: 6,
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

/// Overlapping 22 pt circles, the first on top: the first person in the primary ink with a ring of
/// the page colour, the rest in a quieter grey.
class _PeopleAvatars extends StatelessWidget {
  const _PeopleAvatars(this.glyphs);

  final List<String> glyphs;

  static const double _diameter = 22;
  static const double _step = 15;

  @override
  Widget build(BuildContext context) {
    if (glyphs.isEmpty) return const Icon(Icons.people_outline);
    Widget circle(int index) {
      final first = index == 0;
      return Positioned(
        left: index * _step,
        child: Container(
          width: _diameter,
          height: _diameter,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: first ? OmiColors.accent : OmiColors.textPrimary.withValues(alpha: 0.32),
            border: first
                ? Border.all(color: OmiColors.surface0, width: 2, strokeAlign: BorderSide.strokeAlignOutside)
                : null,
          ),
          child: Text(
            glyphs[index],
            style: OmiType.caption.copyWith(
              color: first ? OmiColors.onAccent : OmiColors.textPrimary,
              fontWeight: FontWeight.w700,
              height: 1,
            ),
          ),
        ),
      );
    }

    return SizedBox(
      width: _diameter + _step * (glyphs.length - 1),
      height: _diameter,
      // Painted last to first so the first person sits on top.
      child: Stack(clipBehavior: Clip.none, children: [for (var i = glyphs.length - 1; i >= 0; i--) circle(i)]),
    );
  }
}

/// Opens the move-to-folder sheet. A filed conversation's folder glyph keeps the folder's colour.
class _FolderChip extends StatelessWidget {
  const _FolderChip({required this.conversation, required this.folder});

  final ServerConversation conversation;
  final Folder? folder;

  @override
  Widget build(BuildContext context) {
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
        child: ConversationDetailChip(
          key: const Key('conversation_folder'),
          icon: FaIcon(folderIconToFa(folder?.icon), size: 13, color: folder?.colorValue),
          label: label,
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

/// Private or Shared, opened from the conversation's ⋯ menu.
abstract final class ConversationVisibilitySheet {
  static void show(BuildContext context, ServerConversation conversation) {
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
              if (isSelected) Icon(Icons.check_circle, color: OmiColors.textPrimary, size: 22),
            ],
          ),
        ),
      ),
    );
  }
}
